// Only this small, service-only projection may cross the startup boundary.
export function normalizeStartup(value) {
  if (!value || value.schema_version !== 1 || !Number.isFinite(Date.parse(value.generated_at)) || !value.input_fingerprint) throw new Error('Invalid startup report.');
  const result={schema_version:1,generated_at:value.generated_at,input_fingerprint:value.input_fingerprint};
  for(const [part,key,max] of [['projects','projects',50],['production','jobs',24]]) {
    const source=value[part];
    if(source?.status==='unavailable'){result[part]={status:'unavailable',[key]:null,total:null,error:'Saved '+part+' could not be read. Retry the connection.'};continue;}
    if(source?.status!=='ready'||!Array.isArray(source[key])||source[key].length>max||!Number.isSafeInteger(source.total)||source.total<source[key].length||typeof source.has_more!=='boolean'||source.has_more!==(source.total>source[key].length))throw new Error('Invalid startup counts.');
    const seen=new Set();
    const items=source[key].map(row=>{
      if(typeof row.id!=='string'||!row.id||seen.has(row.id)||!Number.isFinite(Date.parse(row.updated_at)))throw new Error('Invalid startup item.');
      seen.add(row.id);
      if(part==='projects'){
        if(typeof row.name!=='string'||row.name.length>1000)throw new Error('Invalid project name.');
        return {id:row.id,name:row.name,product_type:row.product_type,updated_at:row.updated_at};
      }
      if(!row.spec||typeof row.spec.name!=='string'||row.spec.name.length>1000||typeof row.spec.family!=='string'||typeof row.product_id!=='string'||typeof row.revision!=='string'||typeof row.status!=='string'||typeof row.has_preview!=='boolean')throw new Error('Invalid production item.');
      return {id:row.id,product_id:row.product_id,revision:row.revision,status:row.status,updated_at:row.updated_at,spec:{name:row.spec.name,family:row.spec.family},has_preview:row.has_preview};
    });
    result[part]={status:'ready',[key]:items,total:source.total,has_more:source.has_more,...(part==='production'?{paused:Boolean(source.paused),human_approval_required:true}:{})};
  }
  if(Buffer.byteLength(JSON.stringify(result))>96*1024)throw new Error('Startup report is too large.');
  return result;
}

export async function bootstrapData({user,profile,mfa,recovery,workspace=true,readWorkspace,readReport}) {
  const session={user:{id:user.id,email:user.email},profile:mfa?null:profile,mfa_required:mfa,recovery:Boolean(recovery),factors:(user.factors||[]).filter(f=>f.status==='verified').map(f=>({id:f.id,friendly_name:f.friendly_name}))};
  // Incomplete authentication must never release workspace or operator data.
  if(mfa||recovery)return session;
  const [saved,report]=await Promise.all([
    workspace?readWorkspace(user.id):Promise.resolve(undefined),
    profile.role==='admin'?readReport().catch(()=>null):Promise.resolve(null),
  ]);
  return {...session,...(saved?{workspace:saved}:{}),...(report?{dashboard:report,startup:report.startup}:{} )};
}
