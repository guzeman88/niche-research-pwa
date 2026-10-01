const test = require('node:test');
const assert = require('node:assert/strict');
const { latestGoogleVolumes } = require('../google-volume.cjs');

test('keeps the newest valid Google monthly volume, including zero', () => {
  const volumes = latestGoogleVolumes([
    { keyword: 'Teacher Mug', value: 2400, observed_at: '2026-09-01' },
    { keyword: 'teacher mug', value: 3100, observed_at: '2026-10-01' },
    { keyword: 'zero search', value: 0, observed_at: '2026-10-01' },
    { keyword: 'bad row', value: null, observed_at: '2026-10-01' },
  ]);

  assert.deepEqual(volumes.get('teacher mug'), { value: 3100, observedAt: '2026-10-01' });
  assert.deepEqual(volumes.get('zero search'), { value: 0, observedAt: '2026-10-01' });
  assert.equal(volumes.has('bad row'), false);
});
