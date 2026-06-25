// Fetches data from the Render backend and saves as static JSON files
// Run before each deploy: node scripts/build-data.cjs
const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');

const API = process.env.VITE_API_URL || 'https://niche-research-api-kqlt.onrender.com';
const OUT = path.join(__dirname, '..', 'public', 'data');
const FALLBACK = path.join(__dirname, '..', 'backend', 'seed_data', 'static');
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
    ['store-ideas.json', '/api/store-ideas/profitable?limit=12&signal_limit=1000'],
    ['gaps.json', '/api/gaps?limit=500'],
    ['keywords.json', '/api/keywords?limit=15000'],
    ['breakouts.json', '/api/keywords/breakouts?limit=100'],
    ['reports.json', '/api/research/reports?limit=50'],
  ];

  let failed = false;
  let useSeedFallback = false;

  function readFallback(filename) {
    const filepath = path.join(FALLBACK, filename);
    if (!fs.existsSync(filepath)) return null;
    return JSON.parse(fs.readFileSync(filepath, 'utf8'));
  }

  function readExistingSnapshot(filename) {
    const filepath = path.join(OUT, filename);
    if (!fs.existsSync(filepath)) return null;
    return JSON.parse(fs.readFileSync(filepath, 'utf8'));
  }

  for (const [filename, endpoint] of endpoints) {
    try {
      let data = await fetch(`${API}${endpoint}`);
      if (filename === 'store-ideas.json' && !Array.isArray(data)) {
        throw new Error(`store ideas snapshot expected an array, got ${typeof data}`);
      }
      if (filename === 'store-ideas.json' && Array.isArray(data) && data.length === 0) {
        console.warn(`  ${filename}: backend returned 0 ideas; writing empty snapshot`);
      }
      if (filename === 'stats.json' && data && data.total_seeds < MIN_KEYWORD_SNAPSHOT_COUNT) {
        useSeedFallback = true;
        const fallback = readFallback(filename);
        if (!fallback || fallback.total_seeds < MIN_KEYWORD_SNAPSHOT_COUNT) {
          throw new Error(`stats snapshot only reports ${data.total_seeds} keywords; fallback is missing or too small`);
        }
        console.warn(`  ${filename}: backend only reports ${data.total_seeds} keywords; using seed snapshot stats`);
        data = fallback;
      } else if (useSeedFallback) {
        const fallback = readFallback(filename);
        if (fallback) {
          console.warn(`  ${filename}: using seed snapshot because backend stats are undersized`);
          data = fallback;
        }
      }
      if (filename === 'keywords.json' && Array.isArray(data) && data.length < MIN_KEYWORD_SNAPSHOT_COUNT) {
        const fallback = readFallback(filename);
        if (!Array.isArray(fallback) || fallback.length < MIN_KEYWORD_SNAPSHOT_COUNT) {
          throw new Error(`keyword snapshot only has ${data.length} rows; fallback is missing or too small`);
        }
        console.warn(`  ${filename}: backend only returned ${data.length}; using ${fallback.length}-row seed snapshot`);
        data = fallback;
      }
      const filepath = path.join(OUT, filename);
      fs.writeFileSync(filepath, JSON.stringify(data));
      const kb = (fs.statSync(filepath).size / 1024).toFixed(1);
      console.log(`  ${filename}: ${Array.isArray(data) ? data.length : Object.keys(data).length} entries (${kb} KB)`);
    } catch (e) {
      const fallback = filename === 'store-ideas.json'
        ? null
        : (readFallback(filename) || readExistingSnapshot(filename));
      if (fallback) {
        const filepath = path.join(OUT, filename);
        fs.writeFileSync(filepath, JSON.stringify(fallback));
        const kb = (fs.statSync(filepath).size / 1024).toFixed(1);
        console.warn(`  ${filename}: using seed snapshot fallback after fetch failure - ${e.message}`);
        console.log(`  ${filename}: ${Array.isArray(fallback) ? fallback.length : Object.keys(fallback).length} entries (${kb} KB)`);
      } else {
        if (filename === 'store-ideas.json' || filename === 'reports.json') {
          const filepath = path.join(OUT, filename);
          fs.writeFileSync(filepath, JSON.stringify([]));
          console.warn(`  ${filename}: endpoint unavailable, writing empty snapshot - ${e.message}`);
          console.log(`  ${filename}: 0 entries (2 bytes)`);
          continue;
        }
        console.error(`  ${filename}: FAILED - ${e.message}`);
        failed = true;
      }
    }
  }

  if (failed) {
    process.exitCode = 1;
    return;
  }

  console.log('Done.');
})();
