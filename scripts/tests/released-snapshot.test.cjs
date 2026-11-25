const {test}=require('node:test');
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const {readReleasedSnapshot}=require('../released-snapshot.cjs');
test('recovery preserves the complete immutable release, its dates and every exact snapshot byte',async()=>{
 const origin='https://0123456789abcdef01234567--etgen.netlify.app',commit='a'.repeat(40),date='2026-11-24T12:00:00Z';
 const names=['stats.json','opportunities.json','store-ideas.json','gaps.json','keywords.json','breakouts.json','reports.json','test-candidates.json'];
 const raw=Object.fromEntries(names.map(name=>[name,Buffer.from(JSON.stringify(name==='stats.json'?{total_seeds:1}:name==='keywords.json'?[{keyword:'fixture'}]:[]))]));
 const release={source:'supabase',commit,generated_at:date,source_data_as_of:date,files:Object.fromEntries(names.map(name=>[name,createHash('sha256').update(raw[name]).digest('hex')]))};
 let corrupt=false;
 const read=async url=>{const name=url.split('/').pop();return new Response(name==='release.json'?JSON.stringify(release):corrupt&&name==='keywords.json'?'[]':raw[name])};
 const prior=await readReleasedSnapshot(origin,commit,read);assert.deepEqual(prior.raw,raw);assert.equal(prior.release.source_data_as_of,date);
 await assert.rejects(readReleasedSnapshot(origin,'b'.repeat(40),read),/identity/);
 await assert.rejects(readReleasedSnapshot('https://etgen.xyz',commit,read),/pinned/);
 corrupt=true;await assert.rejects(readReleasedSnapshot(origin,commit,read),/checksum/);
});
