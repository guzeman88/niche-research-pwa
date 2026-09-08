// Verify the actual deployed bytes against the manifest produced by this build.
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { isDeepStrictEqual } = require('node:util');

async function verifyRelease(baseUrl, directory = path.join(__dirname, '..', 'dist', 'data')) {
  const local = JSON.parse(fs.readFileSync(path.join(directory, 'release.json'), 'utf8'));
  if (local.source !== 'supabase' || !local.commit || Object.keys(local.files || {}).length !== 7) {
    throw new Error('Missing production source metadata');
  }
  async function read(name) {
    const response = await fetch(`${baseUrl.replace(/\/$/, '')}/data/${name}?verify=${Date.now()}`, {
      signal: AbortSignal.timeout(30000), cache: 'no-store',
    });
    if (!response.ok) throw new Error(`${name}: HTTP ${response.status}`);
    return Buffer.from(await response.arrayBuffer());
  }
  const live = JSON.parse((await read('release.json')).toString('utf8'));
  if (!isDeepStrictEqual(live, local)) throw new Error('Live release differs from this build');
  for (const [name, expected] of Object.entries(local.files)) {
    const actual = createHash('sha256').update(await read(name)).digest('hex');
    if (actual !== expected) throw new Error(`Live snapshot hash mismatch: ${name}`);
  }
  console.log(`Verified seven live snapshot files at commit ${local.commit}`);
}

if (require.main === module) {
  verifyRelease(process.argv[2] || 'https://etsy-niches.netlify.app').catch(error => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
module.exports = { verifyRelease };
