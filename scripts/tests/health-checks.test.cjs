const {test}=require('node:test');
const assert=require('node:assert/strict');
test('health checks record all three bounded results and separate warnings from unavailable evidence',async()=>{
 const {sampleHealth,publicHealthRows}=await import('../../netlify/functions/lib/health-checks.mjs');
 const now=Date.parse('2026-11-25T18:00:00Z'),at=new Date(now).toISOString();let recorded;
 const service={rpc:async(name,body)=>{if(name==='app_record_health_checks'){recorded=body.checks;return {error:null}}return {data:{database_bytes:360000000,warning_bytes:350000000}}},from:()=>({select:()=>({eq:()=>({maybeSingle:async()=>({data:{enabled:true,updated_at:at}})})})})};
 const read=async()=>Response.json({schema_version:1,source:'supabase_local',scope:'local_research_projection',id:'a'.repeat(64),generated_at:at,source_data_as_of:at,resources:{'keywords.json':{items:123}}});
 const result=await sampleHealth(service,read,now);
 assert.deepEqual(result.map(r=>r.status),['warning','healthy','healthy']);assert.deepEqual(recorded,result);
 assert.equal(result[0].details.database_bytes,360000000);
 const unavailable=await sampleHealth({...service,rpc:async(name,body)=>name==='app_record_health_checks'?service.rpc(name,body):{error:{message:'PRIVATE PROVIDER TEXT'}}},async()=>new Response('not published',{status:404}),now);
 assert.equal(unavailable[0].status,'unavailable');assert.equal(unavailable[2].status,'unavailable');assert(!JSON.stringify(unavailable).includes('PRIVATE'));
 assert.equal(publicHealthRows([{...result[1],checked_at:'2026-11-25T17:00:00Z'}],now).find(r=>r.id==='private_backend').status,'unavailable');
});
test('native storage reports never advertise an inferred collection maximum or utilization percentage',async()=>{
 const {buildCollectionReport}=await import('../../netlify/functions/lib/collection-report.mjs');
 const report=buildCollectionReport({counts:{etsy_listings_total:12,etsy_observations_total:3,etsy_listings_24h:2,etsy_observations_24h:1},measuredStorage:true,latest:{etsy_open_api:'2026-11-25T12:00:00Z'}});
 const source=report.sources.find(r=>r.id==='etsy_open_api');
 assert.equal(source.total_stored,15);assert.equal(source.stored_24h,3);assert.equal(source.rate.value,null);assert.equal(source.maximum.headline,'Not established');assert.equal(report.target_min_pct,null);assert.equal(report.rate_basis,'observed_storage');
});
