import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { productionRequest, type ProductionJob } from '../lib/production'
import { operatorHeaders, readConnection } from '../lib/operatorConnection'

interface CustomerInstance {
  id: string; status: string; product_id?: string; revision?: string
  payload?: {values?:Record<string,string>;creative_note?:string}
  result?: {manifest?: {artifact_fingerprint: string; files: Array<{name: string; bytes: number}>}}
  manifest?: {artifact_fingerprint: string; files: Array<{name: string; bytes: number}>}
}

export default function ProductionCustomers({jobs}: {jobs: ProductionJob[]}) {
  const [open,setOpen]=useState(false)
  const [selected,setSelected]=useState('')
  const [notice,setNotice]=useState('')
  const available=jobs.filter(job=>job.spec.schema_version===2 && ['approved','exported'].includes(job.status))
  const list=useQuery({queryKey:['production-customers'],queryFn:()=>productionRequest<CustomerInstance[] | {instances: CustomerInstance[]}>('/customers'),enabled:open,retry:false})
  const detail=useQuery({queryKey:['production-customer',selected],queryFn:()=>productionRequest<CustomerInstance>(`/customers/${selected}`),enabled:open && Boolean(selected),retry:false})
  const rows=Array.isArray(list.data) ? list.data : list.data?.instances || []
  const mutation=useMutation({mutationFn:({path,body}:{path:string;body:unknown})=>productionRequest<Record<string,unknown>>(path,body),onSuccess:value=>{
    if (typeof value.id==='string') setSelected(value.id)
    setNotice('Saved privately. No listing was activated, customer message sent or fulfillment order placed.')
    void list.refetch(); if(selected) void detail.refetch()
  }})
  const run=(path:string,body:unknown={})=>mutation.mutate({path,body})
  const manifest=detail.data?.result?.manifest || detail.data?.manifest
  async function download(name:string) {
    try {
      const {url}=readConnection()
      const response=await fetch(`${url}/api/production/customers/${encodeURIComponent(selected)}/files/${encodeURIComponent(name)}`,{headers:operatorHeaders(url)})
      if (!response.ok) throw new Error('Private file is unavailable or failed verification.')
      const link=document.createElement('a');const href=URL.createObjectURL(await response.blob());link.href=href;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(href),1000)
    } catch (error) {setNotice(error instanceof Error ? error.message : 'Private download failed.')}
  }
  return <details className="mt-6 border-t border-surface-600 pt-5" onToggle={event=>setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer text-sm font-semibold">Private order personalization</summary>
    {open && <div className="mt-4 max-w-3xl space-y-5">
      <p className="max-w-prose text-sm text-surface-200">Bind an operator-imported order to an approved product revision. Customer inputs and proofs stay in private storage. Delivery is an operator handoff; no customer messages or orders are sent automatically.</p>
      {!available.length && <p className="text-sm">Approve a product-line revision before adding customer work.</p>}
      {available.length>0 && <form aria-label="Private customer intake" className="space-y-4" onSubmit={event=>{
        event.preventDefault();const fields=new FormData(event.currentTarget);const job=available.find(value=>value.id===fields.get('catalog_job'));if(!job)return
        const values=Object.fromEntries(String(fields.get('values') || '').split('\n').filter(line=>line.trim()).map(line=>{const colon=line.indexOf(':');if(colon<1)return [line.trim(),''];return [line.slice(0,colon).trim(),line.slice(colon+1).trim()]}))
        run('/customers',{source_order_id:fields.get('source_order_id'),line_item_id:fields.get('line_item_id'),product_id:job.product_id,revision:job.revision,values,
          consent_note:fields.get('consent_note'),retention_note:fields.get('retention_note'),creative_note:fields.get('creative_note')})
      }}>
        <label className="block text-sm">Approved catalog revision<select name="catalog_job" className="input mt-2 w-full">{available.map(job=><option key={job.id} value={job.id}>{job.spec.name} · {job.revision.slice(0,8)}</option>)}</select></label>
        <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Source order reference<input name="source_order_id" className="input mt-2 w-full" required /></label><label className="text-sm">Order line reference<input name="line_item_id" className="input mt-2 w-full" required /></label></div>
        <label className="block text-sm">Personalization · field: value, one per line<textarea name="values" className="input mt-2 w-full" placeholder="recipient: Customer supplied name" required /></label>
        <label className="block text-sm">Photo and input consent<textarea name="consent_note" className="input mt-2 w-full" minLength={10} required /></label>
        <label className="block text-sm">Individual creative choices<textarea name="creative_note" className="input mt-2 w-full" minLength={10} required /></label>
        <label className="block text-sm">Retention and deletion agreement<textarea name="retention_note" className="input mt-2 w-full" minLength={10} required /></label>
        <button className="btn-secondary" disabled={mutation.isPending}>Save private order instance</button>
      </form>}
      {list.error && <p role="alert" className="text-sm">{list.error.message}</p>}
      {rows.length>0 && <label className="block text-sm">Saved private instance<select className="input mt-2 w-full" value={selected} onChange={event=>setSelected(event.target.value)}><option value="">Choose an instance</option>{rows.map(row=><option key={row.id} value={row.id}>{row.id.slice(0,12)} · {row.status.replace(/_/g,' ')}</option>)}</select></label>}
      {detail.data && <div className="space-y-4 border-t border-surface-600 pt-4">
        <p className="text-sm">{detail.data.status.replace(/_/g,' ')}</p>
        <details><summary className="cursor-pointer text-sm">Revise private personalization</summary><form className="mt-3 space-y-3" onSubmit={event=>{event.preventDefault();const fields=new FormData(event.currentTarget);const values=Object.fromEntries(String(fields.get('values')).split('\n').filter(line=>line.trim()).map(line=>{const colon=line.indexOf(':');return [line.slice(0,colon).trim(),line.slice(colon+1).trim()]}));run(`/customers/${selected}/revise`,{values,creative_note:fields.get('creative_note')})}}><label className="block text-sm">Revised fields · field: value<textarea name="values" className="input mt-2 w-full" required defaultValue={Object.entries(detail.data.payload?.values || {}).map(([key,value])=>`${key}: ${value}`).join('\n')} /></label><label className="block text-sm">Creative revision note<textarea name="creative_note" className="input mt-2 w-full" minLength={10} required /></label><button className="btn-secondary" disabled={mutation.isPending}>Preserve revision and invalidate proof approval</button></form></details>
        <form className="space-y-3" onSubmit={event=>{
          event.preventDefault();const fields=new FormData(event.currentTarget);const file=fields.get('photo') as File
          if(!file?.size || file.size>20_000_000){setNotice('Choose a photo no larger than twenty MB.');return}
          const reader=new FileReader();reader.onload=()=>run(`/customers/${selected}/photos`,{base64:String(reader.result).split(',')[1],license_note:fields.get('license_note'),kind:fields.get('kind')});reader.readAsDataURL(file)
        }}><label className="block text-sm">Customer-authorized photo<input name="photo" type="file" accept="image/png,image/jpeg" className="mt-2 block max-w-full text-sm" required /></label><label className="block text-sm">Image purpose<select name="kind" className="input mt-2 w-full"><option value="reference">Reference photo · not finished artwork</option><option value="artwork">Original finished artwork for the customer</option></select></label><label className="block text-sm">Photo rights and consent note<textarea name="license_note" className="input mt-2 w-full" minLength={10} required /></label><button className="btn-secondary" disabled={mutation.isPending}>Preserve private photo</button></form>
        <div className="flex flex-wrap gap-3"><button className="btn-secondary" disabled={mutation.isPending || detail.data.status==='cancelled'} onClick={()=>run(`/customers/${selected}/produce`)}>Produce private proof</button><button className="btn-secondary" disabled={mutation.isPending || ['approved','exported','cancelled'].includes(detail.data.status)} onClick={()=>run(`/customers/${selected}/cancel`)}>Cancel pending customer work</button></div>
        {manifest && <><ul className="space-y-2 text-sm">{manifest.files.map(file=><li key={file.name}><button className="underline underline-offset-4" onClick={()=>void download(file.name)}>Review private file: {file.name}</button></li>)}</ul>
          <form className="space-y-3" onSubmit={event=>{event.preventDefault();const fields=new FormData(event.currentTarget);run(`/customers/${selected}/review`,{artifact_fingerprint:manifest.artifact_fingerprint,decision:'approve',note:fields.get('note'),checks:{identity:fields.has('identity'),files:fields.has('files'),rights:fields.has('rights')}})}}>
            {['identity','files','rights'].map(key=><label key={key} className="flex items-center gap-3 text-sm"><input type="checkbox" name={key} required />Reviewed {key} against this customer's inputs</label>)}
            <label className="block text-sm">Proof review note<textarea name="note" className="input mt-2 w-full" minLength={10} required /></label><div className="flex flex-wrap gap-3"><button className="btn-secondary" disabled={mutation.isPending}>Approve exact private proof</button><button type="button" className="btn-secondary" disabled={mutation.isPending} onClick={event=>{const note=String(new FormData(event.currentTarget.form!).get('note') || 'Rejected the current customer proof; revise the private instance.');run(`/customers/${selected}/review`,{artifact_fingerprint:manifest.artifact_fingerprint,decision:'reject',note,checks:{identity:false,files:false,rights:false}})}}>Reject private proof</button></div>
          </form><button className="btn-secondary" disabled={mutation.isPending || !['approved','exported'].includes(detail.data.status)} onClick={()=>run(`/customers/${selected}/export`)}>Export approved files for manual delivery</button></>}
      </div>}
      {detail.error && <p role="alert" className="text-sm">{detail.error.message}</p>}
      {mutation.error && <p role="alert" className="text-sm">{mutation.error.message}</p>}
      {notice && <p role="status" className="text-sm">{notice}</p>}
    </div>}
  </details>
}
