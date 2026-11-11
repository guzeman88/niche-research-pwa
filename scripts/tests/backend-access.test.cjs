const {test}=require('node:test');
const assert=require('node:assert/strict');
const {createHmac}=require('node:crypto');

test('backend tickets restrict resources, expire promptly and never contain the long-lived key',async()=>{
 const {backendPath,accessTicket}=await import('../../netlify/functions/lib/backend-access.mjs');
 for(const path of ['https://evil.test/api/production','//evil.test/api/production','/api/production/../settings','/api/production/%2e%2e/settings','/api/production/%252fsecret','/api/account/login','/api/production#secret'])assert.throws(()=>backendPath(path));
 assert.throws(()=>backendPath('/api/production','PATCH'));
 const secret='s'.repeat(64),at=Date.now();
 const resource=backendPath('/api/production/jobs/fixture/files/hello%20world.pdf','GET');
 const result=accessTicket({endpoint:'https://fixture.trycloudflare.com',token:secret},resource,'admin-fixture',at);
 const [header,payload,signature]=result.token.split('.');const claims=JSON.parse(Buffer.from(payload,'base64url'));
 assert.equal(claims.path,'/api/production/jobs/fixture/files/hello world.pdf');
 assert.equal(claims.exp-claims.iat,30);assert.equal(claims.sub,'admin-fixture');
 assert.equal(signature,createHmac('sha256',secret).update(header+'.'+payload).digest('base64url'));
 assert(!JSON.stringify(result).includes(secret));
});

test('missing, stale or invalid backend connections fail closed',async()=>{
 const {activeBackend}=await import('../../netlify/functions/lib/backend-access.mjs');
 const fake=data=>({from:()=>({select:()=>({eq:()=>({maybeSingle:async()=>({data})})})})});
 for(const data of [null,{enabled:false},{enabled:true,updated_at:'invalid'},{enabled:true,updated_at:new Date(Date.now()-200000).toISOString()}])await assert.rejects(()=>activeBackend(fake(data),'invalid'));
});
