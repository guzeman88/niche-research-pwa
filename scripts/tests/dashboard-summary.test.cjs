const test = require('node:test');
const assert = require('node:assert/strict');

test('dashboard snapshot normalizer preserves an atomic version and delivery policy', async () => {
  const { normalizeDashboardSnapshot, dashboardEtag } = await import('../../netlify/functions/lib/dashboard-summary.mjs');
  const row = {
    snapshot_version: 42,
    generated_at: '2026-09-26T21:00:00Z',
    data_status: 'healthy',
    input_fingerprint: 'abcdef0123456789',
    source_watermarks: { observations_at: '2026-09-26T20:59:00Z' },
    duration_ms: 18,
    payload: {
      schema_version: 1,
      stats: { total_seeds: 30588, scanned: 3251 },
      evidence: { versioned_scores: 0 },
      providers: [],
    },
  };
  const summary = normalizeDashboardSnapshot(row);
  assert.equal(summary.snapshot_version, 42);
  assert.equal(summary.stats.total_seeds, 30588);
  assert.deepEqual(summary.delivery, { mode: 'live', refresh_interval_seconds: 60 });
  assert.equal(dashboardEtag(row), 'W/\"dashboard-42-abcdef012345\"');
});

test('dashboard snapshot normalizer rejects incomplete payloads', async () => {
  const { normalizeDashboardSnapshot } = await import('../../netlify/functions/lib/dashboard-summary.mjs');
  assert.throws(() => normalizeDashboardSnapshot({ payload: {} }), /incomplete/);
  assert.throws(() => normalizeDashboardSnapshot(null), /unavailable/);
});


test('operational reports reject mixed versions, unknown counts and impossible scopes',async()=>{
 const {normalizeOperationalSnapshot}=await import('../../netlify/functions/lib/dashboard-summary.mjs');
 const at=Date.now(),stamp=new Date(at).toISOString();const row={snapshot_version:12,generated_at:stamp,input_fingerprint:'fixture',payload:{schema_version:2,snapshot_version:12,generated_at:stamp,input_fingerprint:'fixture',stats:{total_seeds:10,scanned:3},evidence:{versioned_scores:null}}};
 assert.equal(normalizeOperationalSnapshot(row,at).evidence.versioned_scores,null);
 assert.equal(normalizeOperationalSnapshot({...row,generated_at:new Date(at-200000).toISOString(),payload:{...row.payload,generated_at:new Date(at-200000).toISOString()}},at).delivery.stale,true);
 for(const invalid of [null,'10',-1,1.5])assert.throws(()=>normalizeOperationalSnapshot({...row,payload:{...row.payload,stats:{total_seeds:invalid}}},at));
 assert.throws(()=>normalizeOperationalSnapshot({...row,payload:{...row.payload,snapshot_version:13}},at),/versions/);
 assert.throws(()=>normalizeOperationalSnapshot({...row,payload:{...row.payload,input_fingerprint:'other'}},at),/fingerprints/);
 assert.throws(()=>normalizeOperationalSnapshot({...row,payload:{...row.payload,stats:{total_seeds:2,scanned:3}}},at),/scopes/);
});
