const {test}=require('node:test');
const assert=require('node:assert/strict');
const {randomBytes}=require('node:crypto');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');

test('session encryption rejects tampering and cross-session substitution',async()=>{
  const {seal,unseal}=await import('../../netlify/functions/lib/account-security.mjs');
  const key=randomBytes(32).toString('base64'),value={refresh_token:'private'};
  const encrypted=seal(value,key,'session-one');
  assert.ok(!encrypted.includes('private'));
  assert.deepEqual(unseal(encrypted,key,'session-one'),value);
  assert.throws(()=>unseal(encrypted,key,'session-two'));
  assert.throws(()=>unseal(encrypted,randomBytes(32).toString('base64'),'session-one'));
  const corrupt=Buffer.from(encrypted,'base64url');corrupt[30]^=1;
  assert.throws(()=>unseal(corrupt.toString('base64url'),key,'session-one'));
});
test('production cookies and CSRF reject cross-origin requests',async()=>{
  const {sessionCookie,trustedMutation,validateProfile,validateWorkspace}=await import('../../netlify/functions/lib/account-security.mjs');
  assert.match(sessionCookie('id','https://app.example'),/^__Host-.*HttpOnly.*SameSite=Lax.*Secure$/);
  assert.match(sessionCookie('','https://app.example',true),/Max-Age=0/);
  assert.equal(trustedMutation(new Request('https://app.example',{headers:{Origin:'https://evil.example','Content-Type':'application/json','X-Etgen-Request':'1'}}),'https://app.example'),false);
  assert.throws(()=>validateProfile({role:'admin'}));
  assert.throws(()=>validateWorkspace({'credentials':'secret'}));
});
test('interrupted saves preserve owner edits without exposing them to another account',async()=>{
  const source=fs.readFileSync(path.join(__dirname,'../../src/lib/accountWorkspace.ts'),'utf8');
  const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const module={exports:{}};
  let fail=true;
  new Function('exports','module','require',compiled)(module.exports,module,()=>({accountRequest:async()=>{if(fail)throw new Error('Session expired');return {revision:2};}}));
  const w=module.exports;
  w.activateWorkspace('owner',{},0);w.accountStorage.setItem('stores','["private"]');
  await assert.rejects(w.flushAccountWorkspace());
  w.clearAccountWorkspace();assert.ok(w.hasInterruptedEdits());w.activateWorkspace('other',{},0);
  assert.equal(w.accountStorage.getItem('stores'),null);
  w.clearAccountWorkspace();w.activateWorkspace('owner',{},0);
  assert.equal(w.accountStorage.getItem('stores'),'["private"]');
  assert.ok(w.workspaceStatus().dirty);fail=false;
  await w.flushAccountWorkspace();assert.equal(w.workspaceStatus().dirty,false);assert.equal(w.hasInterruptedEdits(),false);
});
