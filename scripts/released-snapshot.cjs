const {createHash}=require('node:crypto');
const names=['stats.json','opportunities.json','store-ideas.json','gaps.json','keywords.json','breakouts.json','reports.json','test-candidates.json'];
async function readReleasedSnapshot(origin,expectedCommit,read=fetch){
 const url=new URL(origin);
 if(url.protocol!=='https:'||!/^([a-f0-9]{24})--etgen\.netlify\.app$/.test(url.hostname)||url.username||url.password||url.search||url.hash||url.pathname!=='/'||!/^[a-f0-9]{40}$/.test(expectedCommit||''))throw new Error('Recovery requires a pinned immutable EtGen deployment URL and its exact source commit.');
 async function bytes(name){
  const response=await read(url.origin+'/data/'+name,{redirect:'error',cache:'no-store',signal:AbortSignal.timeout(30000)});
  if(!response.ok)throw new Error('Published snapshot read failed: '+name);
  const value=Buffer.from(await response.arrayBuffer());if(value.length>64*1024*1024)throw new Error('Published snapshot exceeds the bounded recovery size.');return value;
 }
 const release=JSON.parse((await bytes('release.json')).toString('utf8'));
 if(release.source!=='supabase'||release.commit!==expectedCommit||!Number.isFinite(Date.parse(release.generated_at))||Object.keys(release.files||{}).length!==names.length||names.some(name=>!/^[a-f0-9]{64}$/.test(release.files[name]||'')))throw new Error('Published release identity or snapshot manifest failed verification.');
 const raw={},data={};
 for(const name of names){
  raw[name]=await bytes(name);
  if(createHash('sha256').update(raw[name]).digest('hex')!==release.files[name])throw new Error('Published snapshot checksum differs: '+name);
  data[name]=JSON.parse(raw[name].toString('utf8'));
 }
 if(!Array.isArray(data['keywords.json'])||data['keywords.json'].length!==data['stats.json'].total_seeds)throw new Error('Published keyword count and statistics disagree.');
 return {raw,data,release,origin:url.origin};
}
module.exports={readReleasedSnapshot};
