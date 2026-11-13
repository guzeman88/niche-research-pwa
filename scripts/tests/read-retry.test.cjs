const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readWithRetry}=require('../read-retry.cjs');

test('a transient database read timeout recovers without changing returned data',async()=>{
 let attempts=0;const waits=[],rows=[{keyword:'unknown demand',value:null},{keyword:'measured zero',value:0}];
 const result=await readWithRetry(async()=>{
  if(++attempts<3)throw Object.assign(new Error('statement timeout'),{statusCode:500});
  return rows;
 },{sleep:async ms=>waits.push(ms)});
 assert.equal(result,rows);assert.equal(attempts,3);assert.deepEqual(waits,[1000,2000]);
});

test('authorization, invalid input and malformed-data failures are not retried',async()=>{
 for(const properties of [{statusCode:401},{statusCode:403},{statusCode:400},{}]){
  let attempts=0;const error=Object.assign(new Error('permanent'),properties);
  await assert.rejects(readWithRetry(async()=>{attempts++;throw error;},{sleep:async()=>assert.fail('unexpected retry')}),value=>value===error);
  assert.equal(attempts,1);
 }
});

test('network retries are bounded and preserve the final failure',async()=>{
 let attempts=0;const error=Object.assign(new Error('connection reset'),{code:'ECONNRESET'});
 await assert.rejects(readWithRetry(async()=>{attempts++;throw error;},{sleep:async()=>{}}),value=>value===error);
 assert.equal(attempts,3);
});
