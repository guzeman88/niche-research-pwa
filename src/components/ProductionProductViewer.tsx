import {useEffect, useId, useRef, useState} from 'react'
import {useQuery} from '@tanstack/react-query'
import {createPortal} from 'react-dom'
import {artifactBlob, documentPageBlob, downloadArtifact, productionRequest, type ProductionJob} from '../lib/production'
import './ProductionProductViewer.css'

type Cell = {address:string;value:string|number|boolean|null;formula:string|null;format:string;bold:boolean;fill:string|null}
type Sheet = {name:string;state:string;rows:Cell[][];columns:number;merged:string[]}
type View = {artifact_fingerprint:string;name:string} & (
  {kind:'workbook';sheets:Sheet[]} | {kind:'text';text:string} |
  {kind:'slides';slides:string[][]} | {kind:'package';files:{name:string;bytes:number}[]})

function ImagePage({job,name,label,pdf}:{job:string;name:string;label:string;pdf?:{name:string;fingerprint:string;page:number}}) {
  const target=useRef<HTMLElement>(null)
  const pdfName=pdf?.name,pdfFingerprint=pdf?.fingerprint,pdfPage=pdf?.page
  const [visible,setVisible]=useState(false),[url,setUrl]=useState(''),[error,setError]=useState(''),[attempt,setAttempt]=useState(0)
  useEffect(()=>{
    const observer=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting)){setVisible(true);observer.disconnect()}},{rootMargin:'400px'})
    if(target.current)observer.observe(target.current)
    return ()=>observer.disconnect()
  },[])
  useEffect(()=>{
    if(!visible)return
    let active=true,objectUrl=''
    const request=pdfName&&pdfFingerprint&&pdfPage!==undefined?documentPageBlob(job,pdfName,pdfFingerprint,pdfPage):artifactBlob(job,name)
    request.then(blob=>{objectUrl=URL.createObjectURL(blob);if(active){setUrl(objectUrl);setError('')}else URL.revokeObjectURL(objectUrl)}).catch(cause=>{if(active)setError(cause instanceof Error?cause.message:'This page could not be loaded.')})
    return ()=>{active=false;if(objectUrl)URL.revokeObjectURL(objectUrl)}
  },[job,name,visible,attempt,pdfName,pdfFingerprint,pdfPage])
  return <figure ref={target} className="product-viewer-page"><figcaption>{label}</figcaption>{url?<img src={url} alt={label} decoding="async"/>:error?<div role="alert">{error}<button type="button" onClick={()=>{setError('');setAttempt(x=>x+1)}}>Retry page</button></div>:<div className="product-viewer-loading" role="status">Loading {label.toLowerCase()}…</div>}</figure>
}

function columnName(index:number){let result='';for(let n=index+1;n;n=Math.floor((n-1)/26))result=String.fromCharCode(65+(n-1)%26)+result;return result}
function display(cell:Cell){
  if(cell.value===null)return cell.formula?'Not calculated':''
  if(typeof cell.value==='boolean')return cell.value?'TRUE':'FALSE'
  if(typeof cell.value!=='number')return cell.value
  const percentage=cell.format.includes('%'),currency=cell.format.includes('$')
  if(percentage)return new Intl.NumberFormat('en-US',{style:'percent',maximumFractionDigits:2}).format(cell.value)
  if(currency)return new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(cell.value)
  return String(cell.value)
}

