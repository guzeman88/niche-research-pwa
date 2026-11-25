const {test}=require('node:test');
const assert=require('node:assert/strict');
const {randomBytes}=require('node:crypto');
test('provider quotas and outages are distinct from invalid credentials',async()=>{
 const {accountServiceProblem:problem}=await import('../../netlify/functions/lib/account-availability.mjs');
 assert.equal(problem({status:402,error:{message:'exceed_db_size_quota'}}).reason,'database_size_quota');
 assert.equal(problem({error:{status:402,message:'exceed_db_size_quota'}}).status,503);
 assert.equal(problem({status:503,error:{message:'Internal error'}}).code,'account_service_unavailable');
 assert.equal(problem({error:{status:400,code:'invalid_credentials',message:'Invalid login credentials'}}),null);
 assert.equal(problem({status:409,error:{code:'PT409',message:'Conflict'}}),null);
});
test('restricted password login and existing sessions fail closed without clearing cookies or querying passwords',async()=>{
 const {default:handler}=await import('../../netlify/functions/account.mjs');
 const previous=global.fetch;let calls=[];
 Object.assign(process.env,{APP_ORIGIN:'https://app.example',SUPABASE_URL:'https://auth.example',SUPABASE_ANON_KEY:'qa-anon',SUPABASE_SERVICE_ROLE_KEY:'qa-service',AUTH_COOKIE_SECRET:randomBytes(32).toString('base64')});
 global.fetch=async input=>{calls.push(String(input?.url||input));return Response.json({message:'Service restricted: exceed_db_size_quota'},{status:402})};
 try{
  for(const method of ['GET','POST']){
   calls=[];
   const response=await handler(new Request('https://app.example/api/account'+(method==='GET'?'/bootstrap':'/login'),{method,headers:{Origin:'https://app.example','X-Etgen-Request':'1','Content-Type':'application/json',Cookie:'__Host-etgen-session='+'a'.repeat(43)},...(method==='POST'?{body:JSON.stringify({email:'qa@example.test',password:'not-a-real-password'})}:{})}));
   const data=await response.json();assert.equal(response.status,503);assert.equal(data.code,'account_service_restricted');assert.equal(data.reason,'database_size_quota');
   assert.match(data.error,/storage limit/);assert.equal(response.headers.get('set-cookie'),null);
   assert(!calls.some(url=>url.includes('/auth/v1/token')),'A provider-level failure must not reach password authentication');
   assert(!JSON.stringify(data).includes('auth.example'));
  }
 }finally{global.fetch=previous}
});
