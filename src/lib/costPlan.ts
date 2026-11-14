import type {CostPlan} from './production'

export const costPlanFields:Array<{key:keyof CostPlan;label:string;example:number;percent?:boolean;max:number}>=[
  {key:'support_contact_fraction',label:'Orders needing help · %',example:15,percent:true,max:100},
  {key:'support_minutes_per_contact',label:'Minutes per help request',example:10,max:600},
  {key:'hourly_labor_usd',label:'Value of your time · USD per hour',example:25,max:10000},
  {key:'refund_revenue_fraction',label:'Refund allowance · % of revenue',example:3,percent:true,max:100},
  {key:'buyer_tax_usd',label:'Buyer sales tax per order · USD',example:0,max:100000},
  {key:'tax_on_seller_fees_usd',label:'Tax on seller fees · USD',example:0,max:100000},
  {key:'other_variable_usd',label:'Other variable cost per order · USD',example:0,max:100000},
]
export function costPlanFromForm(data:Record<string,string>):CostPlan {
  const result:Record<string,unknown>={country:'US',currency:'USD',fee_schedule_id:'etsy-us-2026-11-13',assumptions_note:data.cp_assumptions_note}
  for(const field of costPlanFields){const raw=data['cp_'+field.key];if(raw===undefined||raw.trim()===''||!Number.isFinite(Number(raw)))throw new Error('Complete every provisional cost input; missing amounts cannot be zero.');result[field.key]=Number(raw)/(field.percent?100:1)}
  if(!['0','0.12','0.15'].includes(data.cp_offsite_fee_fraction))throw new Error('Choose the advertising fee case.')
  result.offsite_fee_fraction=Number(data.cp_offsite_fee_fraction)
  return result as unknown as CostPlan
}