function Workbook({sheets}:{sheets:Sheet[]}){
  const [index,setIndex]=useState(0),[start,setStart]=useState(0),[selected,setSelected]=useState<[number,number]>([0,0])
  const sheet=sheets[index],cell=sheet?.rows[selected[0]]?.[selected[1]],table=useRef<HTMLTableElement>(null)
  if(!sheet)return <p>No worksheets in this file.</p>
  const end=Math.min(start+100,sheet.rows.length)
  function select(row:number,col:number,focus=false){
    row=Math.max(0,Math.min(sheet.rows.length-1,row));col=Math.max(0,Math.min(sheet.columns-1,col))
    setSelected([row,col]);setStart(Math.floor(row/100)*100)
    if(focus)requestAnimationFrame(()=>table.current?.querySelector<HTMLElement>(`[data-cell="${row}-${col}"]`)?.focus())
  }
  return <div className="product-workbook">
    <div className="product-viewer-controls"><label>Worksheet<select aria-label="Worksheet" value={index} onChange={event=>{setIndex(Number(event.target.value));setStart(0);setSelected([0,0])}}>{sheets.map((s,i)=><option key={s.name} value={i}>{s.name}{s.state==='visible'?'':` (${s.state})`}</option>)}</select></label><span>Read-only · saved values</span></div>
    <div className="product-formula"><strong>{cell?.address||'Cell'}</strong><output aria-label="Cell contents">{cell?.formula||String(cell?.value??'')}</output></div>
    <div className="product-sheet-scroll" tabIndex={0} role="region" aria-label={`${sheet.name} worksheet`}>
      <table ref={table} role="grid" aria-readonly="true" aria-label={`${sheet.name} cells`}><thead><tr><th aria-label="Row"/>{Array.from({length:sheet.columns},(_,i)=><th key={i} scope="col">{columnName(i)}</th>)}</tr></thead>
        <tbody>{sheet.rows.slice(start,end).map((row,offset)=><tr key={start+offset}><th scope="row">{start+offset+1}</th>{row.map((c,col)=><td role="gridcell" key={c.address} data-cell={`${start+offset}-${col}`} tabIndex={selected[0]===start+offset&&selected[1]===col?0:-1} aria-selected={selected[0]===start+offset&&selected[1]===col} onClick={()=>select(start+offset,col)} onFocus={()=>setSelected([start+offset,col])} onKeyDown={event=>{const move:Record<string,[number,number]>={ArrowDown:[1,0],ArrowUp:[-1,0],ArrowRight:[0,1],ArrowLeft:[0,-1]};if(move[event.key]){event.preventDefault();select(start+offset+move[event.key][0],col+move[event.key][1],true)}}} style={{fontWeight:c.bold?600:400}} title={c.formula||undefined}>{display(c)}</td>)}</tr>)}</tbody></table>
    </div>
    <div className="product-viewer-controls"><button type="button" disabled={start===0} onClick={()=>{setStart(Math.max(0,start-100));setSelected([Math.max(0,start-100),0])}}>Previous rows</button><span>{start+1}–{end} of {sheet.rows.length} rows</span><button type="button" disabled={end===sheet.rows.length} onClick={()=>{setStart(end);setSelected([end,0])}}>Next rows</button></div>
    {sheet.merged.length>0&&<details><summary>Merged cells</summary><p>{sheet.merged.join(', ')}</p></details>}
  </div>
}

