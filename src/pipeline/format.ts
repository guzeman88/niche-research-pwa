export const number=(v:number|null|undefined)=>v==null||!Number.isFinite(v)?'Unknown':v.toLocaleString('en-US',{maximumFractionDigits:2})

const labels:Record<string,string>={verified:'Listing data',partial:'Partial evidence',unverified:'Not collected',needs_evidence:'Needs evidence',needs_review:'Needs review',needs_attention:'Needs attention',uncalibrated_review_scenario:'Uncalibrated',not_connected:'Not connected',google_supported:'Google supported',provisional_marketplace:'Provisional',passed:'Passed',completed:'Completed',ready_to_test:'Ready to test'}
export const text=(v:string|null|undefined)=>labels[v||'']||(v||'Unknown').replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase())

export const date=(v:string|null|undefined)=>v&&Number.isFinite(Date.parse(v))?new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}).format(new Date(v)):'Not recorded'


export const money=(v:number|null|undefined)=>v==null||!Number.isFinite(v)?'Unknown':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(v)
