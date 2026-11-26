const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');
function api(fetcher){const exports={};const code=ts.transpileModule(fs.readFileSync('src/lib/accountApi.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;new Function('exports','fetch',code)(exports,fetcher);return exports;}
test('account reads stop on the overall deadline and give a recoverable error',async()=>{
 const controller=new AbortController();let calls=0;
 const {accountRequest,AccountError}=api((_url,{signal})=>new Promise((_resolve,reject)=>{calls++;signal.addEventListener('abort',()=>reject(signal.reason),{once:true})}));
 const pending=accountRequest('/bootstrap',undefined,{signal:controller.signal});controller.abort(new DOMException('Deadline','TimeoutError'));
 await assert.rejects(pending,error=>error instanceof AccountError&&error.status===504&&error.message.includes('Retry the connection'));assert.equal(calls,1);
});
test('cancelling a superseded check stays distinct from a provider failure',async()=>{
 const controller=new AbortController();const {accountRequest}=api((_url,{signal})=>new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(signal.reason),{once:true})));
 const pending=accountRequest('/bootstrap',undefined,{signal:controller.signal});controller.abort();await assert.rejects(pending,{name:'AbortError'});
});
test('a stalled JSON response body is covered by the same deadline',async()=>{
 const controller=new AbortController();let started;const ready=new Promise(resolve=>{started=resolve});
 const {accountRequest}=api(async(_url,{signal})=>({ok:true,headers:new Headers({'Content-Type':'application/json'}),json:()=>{started();return new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(signal.reason),{once:true}))}}));
 const pending=accountRequest('/workspace',undefined,{signal:controller.signal});await ready;controller.abort(new DOMException('Deadline','TimeoutError'));await assert.rejects(pending,error=>error.status===504);
});
test('network failure never retries a mutation or asks for automatic credential replay',async()=>{
 let calls=0;const {accountRequest}=api(async()=>{calls++;throw new TypeError('Failed to fetch')});await assert.rejects(accountRequest('/login',{email:'qa@example.test',password:'synthetic-test-only'}),error=>error.status===503&&!error.message.includes('retry'));assert.equal(calls,1);
});
