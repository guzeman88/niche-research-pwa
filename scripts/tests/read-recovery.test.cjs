const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');
function load(file,extra={}){
 const context={exports:{},URL,AbortController,DOMException,SyntaxError,Response,Date,Math,clearTimeout,setTimeout:(fn)=>{fn();return 1},...extra};
 // Test delays complete immediately; request timeouts must not pre-abort.
 context.setTimeout=(fn,ms)=>ms>3000?123:setImmediate(fn);
 context.clearTimeout=()=>{};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,context);
 return context.exports;
}
function operator(fetch){
 const contracts=load('src/lib/dataContracts.ts');
 return load('src/lib/operatorConnection.ts',{require:()=>contracts,location:{hostname:'etgen.test',origin:'https://etgen.test',pathname:'/validation'},sessionStorage:{getItem:()=>null},fetch});
}
const json=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json'}});

test('a transient read gets new scoped permissions; never reuse an expired ticket',async()=>{
 const calls=[];let tickets=0;
 const api=operator(async(url,options)=>{
  calls.push({url,method:options.method,authorization:options.headers.Authorization});
  if(url==='/api/account/backend/access')return json({url:'https://fixture.test/'+(++tickets),token:'ticket-'+tickets});
  return tickets===1?json({detail:'busy'},503):json({projects:[]});
 });
 api.setAccountConnectionAvailable(true);
 assert.deepEqual(JSON.parse(JSON.stringify(await api.operatorRequest('/api/product-validation'))),{projects:[]});
 assert.equal(tickets,2);assert.equal(calls[1].authorization,'Bearer ticket-1');assert.equal(calls[3].authorization,'Bearer ticket-2');
});

test('writes and authorization failures are never automatically replayed',async()=>{
 let permission=0,actions=0;
 const api=operator(async(url)=>{if(url==='/api/account/backend/access'){permission++;return json({url:'https://fixture.test/action',token:'ticket'})}actions++;return json({detail:'failed'},503)});
 api.setAccountConnectionAvailable(true);
 await assert.rejects(()=>api.operatorRequest('/api/production/jobs',{spec:{}}));
 assert.equal(permission,1);assert.equal(actions,1);
 let requests=0;
 const denied=operator(async()=>{requests++;return json({error:'Sign in again'},401)});denied.setAccountConnectionAvailable(true);
 await assert.rejects(()=>denied.operatorRequest('/api/product-validation'));assert.equal(requests,1);
});

test('malformed collections fail visibly rather than becoming empty or accurate-looking counts',async()=>{
 let calls=0;
 const api=operator(async url=>{if(url==='/api/account/backend/access')return json({url:'https://fixture.test/read',token:'ticket'});calls++;return json({projects:null})});api.setAccountConnectionAvailable(true);
 await assert.rejects(()=>api.operatorRequest('/api/product-validation'),/incomplete or inconsistent/);assert.equal(calls,1);
 const {validateReadData}=load('src/lib/dataContracts.ts');
 for(const bad of [{items:[],total:null},{items:[{keyword:'x',listing_count:-2}],total:1},{items:[{keyword:'x'},{keyword:'x'}],total:2}])assert.throws(()=>validateReadData('/api/dashboard/keywords',bad));
 assert.doesNotThrow(()=>validateReadData('/api/dashboard/keywords',{items:[{keyword:'x',listing_count:null,avg_price_usd:null}],total:1}));
});

test('a cancelled read does not obtain a permission or send a request',async()=>{
 let requests=0;const api=operator(async()=>{requests++;return json({})});api.setAccountConnectionAvailable(true);
 const controller=new AbortController();controller.abort();
 await assert.rejects(()=>api.operatorFetch('/api/health',{signal:controller.signal}));assert.equal(requests,0);
});

test('a session-renewal conflict retries reads using a fresh session',async()=>{
 let tickets=0;const api=operator(async url=>url==='/api/account/backend/access'?++tickets===1?json({error:'Session changed'},409):json({url:'https://fixture.test/read',token:'renewed'}):json({projects:[]}));api.setAccountConnectionAvailable(true);
 await api.operatorRequest('/api/product-validation');assert.equal(tickets,2);
});


test('an interrupted file body retries with a new ticket and preserves exact bytes',async()=>{
 let tickets=0;
 const api=operator(async url=>{
  if(url==='/api/account/backend/access')return json({url:'https://fixture.test/file',token:'ticket-'+(++tickets)});
  if(tickets===1){const response=new Response('partial');response.arrayBuffer=async()=>{throw new TypeError('Connection reset after headers')};return response}
  return new Response(Uint8Array.from([1,2,3,4]),{headers:{'content-type':'application/pdf'}});
 });api.setAccountConnectionAvailable(true);
 const response=await api.operatorFetch('/api/production/jobs/fixture/files/customer.pdf');
 assert.equal(tickets,2);assert.deepEqual([...new Uint8Array(await response.arrayBuffer())],[1,2,3,4]);assert.equal(response.headers.get('content-type'),'application/pdf');
});


test('a read completed after account or connection removal cannot refill its cache',async()=>{
 let api;
 api=operator(async url=>{
  if(url==='/api/account/backend/access')return json({url:'https://fixture.test/read',token:'ticket'});
  api.setAccountConnectionAvailable(false);
  return json({projects:[]});
 });api.setAccountConnectionAvailable(true);
 await assert.rejects(()=>api.operatorRequest('/api/product-validation'),/workspace connection changed/);
});
