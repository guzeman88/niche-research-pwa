const {test}=require('node:test');
const assert=require('node:assert/strict');

test('dedicated accounts select a complete separate credential namespace',async()=>{
 const {accountServiceConfig:config}=await import('../../netlify/functions/lib/account-service-config.mjs');
 const research={SUPABASE_URL:'https://research.test',SUPABASE_ANON_KEY:'research-anon',SUPABASE_SERVICE_ROLE_KEY:'research-service'};
 assert.deepEqual(config(research),{dedicated:false,url:research.SUPABASE_URL,anonKey:'research-anon',serviceKey:'research-service'});
 const separate={ACCOUNT_SUPABASE_URL:'https://accounts.test',ACCOUNT_SUPABASE_ANON_KEY:'account-anon',ACCOUNT_SUPABASE_SERVICE_ROLE_KEY:'account-service'};
 assert.deepEqual(config({...research,...separate}),{dedicated:true,url:separate.ACCOUNT_SUPABASE_URL,anonKey:'account-anon',serviceKey:'account-service'});
 for(const [key,value] of Object.entries(separate)){
  const partial=config({...research,[key]:value});
  assert(partial.dedicated);
  assert(!Object.values(partial).includes('research-anon'));
  assert(!Object.values(partial).includes('research-service'));
  assert.notEqual(partial.url,research.SUPABASE_URL);
 }
});

test('incomplete dedicated settings fail closed before any provider request',async()=>{
 const {default:handler}=await import('../../netlify/functions/account.mjs');
 const before={...process.env},previousFetch=global.fetch;let calls=0;
 Object.assign(process.env,{SUPABASE_URL:'https://research.test',SUPABASE_ANON_KEY:'research-anon',SUPABASE_SERVICE_ROLE_KEY:'research-service',ACCOUNT_SUPABASE_URL:'https://accounts.test'});
 delete process.env.ACCOUNT_SUPABASE_ANON_KEY;delete process.env.ACCOUNT_SUPABASE_SERVICE_ROLE_KEY;
 global.fetch=async()=>{calls++;throw new Error('Unexpected provider call')};
 try{
  const response=await handler(new Request('https://etgen.xyz/api/account/bootstrap'));
  assert.equal(response.status,503);assert.equal(calls,0);
  assert.equal(response.headers.get('set-cookie'),null);
 }finally{
  global.fetch=previousFetch;
  for(const key of Object.keys(process.env))if(!(key in before))delete process.env[key];
  Object.assign(process.env,before);
 }
});
