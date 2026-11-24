const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');
const {QueryClient}=require('@tanstack/react-query');
const at=()=>new Date().toISOString();
const startup=()=>({schema_version:1,generated_at:at(),input_fingerprint:'qa',projects:{status:'ready',total:1,has_more:false,projects:[{id:'p',name:'Binder',updated_at:at(),raw:'DO-NOT-SAVE'}]},production:{status:'ready',total:0,has_more:false,jobs:[],human_approval_required:true},access_token:'DO-NOT-SAVE'});
function moduleFrom(file,dependencies={}){
 const module={exports:{}};
 const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 new Function('exports','module','require',code)(module.exports,module,name=>dependencies[name]||{});return module.exports;
}
class Storage{rows=new Map();get length(){return this.rows.size}key(i){return [...this.rows.keys()][i]}getItem(k){return this.rows.get(k)||null}setItem(k,v){this.rows.set(k,v)}removeItem(k){this.rows.delete(k)}}
test('bootstrap excludes data until MFA/recovery is complete and never reads admin data for members',async()=>{
 const {bootstrapData}=await import('../../netlify/functions/lib/startup.mjs');
 let reads=0;
 const args={user:{id:'verified-owner',email:'qa@example.test'},profile:{role:'admin'},readWorkspace:async owner=>{assert.equal(owner,'verified-owner');reads++;return {payload:{},revision:1}},readReport:async()=>{reads++;return {startup:startup()}}};
 for(const gate of [{mfa:true},{recovery:true}]){const value=await bootstrapData({...args,...gate});assert.equal(value.workspace,undefined);assert.equal(value.startup,undefined)}
 assert.equal(reads,0);
 const member=await bootstrapData({...args,profile:{role:'member'}});assert.equal(member.startup,undefined);assert.equal(reads,1);
 const admin=await bootstrapData(args);assert.equal(admin.startup.schema_version,1);assert.equal(reads,3);
 const refresh=await bootstrapData({...args,workspace:false});assert.equal(refresh.workspace,undefined);assert.equal(reads,4);
});
test('startup normalizer removes raw evidence and fails closed on malformed counts',async()=>{
 const {normalizeStartup}=await import('../../netlify/functions/lib/startup.mjs');
 const value=startup(),safe=normalizeStartup(value);assert(!JSON.stringify(safe).includes('DO-NOT-SAVE'));
 value.projects.total=0;assert.throws(()=>normalizeStartup(value));
});
test('display cache is bounded, account-scoped, expires and clears on role change/logout',()=>{
 const startupModule=moduleFrom('src/lib/startup.ts');
 const cache=moduleFrom('src/lib/startupCache.ts',{'./startup':startupModule});
 const storage=new Storage(),client=new QueryClient();client.setQueryData(['startup'],startup());
 client.setQueryData(['account-session'],{password:'DO-NOT-SAVE'});
 cache.persistStartupCache(client,'owner','admin',storage);assert.equal(storage.length,1);assert(![...storage.rows.values()][0].includes('DO-NOT-SAVE'));
 const restored=new QueryClient();cache.hydrateStartupCache(restored,'owner','admin',storage);assert.equal(restored.getQueryData(['startup']).projects.total,1);assert.equal(restored.getQueryData(['account-session']),undefined);
 const other=new QueryClient();cache.hydrateStartupCache(other,'another','admin',storage);assert.equal(other.getQueryData(['startup']),undefined);assert.equal(storage.length,0);
 cache.persistStartupCache(client,'owner','admin',storage);cache.hydrateStartupCache(other,'owner','member',storage);assert.equal(storage.length,0);
 cache.persistStartupCache(client,'owner','admin',storage);let [key,raw]=[...storage.rows][0];storage.setItem(key,JSON.stringify({...JSON.parse(raw),savedAt:Date.now()-86400001}));cache.hydrateStartupCache(other,'owner','admin',storage);assert.equal(storage.length,0);
 cache.persistStartupCache(client,'owner','admin',storage);cache.purgeStartupCache(storage);assert.equal(storage.length,0);
});
