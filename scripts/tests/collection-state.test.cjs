const test = require('node:test');
const assert = require('node:assert/strict');
const {collectionScanStatus, summarizeCollectionStates} = require('../collection-state.cjs');

test('durable collection state drives static snapshot coverage', () => {
  const states = [
    {keyword:'verified', evidence_status:'verified', sources:['etsy_open_api'], last_collected_at:'2026-09-24T12:00:00Z'},
    {keyword:'partial', evidence_status:'partial', sources:['google_trends'], last_collected_at:'2026-09-24T12:00:00Z'},
    {keyword:'empty', evidence_status:'unverified', sources:[], last_collected_at:'2026-09-24T12:00:00Z'},
    {keyword:'failed', evidence_status:'failed', sources:[], last_collected_at:'2026-09-24T12:00:00Z'},
  ];
  assert.deepEqual(summarizeCollectionStates(states, 10, new Date('2026-09-25T00:00:00Z')), {
    attempted:4, successful:2, evidence_backed:1, failed:1, no_data:1, stale:0,
    scanned:4, unscanned:6, coverage_pct:40,
  });
});

test('durable collection state exposes a stable scan status', () => {
  assert.equal(collectionScanStatus({last_collected_at:'2026-09-24', evidence_status:'verified', sources:['etsy']}), 'signals');
  assert.equal(collectionScanStatus({last_collected_at:'2026-09-24', evidence_status:'unverified', sources:[]}), 'no_data');
  assert.equal(collectionScanStatus({last_collected_at:'2026-09-24', evidence_status:'failed', sources:[]}), 'failed');
  assert.equal(collectionScanStatus({}), null);
});
