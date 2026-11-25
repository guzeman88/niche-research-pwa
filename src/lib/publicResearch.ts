import {DataIntegrityError} from './dataContracts'

type Resource = {path?:string;parts?:string[];items?:number}
interface Manifest {
  schema_version:number;source:string;scope:string;id:string;commit:string
  generated_at:string;source_data_as_of:string|null
  files:Record<string,{bytes:number;sha256:string}>;resources:Record<string,Resource>
}
const names=['stats.json','opportunities.json','store-ideas.json','gaps.json','keywords.json','breakouts.json','reports.json','test-candidates.json']
const fail=():never=>{throw new DataIntegrityError('The published research package is incomplete or inconsistent. Retry to load a complete release.')}
const hash=async(bytes:Uint8Array)=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new Uint8Array(bytes)))).map(x=>x.toString(16).padStart(2,'0')).join('')
const object=(value:unknown):value is Record<string,unknown>=>value!==null&&typeof value==='object'&&!Array.isArray(value)
async function bytes(response:Response,limit:number){
  if(!response.ok||!response.body||Number(response.headers.get('content-length')||0)>limit)fail()
  const reader=response.body!.getReader(),chunks:Uint8Array[]=[];let size=0
  try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>limit)fail();chunks.push(value)}}finally{await reader.cancel().catch(()=>{})}
  const result=new Uint8Array(size);let offset=0;for(const chunk of chunks){result.set(chunk,offset);offset+=chunk.length}return result
}
const read=(path:string)=>fetch(path+(path.includes('?')?'&':'?')+'release='+Date.now(),{cache:'no-store',redirect:'error',signal:AbortSignal.timeout(30000)})
const parse=(raw:Uint8Array):unknown=>{try{return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw))}catch{return fail()}}
export async function validatePublicManifest(value:unknown):Promise<Manifest>{
  if(!object(value))return fail()
  const m=value as unknown as Manifest
  if(m.schema_version!==1||m.source!=='supabase_local'||m.scope!=='local_research_projection'||!/^[a-f0-9]{64}$/.test(m.id)||!/^[a-f0-9]{40}$/.test(m.commit)||!Number.isFinite(Date.parse(m.generated_at))||m.source_data_as_of!==null&&!Number.isFinite(Date.parse(m.source_data_as_of))||!object(m.files)||!object(m.resources))return fail()
  const entries=Object.entries(m.files),required:string[]=[]
  if(!entries.length||entries.length>512||Object.keys(m.resources).length!==names.length)return fail()
  for(const name of names){const r=m.resources[name];if(!object(r))return fail();if(name==='keywords.json'){
    if(!Array.isArray(r.parts)||!r.parts.length||!Number.isSafeInteger(r.items)||r.items!<0||r.parts.some((p,i)=>p!==`keywords/part-${String(i).padStart(5,'0')}.json`))return fail()
    required.push(...r.parts)
  }else{if(r.path!==name)return fail();required.push(name)}}
  if(required.length!==entries.length||entries.some(([name,r])=>!required.includes(name)||!object(r)||!Number.isSafeInteger(r.bytes)||r.bytes<2||r.bytes>8*1024*1024||!/^[a-f0-9]{64}$/.test(r.sha256))||entries.reduce((s,[,r])=>s+r.bytes,0)>512*1024*1024)return fail()
  const identity={commit:m.commit,source_data_as_of:m.source_data_as_of,files:m.files,resources:m.resources}
  if(await hash(new TextEncoder().encode(JSON.stringify(identity)))!==m.id)return fail()
  return m
}
let pending:Promise<Manifest|null>|undefined,checkedAt=0
async function manifest():Promise<Manifest|null>{
  if(pending&&Date.now()-checkedAt<60000)return pending
  checkedAt=Date.now()
  pending=(async()=>{
    const root=await read('/data/release.json')
    // Releases predating partitioned publication keep their original eight files.
    if(root.status===404||root.ok&&root.headers.get('content-type')?.includes('text/html'))return null
    const release=parse(await bytes(root,256*1024))
    if(!object(release))return fail()
    if(release.current_public===undefined)return null
    if(!object(release.current_public)||!/^([a-f0-9]{64})$/.test(String(release.current_public.id)))return fail()
    const current=await validatePublicManifest(parse(await bytes(await read('/data/current/release.json'),256*1024)))
    if(current.id!==release.current_public.id)return fail()
    return current
  })().catch(error=>{pending=undefined;throw error})
  return pending
}
async function resource(m:Manifest,name:string):Promise<unknown>{
  const r=m.resources[name];if(!r)return fail()
  const load=async(file:string)=>{const expected=m.files[file];const raw=await bytes(await read(`/data/current/${m.id}/${file}`),expected.bytes);if(raw.length!==expected.bytes||await hash(raw)!==expected.sha256)return fail();return parse(raw)}
  if(name!=='keywords.json')return load(r.path!)
  const parts=r.parts!,arrays:unknown[][]=new Array(parts.length);let cursor=0
  await Promise.all(Array.from({length:Math.min(4,parts.length)},async()=>{while(cursor<parts.length){const i=cursor++,rows=await load(parts[i]);if(!Array.isArray(rows))return fail();arrays[i]=rows}}))
  const rows=arrays.flat(),ids=new Set<string>()
  for(const row of rows){if(!object(row)||typeof row.keyword!=='string'||!row.keyword||ids.has(row.keyword))return fail();ids.add(row.keyword)}
  if(rows.length!==r.items)return fail()
  const stats=await resource(m,'stats.json');if(!object(stats)||stats.total_seeds!==rows.length)return fail()
  return rows
}
export async function readPublicResearch(name:string):Promise<unknown>{
  if(!names.includes(name))return fail()
  const first=await manifest()
  if(!first){const response=await read('/data/'+name);if(!response.ok)return null;return parse(await bytes(response,64*1024*1024))}
  try{return await resource(first,name)}catch(error){
    // An atomic deployment can remove the previous family's files mid-read.
    // Restart once only when the release identity actually changed.
    pending=undefined
    const next=await manifest()
    if(next&&next.id!==first.id)return resource(next,name)
    throw error
  }
}
