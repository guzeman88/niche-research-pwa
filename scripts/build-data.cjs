// Fetches data from the Render backend and saves as static JSON files
// Run before each deploy: node scripts/build-data.cjs
const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');

const API = process.env.VITE_API_URL || 'https://niche-research-api-kqlt.onrender.com';
const OUT = path.join(__dirname, '..', 'public', 'data');
const MIN_KEYWORD_SNAPSHOT_COUNT = Number(process.env.MIN_KEYWORD_SNAPSHOT_COUNT || 13000);

function fetch(url) {
  return new Promise((resolve, reject) => {
    const transport = url.startsWith('https') ? https : http;
    transport.get(url, { timeout: 60000 }, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch(e) { reject(new Error(`JSON parse failed for ${url}: ${data.slice(0,200)}`)); }
      });
    }).on('error', reject);
  });
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  console.log(`Fetching static data snapshots from ${API}...`);

  const endpoints = [
    ['stats.json', '/api/stats'],
    ['opportunities.json', '/api/keywords/opportunities?limit=500'],
    ['gaps.json', '/api/gaps?limit=500'],
    ['keywords.json', '/api/keywords?limit=15000'],
    ['breakouts.json', '/api/keywords/breakouts?limit=100'],
    ['reports.json', '/api/research/reports?limit=50'],
  ];

  let failed = false;

  for (const [filename, endpoint] of endpoints) {
    try {
      const data = await fetch(`${API}${endpoint}`);
      if (filename === 'keywords.json' && Array.isArray(data) && data.length < MIN_KEYWORD_SNAPSHOT_COUNT) {
        throw new Error(`keyword snapshot only has ${data.length} rows; expected at least ${MIN_KEYWORD_SNAPSHOT_COUNT}`);
      }
      const filepath = path.join(OUT, filename);
      fs.writeFileSync(filepath, JSON.stringify(data));
      const kb = (fs.statSync(filepath).size / 1024).toFixed(1);
      console.log(`  ${filename}: ${Array.isArray(data) ? data.length : Object.keys(data).length} entries (${kb} KB)`);
    } catch (e) {
      console.error(`  ${filename}: FAILED - ${e.message}`);
      failed = true;
    }
  }

  if (failed) {
    process.exitCode = 1;
    return;
  }

  console.log('Done.');
})();
