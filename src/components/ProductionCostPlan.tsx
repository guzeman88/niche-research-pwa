import {useState} from 'react'
import {useMutation} from '@tanstack/react-query'
import {productionRequest,type CostPlan,type CostSummary} from '../lib/production'
import {costPlanFields as fields,costPlanFromForm} from '../lib/costPlan'

const usd=(value:number)=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(value)
export function CostPlanSummary({summary}:{summary:CostSummary}) {
  return <section aria-label="Provisional cost summary" className="mt-5 space-y-3 border-y border-surface-600 py-5">
    <h4 className="font-semibold">Provisional cost plan</h4>
    <p className="max-w-prose text-sm text-surface-200">Calculated at a selling price of {usd(summary.selling_price)} using planning assumptions. Actual total costs and profit remain unverified.</p>
    <dl className="grid gap-4 sm:grid-cols-2"><div><dt className="text-sm text-surface-200">Estimated variable cost</dt><dd className="mt-1 font-semibold tabular-nums">{usd(summary.total_variable_cost)}</dd></div><div><dt className="text-sm text-surface-200">Planned contribution per sale</dt><dd className="mt-1 font-semibold tabular-nums">{usd(summary.contribution)}</dd></div></dl>
    <details><summary className="cursor-pointer text-sm">Review assumptions and fee basis</summary><div className="mt-3 space-y-3 text-sm">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2"><dt>Base Etsy fees</dt><dd className="tabular-nums">{usd(summary.platform_fees)}</dd><dt>Support allowance</dt><dd className="tabular-nums">{usd(summary.support_labor)}</dd><dt>Refund allowance</dt><dd className="tabular-nums">{usd(summary.refund_allowance)}</dd><dt>Attributed-order advertising fee</dt><dd className="tabular-nums">{usd(summary.offsite_fee)}</dd></dl>
      <p>{summary.assumptions_note}</p><p>Support: {summary.assumptions.support_contact_fraction*100}% of orders × {summary.assumptions.support_minutes_per_contact} minutes × {usd(summary.assumptions.hourly_labor_usd)} per hour. Refund reserve: {summary.assumptions.refund_revenue_fraction*100}%.</p>
      <p>Advertising fees apply to attributed orders. Zero tax or other-cost inputs are assumptions, not verified exemptions. Fixed development costs and income taxes are separate.</p>
      <p className="text-surface-200">Fee schedule: {summary.fee_schedule_id}. {summary.fee_sources.map((url,i)=><a key={url} className="mr-3 underline underline-offset-4" href={url} target="_blank" rel="noreferrer">Fee source {i+1}</a>)}</p>
    </div></details>
  </section>
}
export default function ProductionCostPlan({initial,enabled,toggle}:{initial?:CostPlan|null;enabled:boolean;toggle:(value:boolean)=>void}) {
  const [error,setError]=useState('')
  const preview=useMutation({mutationFn:(body:unknown)=>productionRequest<CostSummary>('/cost-plan/preview',body)})
  return <fieldset className="space-y-4 border-y border-surface-600 py-5" onChange={()=>{preview.reset();setError('')}}>
    <legend className="font-semibold">Cost basis</legend>
    <label className="flex items-start gap-3 text-sm"><input type="checkbox" checked={enabled} onChange={event=>toggle(event.target.checked)}/>Use a provisional cost plan for this US digital download</label>
    {enabled&&<><p className="max-w-prose text-sm text-surface-200">Editable examples are not seller averages. Actual costs stay unknown. Acknowledge the plan at the final exact-product review.</p>
      <div className="grid gap-4 sm:grid-cols-2">{fields.map(field=><label className="min-w-0 text-sm" key={field.key}>{field.label}<input className="input mt-2 w-full" name={'cp_'+field.key} type="number" min="0" max={field.max} step="any" required defaultValue={initial?Number(initial[field.key])*(field.percent?100:1):field.example}/></label>)}
      <label className="text-sm">Offsite advertising fee case<select className="input mt-2 w-full" name="cp_offsite_fee_fraction" defaultValue={initial?.offsite_fee_fraction??0}><option value="0">No attributed ad fee · assumption</option><option value="0.12">12% on an attributed order</option><option value="0.15">15% on an attributed order</option></select></label></div>
      <label className="block text-sm">Explain the planning assumptions<textarea className="input mt-2 w-full" name="cp_assumptions_note" required minLength={20} maxLength={1200} defaultValue={initial?.assumptions_note||'Planning assumptions for a new product. Support and refund allowances are not measured history; zero tax and other-cost inputs are scenario assumptions.'}/></label>
      <button type="button" className="btn-secondary" disabled={preview.isPending} onClick={event=>{try{const data=Object.fromEntries(new FormData(event.currentTarget.form!)) as Record<string,string>;if(!data.price)throw new Error('Enter the selling price first.');preview.mutate({price:Number(data.price),cost_plan:costPlanFromForm(data)})}catch(e){setError(e instanceof Error?e.message:'Check the planning inputs.')}}}>{preview.isPending?'Calculating…':'Calculate provisional costs'}</button>
      {(error||preview.error)&&<p role="alert" className="text-sm">{error||preview.error?.message}</p>}
      {preview.data&&<CostPlanSummary summary={preview.data}/>}
    </>}
  </fieldset>
}
