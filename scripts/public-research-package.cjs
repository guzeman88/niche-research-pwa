const fs=require('node:fs');
const path=require('node:path');
const {createHash}=require('node:crypto');
const names=['stats.json','opportunities.json','store-ideas.json','gaps.json','keywords.json','breakouts.json','reports.json','test-candidates.json'];
const digest=value=>createHash('sha256').update(value).digest('hex');
const fileName=name=>names.includes(name)&&name!=='keywords.json'||/^keywords\/part-[0-9]{5}\.json$/.test(name);
const MAX_FILE=8*1024*1024,MAX_TOTAL=512*1024*1024;

function validateManifest(m){
 if(m?.schema_version!==1||m.source!=='supabase_local'||m.scope!=='local_research_projection'||!/^[a-f0-9]{64}$/.test(m.id||'')||!/^[a-f0-9]{40}$/.test(m.commit||'')||!Number.isFinite(Date.parse(m.generated_at))||m.source_data_as_of!==null&&!Number.isFinite(Date.parse(m.source_data_as_of)))throw new Error('Invalid public research identity.');
 if(!m.files||!m.resources||Object.keys(m.resources).length!==names.length||names.some(n=>!m.resources[n]))throw new Error('Incomplete public research resources.');
 const entries=Object.entries(m.files);
 if(!entries.length||entries.length>512||entries.some(([n,v])=>!fileName(n)||!/^[a-f0-9]{64}$/.test(v.sha256||'')||!Number.isSafeInteger(v.bytes)||v.bytes<2||v.bytes>MAX_FILE)||entries.reduce((s,[,v])=>s+v.bytes,0)>MAX_TOTAL)throw new Error('Public research size or file bounds failed.');
 const required=[];
 for(const n of names){const r=m.resources[n];if(n==='keywords.json'){
  if(!Array.isArray(r.parts)||!r.parts.length||new Set(r.parts).size!==r.parts.length||!Number.isSafeInteger(r.items)||r.items<0||r.parts.some((p,i)=>p!==`keywords/part-${String(i).padStart(5,'0')}.json`))throw new Error('Invalid keyword partitions.');
  required.push(...r.parts);
 }else{if(r.path!==n)throw new Error('Invalid public resource path.');required.push(n)}}
 if(required.length!==entries.length||required.some(n=>!m.files[n]))throw new Error('Public research manifest has missing or extra files.');
 const identity={commit:m.commit,source_data_as_of:m.source_data_as_of,files:m.files,resources:m.resources};
 if(digest(JSON.stringify(identity))!==m.id)throw new Error('Public research identity checksum failed.');
 return m;
}

function writePackage(directory,data,{commit,sourceDataAsOf=null,generatedAt=new Date().toISOString()}={}){
 if(!Array.isArray(data['keywords.json'])||data['keywords.json'].length!==data['stats.json']?.total_seeds)throw new Error('Public keyword count differs from statistics.');
 const files={},resources={};fs.mkdirSync(directory,{recursive:true});
 function write(name,bytes){
  if(!fileName(name)||bytes.length>MAX_FILE)throw new Error('Public resource exceeds its bound.');
  const dest=path.join(directory,name);fs.mkdirSync(path.dirname(dest),{recursive:true});fs.writeFileSync(dest+'.tmp',bytes);fs.renameSync(dest+'.tmp',dest);files[name]={sha256:digest(bytes),bytes:bytes.length};
 }
 for(const name of names){
  if(name!=='keywords.json'){write(name,Buffer.from(JSON.stringify(data[name])));resources[name]={path:name};continue}
  const parts=[];let rows=[],size=2;
  const flush=()=>{const part=`keywords/part-${String(parts.length).padStart(5,'0')}.json`;write(part,Buffer.from('['+rows.join(',')+']'));parts.push(part);rows=[];size=2};
  for(const row of data[name]){
   const encoded=JSON.stringify(row),bytes=Buffer.byteLength(encoded);
   if(bytes>512*1024)throw new Error('A public keyword exceeds its record bound.');
   if(rows.length&&(rows.length>=5000||size+bytes+1>4*1024*1024))flush();
   rows.push(encoded);size+=bytes+1;
  }
  if(rows.length||!parts.length)flush();resources[name]={parts,items:data[name].length};
 }
 const identity={commit,source_data_as_of:sourceDataAsOf,files,resources};
 const manifest={schema_version:1,source:'supabase_local',scope:'local_research_projection',generated_at:generatedAt,...identity,id:digest(JSON.stringify(identity))};
 validateManifest(manifest);fs.writeFileSync(path.join(directory,'release.json'),JSON.stringify(manifest,null,2));return manifest;
}

async function boundedBytes(response,limit){
 if(!response.ok)throw new Error('Public research request failed: HTTP '+response.status);
 if(Number(response.headers.get('content-length')||0)>limit)throw new Error('Public research response exceeds its bound.');
 const chunks=[];let size=0;const reader=response.body.getReader();
 try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>limit)throw new Error('Public research response exceeds its bound.');chunks.push(Buffer.from(value))}}finally{await reader.cancel().catch(()=>{})}
 return Buffer.concat(chunks);
}

async function readPackage(read){
 const manifest=validateManifest(JSON.parse((await boundedBytes(await read('release.json'),256*1024)).toString('utf8')));
 const raw={},entries=Object.entries(manifest.files);let cursor=0;
 await Promise.all(Array.from({length:Math.min(4,entries.length)},async()=>{while(cursor<entries.length){const [name,expected]=entries[cursor++];const bytes=await boundedBytes(await read(name,manifest.id),expected.bytes);if(bytes.length!==expected.bytes||digest(bytes)!==expected.sha256)throw new Error('Public research checksum differs: '+name);JSON.parse(bytes.toString('utf8'));raw[name]=bytes}}));
 const keywords=[];for(const part of manifest.resources['keywords.json'].parts){const rows=JSON.parse(raw[part]);if(!Array.isArray(rows))throw new Error('Invalid public keyword partition.');keywords.push(...rows)}
 const stats=JSON.parse(raw['stats.json']);if(keywords.length!==manifest.resources['keywords.json'].items||keywords.length!==stats.total_seeds||new Set(keywords.map(r=>r.keyword)).size!==keywords.length)throw new Error('Public research keyword counts or identities disagree.');
 return {manifest,raw};
}
module.exports={names,validateManifest,writePackage,boundedBytes,readPackage};
