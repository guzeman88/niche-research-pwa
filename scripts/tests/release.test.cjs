const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { verifyRelease } = require('../verify-release.cjs');

test('release verification rejects stale metadata and corrupted live data', async (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'etgen-release-test-'));
  const content = Buffer.from('[]');
  const digest = createHash('sha256').update(content).digest('hex');
  const files = Object.fromEntries(['stats', 'keywords', 'opportunities', 'store-ideas', 'gaps', 'breakouts', 'reports']
    .map(name => [`${name}.json`, digest]));
  const manifest = { source: 'supabase', commit: 'verified-source', files };
  fs.writeFileSync(path.join(directory, 'release.json'), JSON.stringify(manifest));
  let stale = false, corrupted = false;
  t.mock.method(globalThis, 'fetch', async url => new Response(
    url.includes('/release.json') ? JSON.stringify({ ...manifest, commit: stale ? 'older-source' : manifest.commit })
      : corrupted ? '[1]' : content,
  ));
  await verifyRelease('https://example.test', directory);
  stale = true;
  await assert.rejects(verifyRelease('https://example.test', directory), /differs/);
  stale = false; corrupted = true;
  await assert.rejects(verifyRelease('https://example.test', directory), /hash mismatch/);
  fs.unlinkSync(path.join(directory, 'release.json'));
  fs.rmdirSync(directory);
});
