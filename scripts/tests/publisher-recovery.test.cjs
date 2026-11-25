const {test}=require('node:test');
const assert=require('node:assert/strict');
test('publisher waits through bounded connector recovery without retrying security failures',async()=>{
 const {waitForBackend}=await import('../private-public-export.mjs');
 let attempts=0,waits=0;const result=await waitForBackend({},'fixture',{lookup:async()=>{if(++attempts<3)throw new Error('The private connector is reconnecting.');return {endpoint:'fixture'}},wait:async()=>{waits++}});
 assert.equal(result.endpoint,'fixture');assert.equal(waits,2);
 attempts=0;await assert.rejects(()=>waitForBackend({},'fixture',{lookup:async()=>{attempts++;throw new Error('The research connection failed verification.')},wait:async()=>{throw new Error('Must not wait')}}),/verification/);assert.equal(attempts,1);
 attempts=0;await assert.rejects(()=>waitForBackend({},'fixture',{lookup:async()=>{attempts++;throw new Error('The connection heartbeat is delayed.')},wait:async()=>{}}),/delayed/);assert.equal(attempts,7);
});