export default function ProductionProductViewer({job}:{job:ProductionJob}){
  const manifest=job.result?.manifest,files=manifest?.render.customer_files||manifest?.files.filter(f=>f.name.startsWith('customer.')||['instructions.txt','font-license.txt'].includes(f.name)).map(f=>f.name)||[],fingerprint=manifest?.artifact_fingerprint||''
  const [selected,setSelected]=useState('document'),[zoom,setZoom]=useState(100),[downloadError,setDownloadError]=useState('')
  const [expanded,setExpanded]=useState(false)
  const viewer=useRef<HTMLElement>(null),expandButton=useRef<HTMLButtonElement>(null),exitButton=useRef<HTMLButtonElement>(null)
  useEffect(()=>{
    if(!expanded)return
    const overflow=document.body.style.overflow
    document.body.style.overflow='hidden'
    exitButton.current?.focus()
    const keys=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){
        event.preventDefault();event.stopImmediatePropagation();setExpanded(false)
      }else if(event.key==='Tab'){
        // Keep focus in this viewer, including when it is inside the mobile drawer.
        event.preventDefault();event.stopImmediatePropagation()
        const elements=[exitButton.current,...(viewer.current?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],select:not(:disabled),summary,[tabindex="0"]')||[])].filter((element):element is HTMLElement=>Boolean(element?.checkVisibility()))
        const index=elements.indexOf(document.activeElement as HTMLElement)
        elements[(index+(event.shiftKey?-1:1)+elements.length)%elements.length]?.focus()
      }
    }
    document.addEventListener('keydown',keys,true)
    return ()=>{
      document.body.style.overflow=overflow
      document.removeEventListener('keydown',keys,true)
      requestAnimationFrame(()=>expandButton.current?.focus())
    }
  },[expanded])
  const pdfName=files.find(name=>name.endsWith('.pdf'))
  const documentQuery=useQuery({queryKey:['product-document',job.id,fingerprint,pdfName],enabled:selected==='document'&&Boolean(pdfName),queryFn:async()=>{const data=await productionRequest<{pages:number;previews:string[];artifact_fingerprint:string}>(`/jobs/${encodeURIComponent(job.id)}/document?name=${encodeURIComponent(pdfName!)}&fingerprint=${encodeURIComponent(fingerprint)}`);if(data.artifact_fingerprint!==fingerprint||!Number.isSafeInteger(data.pages)||data.pages<1||data.pages>500)throw new Error('The document could not be verified. Reopen its review.');return data},retry:false,staleTime:Infinity})
  const documentImages=pdfName?(documentQuery.data?.previews.length?documentQuery.data.previews:Array.from({length:documentQuery.data?.pages||0},(_,i)=>'pdf-page-'+i)):manifest?.render.previews||['preview.png']
  const options=[{id:'document',label:'Document',images:documentImages},
    ...files.filter(name=>/\.(xlsx|pptx|txt|zip)$/i.test(name)).map(name=>({id:name,label:name.endsWith('.xlsx')?'Spreadsheet':name.endsWith('.pptx')?'Slide text':name==='instructions.txt'?'Instructions':name==='font-license.txt'?'Font license':name.endsWith('.zip')?'Package contents':name,images:[] as string[]})),
    ...(job.result?.listing_images?.length?[{id:'listing-images',label:'Listing images',images:job.result.listing_images}]:[])]
  const option=options.find(o=>o.id===selected)||options[0],id=useId(),viewport=useRef<HTMLDivElement>(null)
  const query=useQuery({queryKey:['product-file-view',job.id,fingerprint,option.id],enabled:!['document','listing-images'].includes(option.id),
    queryFn:async()=>{const data=await productionRequest<View>(`/jobs/${encodeURIComponent(job.id)}/view?name=${encodeURIComponent(option.id)}&fingerprint=${encodeURIComponent(fingerprint)}`);if(data.artifact_fingerprint!==fingerprint||data.name!==option.id)throw new Error('The product package changed. Reopen its review.');return data},retry:false,staleTime:Infinity})
  if(!manifest)return null
  return <section ref={viewer} id={`${id}-viewer`} className={`product-viewer${expanded?' product-viewer-expanded':''}`} role={expanded?'dialog':'region'} aria-modal={expanded||undefined} aria-label="Complete product viewer">
    {expanded&&<header className="product-viewer-heading"><h3>{job.spec.name}</h3></header>}
    <div className="product-viewer-controls"><label>View<select aria-label="View" value={option.id} onChange={event=>{setSelected(event.target.value);setZoom(100)}}>{options.map(o=><option key={o.id} value={o.id}>{o.label}</option>)}</select></label>
      {!expanded&&<button ref={expandButton} type="button" className="product-viewer-expand" aria-controls={`${id}-viewer`} aria-expanded="false" onClick={()=>setExpanded(true)}>Full screen</button>}
      {option.images.length>0&&<><label>Page<select aria-label="Page" defaultValue="0" key={option.id} onChange={event=>{const target=viewport.current?.querySelector<HTMLElement>(`[data-page="${event.target.value}"]`);if(target&&viewport.current)viewport.current.scrollTo({top:target.offsetTop,behavior:'instant'})}}>{option.images.map((_,i)=><option key={i} value={i}>{i+1} of {option.images.length}</option>)}</select></label><label>Zoom<select aria-label="Zoom" value={zoom} onChange={event=>setZoom(Number(event.target.value))}>{[100,125,150,200].map(value=><option key={value} value={value}>{value===100?'Fit width':value+'%'}</option>)}</select></label></>}
    </div>
    {option.id==='document'&&pdfName&&documentQuery.isPending?<p role="status">Loading document...</p>:option.id==='document'&&pdfName&&documentQuery.isError?<div role="alert">{documentQuery.error.message}<button type="button" onClick={()=>void documentQuery.refetch()}>Retry document</button></div>:option.images.length>0?<div ref={viewport} className="product-page-scroll" tabIndex={0} role="region" aria-label={option.label+' pages'}><div style={{width:zoom+'%'}}>{option.images.map((name,i)=><div key={name} id={`${id}-${i}`} data-page={i}><ImagePage job={job.id} name={name} pdf={option.id==='document'&&pdfName&&!documentQuery.data?.previews.length?{name:pdfName,fingerprint,page:i}:undefined} label={`${option.id==='listing-images'?'Image':'Page'} ${i+1} of ${option.images.length}`}/></div>)}</div></div>:query.isPending?<p role="status">Loading {option.label.toLowerCase()}…</p>:query.isError?<div role="alert">{query.error.message}<button type="button" onClick={()=>void query.refetch()}>Retry file</button></div>:query.data?.kind==='workbook'?<Workbook key={option.id} sheets={query.data.sheets}/>:query.data?.kind==='text'?<pre className="product-text">{query.data.text}</pre>:query.data?.kind==='slides'?<div className="product-text">{query.data.slides.map((blocks,i)=><section key={i}><h4>Slide {i+1}</h4>{blocks.map((text,j)=><p key={j}>{text}</p>)}</section>)}</div>:query.data?.kind==='package'?<ul className="product-package">{query.data.files.map(file=><li key={file.name}><span>{file.name}</span><span>{Math.ceil(file.bytes/1024)} KB</span></li>)}</ul>:null}
    <details className="product-downloads"><summary>Download files</summary><ul>{manifest.files.filter(file=>files.includes(file.name)).map(file=><li key={file.name}><button type="button" onClick={()=>{setDownloadError('');downloadArtifact(job.id,file.name).catch(error=>setDownloadError(error instanceof Error?error.message:'The download failed. Retry the file.'))}}>{file.name}</button></li>)}</ul>{downloadError&&<p role="alert">{downloadError}</p>}</details>
    {expanded&&createPortal(<button ref={exitButton} type="button" className="product-viewer-exit" onClick={()=>setExpanded(false)}>Exit full screen</button>,document.body)}
  </section>
}
