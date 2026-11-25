const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const {webcrypto}=require('node:crypto');
const {names,writePackage,readPackage,validateManifest}=require('../public-research-package.cjs');
function fixture(count=2,commit='a'.repeat(40)){
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'etgen-public-package-'));
 try{
  const data=Object.fromEntries(names.map(n=>[n,n==='stats.json'?{total_seeds:count}:n==='keywords.json'?Array.from({length:count},(_,i)=>({keyword:'fixture '+i,observed_search_volume:null})):[]]));
  const manifest=writePackage(directory,data,{commit,sourceDataAsOf:'2026-11-25T12:00:00Z'});
  return {manifest,raw:Object.fromEntries(Object.keys(manifest.files).map(n=>[n,fs.readFileSync(path.join(directory,n))]))};
 }finally{assert.equal(path.dirname(directory),os.tmpdir());assert(path.basename(directory).startsWith('etgen-public-package-'));fs.rmSync(directory,{recursive:true})}
}
function loadBrowser(fetch){
 const exports={},context={exports,require:()=>({DataIntegrityError:class DataIntegrityError extends Error{}}),fetch,crypto:webcrypto,Response,AbortSignal,TextEncoder,TextDecoder,Uint8Array,Date};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/lib/publicResearch.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,context);
 return exports;
}
const json=value=>new Response(JSON.stringify(value),{headers:{'content-type':'application/json'}});
test('large exports partition and round-trip every keyword with bounded files and exact hashes',async()=>{
 const f=fixture(11001),seen=[];
 assert.equal(f.manifest.resources['keywords.json'].parts.length,3);
 const actual=await readPackage(async(name,id)=>{seen.push(id);return name==='release.json'?json(f.manifest):new Response(f.raw[name])});
 assert.equal(actual.manifest.id,f.manifest.id);assert.equal(seen.filter(Boolean).length,Object.keys(f.raw).length);
 const data=loadBrowser(async url=>{const name=url.split('?')[0];if(name==='/data/release.json')return json({current_public:{id:f.manifest.id}});if(name==='/data/current/release.json')return json(f.manifest);return new Response(f.raw[name.split(f.manifest.id+'/')[1]])});
 assert.equal((await data.readPublicResearch('keywords.json')).length,11001);
});
test('manifest traversal, excessive sizes, missing partitions and corruption fail closed',async()=>{
 const f=fixture();
 for(const mutate of [m=>m.files['../secret']={bytes:2,sha256:'a'.repeat(64)},m=>m.files['stats.json'].bytes=9*1024*1024,m=>m.resources['keywords.json'].parts=[],m=>m.id='b'.repeat(64)]){
  const m=structuredClone(f.manifest);mutate(m);assert.throws(()=>validateManifest(m));
  await assert.rejects(()=>loadBrowser(()=>{}).validatePublicManifest(m));
 }
 await assert.rejects(()=>readPackage(async n=>n==='release.json'?json(f.manifest):new Response(n==='stats.json'?'{}':f.raw[n])),/checksum|bound/);
 const browser=loadBrowser(async url=>url.startsWith('/data/release.json')?json({current_public:{id:f.manifest.id}}):url.startsWith('/data/current/release.json')?json(f.manifest):new Response('{}'));
 await assert.rejects(()=>browser.readPublicResearch('keywords.json'),/incomplete or inconsistent/);
});
test('old releases stay on original files; a present broken current release never silently uses old data',async()=>{
 const calls=[],old=loadBrowser(async url=>{calls.push(url);return url.startsWith('/data/release.json')?json({commit:'a'.repeat(40)}):json([{keyword:'dated archive'}])});
 assert.equal((await old.readPublicResearch('keywords.json'))[0].keyword,'dated archive');assert.equal(calls.length,2);
 const f=fixture(),broken=loadBrowser(async url=>url.startsWith('/data/release.json')?json({current_public:{id:f.manifest.id}}):new Response('missing',{status:404}));
 await assert.rejects(()=>broken.readPublicResearch('stats.json'));
});
test('a deployment race restarts once with one complete new identity',async()=>{
 const first=fixture(2),second=fixture(3,'b'.repeat(40));let current=first,roots=0;
 const browser=loadBrowser(async url=>{const name=url.split('?')[0];if(name==='/data/release.json'){roots++;return json({current_public:{id:current.manifest.id}})}if(name==='/data/current/release.json')return json(current.manifest);if(name.includes(first.manifest.id)){current=second;return new Response('gone',{status:404})}return new Response(second.raw[name.split(second.manifest.id+'/')[1]])});
 assert.equal((await browser.readPublicResearch('keywords.json')).length,3);assert.equal(roots,2);
});
