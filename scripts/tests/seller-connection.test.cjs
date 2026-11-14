const test=require('node:test');
const assert=require('node:assert/strict');

test('seller authorization is restricted to the exact Etsy consent endpoint',async()=>{
  const {verifiedAuthorization}=await import('../../netlify/functions/lib/seller-connection.mjs');
  assert.equal(verifiedAuthorization({authorize_url:'https://www.etsy.com/oauth/connect?client_id=example',expected_shop:'Example'}).expected_shop,'Example');
  for(const authorize_url of ['https://evil.invalid/oauth/connect','http://www.etsy.com/oauth/connect','https://www.etsy.com.evil.invalid/oauth/connect','https://www.etsy.com/other','https://name@www.etsy.com/oauth/connect'])
    assert.throws(()=>verifiedAuthorization({authorize_url}));
});
test('seller callbacks require bounded state/code and never forward provider error text',async()=>{
  const {callbackFields}=await import('../../netlify/functions/lib/seller-connection.mjs');
  assert.deepEqual(callbackFields(new URL('https://etgen.xyz/api/account/etsy/callback?state='+('a'.repeat(30))+'&code=example-code')),{state:'a'.repeat(30),code:'example-code'});
  assert.throws(()=>callbackFields(new URL('https://etgen.xyz/api/account/etsy/callback?code=x')));
  assert.throws(()=>callbackFields(new URL('https://etgen.xyz/api/account/etsy/callback?state=bad&code=x')));
  assert.equal(callbackFields(new URL('https://etgen.xyz/api/account/etsy/callback?error=access_denied&error_description=PRIVATE_PROVIDER_TEXT')),null);
});
