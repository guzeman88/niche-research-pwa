import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { artifactBlob, downloadArtifact, productionRequest, type ProductionJob, type ProductionSpec } from '../lib/production'

const checks = ['wording', 'usefulness', 'visual_quality', 'rights', 'files', 'mockups', 'facts']
export default function ProductionJobReview({job, refresh, revise}: {job: ProductionJob; refresh: () => void; revise: (spec: ProductionSpec) => void}) {
  const [preview, setPreview] = useState(''); const [previewError, setPreviewError] = useState('')
  const [assessment, setAssessment] = useState('')
  const artifactHash = job.result?.manifest?.artifact_fingerprint
  useEffect(() => {
    let active = true; let url = ''; setPreview(''); setPreviewError('')
    if (artifactHash) artifactBlob(job.id, 'preview.png').then(blob => {
      url = URL.createObjectURL(blob); if (active) setPreview(url); else URL.revokeObjectURL(url)
    }).catch(error => {if (active) setPreviewError(error.message)})
    return () => {active = false; if (url) URL.revokeObjectURL(url)}
  }, [job.id, artifactHash])
  const operation = useMutation({mutationFn: ({path, body}: {path: string; body: unknown}) => productionRequest(path, body),
    onSuccess: result => {setAssessment(JSON.stringify(result, null, 2)); refresh()}})
  const run = (path: string, body: unknown = {}) => operation.mutate({path: `/jobs/${job.id}${path}`, body})
  const result = job.result
  return <article className="mt-5 border-t border-surface-600 pt-5">
    <div className="flex flex-wrap items-baseline gap-3"><h3 className="text-lg font-semibold">{job.spec.name}</h3><span className="text-sm text-surface-200">{job.status.replace(/_/g, ' ')}</span></div>
    <p className="mt-2 max-w-prose text-sm text-surface-200">{job.spec.purpose}</p>
    <p className="mt-2 text-xs text-surface-200">Demand: {String(job.spec.research.status || 'unvalidated operator concept')} · Manufacturing: {result?.quality?.manufacturing || 'not assessed'}</p>
    {job.error && <p role="alert" className="mt-3 text-sm">{job.error}</p>}
    <div className="mt-4 flex flex-wrap gap-3">
      <button className="btn-secondary" onClick={() => revise(job.spec)}>Revise specification</button>
      {['failed', 'needs_input', 'cancelled'].includes(job.status) && <button className="btn-secondary" disabled={operation.isPending} onClick={() => run('/action', {action: 'retry'})}>Retry saved job</button>}
      {['queued', 'failed', 'needs_input'].includes(job.status) && <button className="btn-secondary" onClick={() => run('/action', {action: 'cancel'})}>Cancel pending job</button>}
    </div>
    {result?.concepts && <div className="mt-5 space-y-4">{result.concepts.concepts.map((concept, index) => <div key={index} className="border-l-2 border-surface-500 pl-4">
      <h4 className="font-semibold">{concept.name}</h4><p className="mt-2 max-w-prose text-sm">{concept.purpose}</p><p className="mt-2 text-sm text-surface-200">{concept.composition}</p>
      <button className="btn-secondary mt-3" onClick={() => revise({...job.spec, purpose: concept.purpose, content: concept.content, concept_method: 'authored'})}>Review and use this concept</button>
    </div>)}</div>}
    {result?.manifest && <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div>{preview && <img className="max-h-[32rem] w-full rounded bg-white object-contain" src={preview} alt={`Actual generated layout for ${job.spec.name}`} />}
        {previewError && <p role="alert">{previewError}</p>}
        <p className="mt-3 text-xs text-surface-200">{result.manifest.render.preview_kind.replace(/_/g, ' ')}. Inspect customer files before approval.</p>
        <ul className="mt-4 space-y-2">{result.manifest.files.map(file => <li key={file.name}><button className="text-sm underline underline-offset-4" onClick={() => downloadArtifact(job.id, file.name).catch(error => setPreviewError(error.message))}>Download review copy: {file.name}</button><span className="ml-2 text-xs text-surface-200">{Math.ceil(file.bytes / 1024)} KB</span></li>)}</ul>
      </div>
      <div><h4 className="font-semibold">Actual file checks</h4><ul className="mt-3 space-y-2 text-sm">{result.quality?.checks.map(check => <li key={check.check}>{check.passed ? 'Pass' : 'Fail'} · {check.check.replace(/_/g, ' ')}</li>)}</ul>
        <h4 className="mt-5 font-semibold">Listing readiness</h4><ul className="mt-3 space-y-2 text-sm">{result.listing?.blockers.length ? result.listing.blockers.map(item => <li key={item}>{item}</li>) : <li>Facts complete. Human review still required.</li>}</ul>
        <details className="mt-4"><summary className="cursor-pointer text-sm">Generated listing copy</summary><p className="mt-3 whitespace-pre-wrap text-sm">{result.listing?.description}</p><p className="mt-3 text-sm">Tags: {result.listing?.tags.join(', ')}</p></details>
        <div className="mt-5 flex flex-wrap gap-3"><button className="btn-secondary" disabled={operation.isPending} onClick={() => run('/assess', {vision: false})}>Run OCR assessment</button><button className="btn-secondary" disabled={operation.isPending} onClick={() => run('/assess', {vision: true})}>Run local visual critique</button></div>
      </div>
    </div>}
    {job.status === 'needs_review' && result?.manifest && <form className="mt-6 max-w-2xl" aria-label="Review production files" onSubmit={event => {
      event.preventDefault(); const data = new FormData(event.currentTarget)
      run('/review', {revision: job.revision, artifact_fingerprint: result.manifest!.artifact_fingerprint,
        decision: data.get('decision'), note: data.get('note'), checks: Object.fromEntries(checks.map(key => [key, data.has(key)]))})
    }}>
      <fieldset><legend className="font-semibold">Review the exact revision</legend><div className="mt-3 grid gap-3 sm:grid-cols-2">{checks.map(key => <label key={key} className="flex items-center gap-3 text-sm"><input type="checkbox" name={key} />{key.replace(/_/g, ' ')}</label>)}</div></fieldset>
      <label className="mt-4 block text-sm">Review note<textarea name="note" required minLength={10} className="input mt-2 w-full" /></label>
      <div className="mt-4 flex flex-wrap gap-3"><button className="btn-primary" name="decision" value="approve" disabled={operation.isPending} onClick={event => {event.currentTarget.form?.querySelector<HTMLInputElement>('input[name="decision"]')?.setAttribute('value', 'approve')}}>Approve exact package</button>
        <button className="btn-secondary" type="button" onClick={() => run('/review', {revision: job.revision, artifact_fingerprint: result.manifest!.artifact_fingerprint, decision: 'reject', note: 'Rejected after inspecting the actual files; create a revised specification.', checks: {}})}>Reject and preserve revision</button><input type="hidden" name="decision" value="approve" /></div>
    </form>}
    {['approved', 'exported'].includes(job.status) && <div className="mt-5 flex flex-wrap gap-3"><button className="btn-primary" onClick={() => run('/export')}>Export approved package</button><button className="btn-secondary" onClick={() => run('/etsy-draft')}>Create Etsy draft</button></div>}
    {['mug', 'apparel'].includes(job.spec.family) && result?.manifest && <button className="btn-secondary mt-5" onClick={() => run('/mockups')}>Create unpublished provider mockups</button>}
    {operation.error && <p className="mt-3 text-sm" role="alert">{(operation.error as Error).message}</p>}
    {assessment && <details className="mt-4"><summary className="cursor-pointer text-sm">Last operation result</summary><pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">{assessment}</pre></details>}
    <details className="mt-5"><summary className="cursor-pointer text-sm">Revision and operation history</summary><p className="mt-2 break-all text-xs text-surface-200">{job.revision}</p><ul className="mt-3 space-y-2 text-xs">{job.history.map((item, i) => <li key={i}>{item.action.replace(/_/g, ' ')} · {new Date(item.created_at).toLocaleString()}</li>)}</ul></details>
  </article>
}
