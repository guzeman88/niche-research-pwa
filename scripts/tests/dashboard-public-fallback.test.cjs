const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
test('dashboard fallback uses the current verified family and its date while retaining existing live reports',async()=>{
 const exports={},failure=new Error('private unavailable');let reads=0;
 const context={exports,Date,Error,fetch:()=>{throw new Error('Must not read the older compatibility archive')},require:name=>name==='./accountApi'?{accountRequest:async()=>{throw failure}}:{readPublicResearchWithMetadata:async()=>{reads++;return {data:{total_seeds:123},manifest:{id:'a'.repeat(64),source_data_as_of:'2026-11-25T12:00:00Z',generated_at:'2026-11-25T12:05:00Z'}}}}};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/lib/dashboardSummary.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,context);
 const result=await exports.getDashboardSummary();assert.equal(result.stats.total_seeds,123);assert.equal(result.scope,'local_research_projection');assert.equal(result.generated_at,'2026-11-25T12:00:00Z');assert.equal(result.snapshot_version,'a'.repeat(64));assert.equal(result.evidence.versioned_scores,null);
 await assert.rejects(()=>exports.getDashboardSummary({client:{getQueryData:()=>({delivery:{mode:'live'}})},queryKey:['dashboard-summary']}),error=>error===failure);assert.equal(reads,1);
});
