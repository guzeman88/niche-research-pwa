// Fetches data from the Render backend and saves as static JSON files
// Run before each deploy: node scripts/build-data.cjs
const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

let API = process.env.VITE_API_URL || '';
const OUT = process.env.SNAPSHOT_OUTPUT_DIR || path.join(__dirname, '..', 'public', 'data');
const FALLBACK = path.join(__dirname, '..', 'backend', 'seed_data', 'static');
const MIN_KEYWORD_SNAPSHOT_COUNT = Number(process.env.MIN_KEYWORD_SNAPSHOT_COUNT || 13000);
const MIN_SCORED_KEYWORD_COUNT = Number(process.env.MIN_SCORED_KEYWORD_COUNT || 1000);

loadEnvFiles([
  path.join(__dirname, '..', '.env.local'),
  path.join(__dirname, '..', '.env'),
  path.join(__dirname, '..', '..', '.env.local'),
  path.join(__dirname, '..', '..', '.env'),
]);

API = process.env.VITE_API_URL || '';
const SUPABASE_URL = (process.env.SUPABASE_URL || '').replace(/\/+$/, '');
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || '';

function loadEnvFiles(files) {
  for (const file of files) {
    if (!fs.existsSync(file)) continue;
    const lines = fs.readFileSync(file, 'utf8').split(/\r?\n/);
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) continue;
      const idx = trimmed.indexOf('=');
      const key = trimmed.slice(0, idx).trim();
      let value = trimmed.slice(idx + 1).trim();
      if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1);
      }
      if (!process.env[key]) process.env[key] = value;
    }
  }
}

function fetch(url) {
  return new Promise((resolve, reject) => {
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      reject(new Error(`No API URL configured for ${url}`));
      return;
    }
    const transport = url.startsWith('https') ? https : http;
    transport.get(url, { timeout: 60000, headers: process.env.PIPELINE_API_TOKEN ? {authorization: `Bearer ${process.env.PIPELINE_API_TOKEN}`} : {} }, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        if (res.statusCode < 200 || res.statusCode >= 300) return reject(new Error(`HTTP ${res.statusCode} fetching snapshot`));
        try { resolve(JSON.parse(data)); }
        catch(e) { reject(new Error(`JSON parse failed for ${url}: ${data.slice(0,200)}`)); }
      });
    }).on('timeout', function () { this.destroy(new Error('Snapshot request timed out')); }).on('error', reject);
  });
}

function hasSupabaseSource() {
  return Boolean(SUPABASE_URL && SUPABASE_SERVICE_ROLE_KEY);
}

function supabaseFetch(resource, params = {}) {
  return new Promise((resolve, reject) => {
    if (!hasSupabaseSource()) {
      reject(new Error('Supabase URL/key not configured'));
      return;
    }
    const url = new URL(`${SUPABASE_URL}/rest/v1/${resource}`);
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
    }
    https.get(url, {
      timeout: 60000,
      headers: {
        apikey: SUPABASE_SERVICE_ROLE_KEY,
        authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
      },
    }, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(`Supabase ${resource} failed with ${res.statusCode}: ${data.slice(0, 200)}`));
          return;
        }
        try { resolve(JSON.parse(data || '[]')); }
        catch(e) { reject(new Error(`Supabase JSON parse failed for ${resource}: ${data.slice(0, 200)}`)); }
      });
    }).on('timeout', function () { this.destroy(new Error('Snapshot request timed out')); }).on('error', reject);
  });
}

async function supabaseRows(resource, params = {}, limit = 1000, pageSize = 1000) {
  const rows = [];
  let offset = 0;
  while (rows.length < limit) {
    const batchLimit = Math.min(pageSize, limit - rows.length);
    const batch = await supabaseFetch(resource, { ...params, limit: batchLimit, offset });
    if (!Array.isArray(batch)) throw new Error(`Supabase ${resource} returned ${typeof batch}`);
    rows.push(...batch);
    if (batch.length < batchLimit) break;
    offset += batch.length;
  }
  return rows;
}

function numeric(value, fallback = null) {
  if (value === null || value === undefined || value === '') return fallback;
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function boolish(value) {
  return value === true || value === 1 || value === '1';
}

function byKeyword(rows) {
  return new Map(rows.map((row) => [String(row.keyword || '').toLowerCase(), row]));
}

async function supabaseStats() {
  const statsRows = await supabaseRows('keyword_stats', { select: '*' }, 1, 1);
  const stats = statsRows[0] || {};
  const quality = (await supabaseRows('keyword_research_quality', {select:'*'}, 1, 1))[0] || {};
  const seedDomains = await supabaseRows('keyword_seeds', { select: 'domain' }, Infinity, 1000);
  const domainCounts = new Map();
  for (const row of seedDomains) {
    const domain = row.domain || 'unknown';
    domainCounts.set(domain, (domainCounts.get(domain) || 0) + 1);
  }
  const topGapRows = await supabaseRows(
    'keyword_gap_scores',
    { select: 'keyword,gap_score', order: 'gap_score.desc.nullslast' },
    1,
    1,
  );
  return {
    ...quality,
    total_seeds: numeric(stats.total_seeds, 0),
    scanned: numeric(stats.scanned, 0),
    unscanned: numeric(stats.unscanned, 0),
    total_scans: numeric(stats.total_scans, 0),
    coverage_pct: numeric(stats.coverage_pct, 0),
    avg_opportunity: numeric(stats.avg_opportunity, 0),
    avg_gap_score: numeric(stats.avg_gap_score, 0),
    breakout_count: numeric(stats.breakout_count, 0),
    expansion_edges: numeric(stats.expansion_edges, 0),
    top_gap_keyword: topGapRows[0] ? {
      keyword: topGapRows[0].keyword,
      gap_score: numeric(topGapRows[0].gap_score, 0),
    } : null,
    domains: Array.from(domainCounts.entries())
      .map(([domain, cnt]) => ({ domain, cnt }))
      .sort((a, b) => b.cnt - a.cnt || a.domain.localeCompare(b.domain)),
  };
}

async function supabaseKeywords() {
  const [seeds, scans, gaps] = await Promise.all([
    supabaseRows('keyword_seeds', {
      select: 'keyword,domain,source,priority,added_at',
      order: 'keyword.asc',
    }, Infinity, 1000),
    supabaseRows('keyword_latest_scans', {
      select: 'keyword,scanned_at,opportunity_score,gap_score,trajectory,profitability_index', order: 'keyword.asc',
    }, Infinity, 1000),
    supabaseRows('keyword_gap_scores', {
      select: 'keyword,gap_score,trajectory,breakout_flag', order: 'keyword.asc',
    }, Infinity, 1000),
  ]);
  const scanByKeyword = byKeyword(scans);
  const gapByKeyword = byKeyword(gaps);
  return seeds.map((seed) => {
    const key = String(seed.keyword || '').toLowerCase();
    const scan = scanByKeyword.get(key) || {};
    const gap = gapByKeyword.get(key) || {};
    const primaryScore = numeric(scan.profitability_index ?? scan.opportunity_score ?? scan.gap_score ?? gap.gap_score);
    return {
      keyword: seed.keyword,
      domain: seed.domain || 'unknown',
      source: seed.source || 'library',
      priority: numeric(seed.priority, 5),
      added_at: seed.added_at || '',
      scanned: Boolean(scan.scanned_at),
      last_scanned_at: scan.scanned_at || null,
      primary_score: primaryScore,
      primary_score_source: scan.profitability_index != null ? 'profitability_index'
        : scan.opportunity_score != null ? 'opportunity_score'
        : scan.gap_score != null || gap.gap_score != null ? 'gap_score'
        : null,
      opportunity_score: numeric(scan.opportunity_score),
      gap_score: numeric(gap.gap_score ?? scan.gap_score),
      trajectory: gap.trajectory || scan.trajectory || null,
      breakout: boolish(gap.breakout_flag),
    };
  }).sort((a, b) => {
    if (a.scanned !== b.scanned) return a.scanned ? 1 : -1;
    return numeric(b.gap_score, 0) - numeric(a.gap_score, 0)
      || String(b.last_scanned_at || '').localeCompare(String(a.last_scanned_at || ''));
  });
}

async function supabaseOpportunities(limit = 500) {
  const rows = await supabaseRows('keyword_top_opportunities', {
    select: '*',
    order: 'primary_score.desc.nullslast,keyword.asc',
  }, limit, 1000);
  return rows.map((row) => ({
    ...row,
    breakout_flag: boolish(row.breakout_flag),
    opportunity_score: numeric(row.opportunity_score),
    demand_score: numeric(row.demand_score),
    competition_score: numeric(row.competition_score),
    margin_score: numeric(row.margin_score),
    trend_score: numeric(row.trend_score),
    primary_score: numeric(row.primary_score),
    gap_score: numeric(row.gap_score),
  }));
}

async function supabaseGaps(limit = 500) {
  const rows = await supabaseRows('keyword_gap_reports', {
    select: '*',
    order: 'source_gap_report_id.desc',
  }, Infinity, 1000);
  const latest = new Map();
  for (const row of rows) {
    if (!latest.has(row.keyword)) latest.set(row.keyword, row);
  }
  return Array.from(latest.values())
    .filter((row) => numeric(row.composite_gap_score, 0) >= 0)
    .sort((a, b) => numeric(b.composite_gap_score, 0) - numeric(a.composite_gap_score, 0))
    .slice(0, limit)
    .map((row) => ({
      id: row.source_gap_report_id,
      keyword: row.keyword,
      analyzed_at: row.analyzed_at,
      volume_gap_score: numeric(row.volume_gap_score, 0),
      quality_gap_score: numeric(row.quality_gap_score, 0),
      tag_gap_score: numeric(row.tag_gap_score, 0),
      style_gap_score: numeric(row.style_gap_score, 0),
      price_gap_score: numeric(row.price_gap_score, 0),
      recency_gap_score: numeric(row.recency_gap_score, 0),
      buyer_intent_score: numeric(row.buyer_intent_score, 0),
      profit_gap_score: numeric(row.profit_gap_score, 0),
      composite_gap_score: numeric(row.composite_gap_score, 0),
      entry_angle: row.entry_angle || '',
      recommended_price_min: numeric(row.recommended_price_min, 0),
      recommended_price_max: numeric(row.recommended_price_max, 0),
      untagged_searches_json: row.untagged_searches || [],
      dominant_competitor_tags_json: row.dominant_competitor_tags || [],
      recommended_tags_json: row.recommended_tags || [],
      listings_analyzed: numeric(row.listings_analyzed, 0),
      avg_listing_age_months: numeric(row.avg_listing_age_months, 0),
    }));
}

async function supabaseBreakouts(limit = 100) {
  const rows = await supabaseRows('keyword_gap_scores', {
    select: 'keyword,breakout_flag,gap_score',
    breakout_flag: 'eq.true',
    order: 'gap_score.desc.nullslast',
  }, limit, 1000);
  return rows.map((row) => ({ keyword: row.keyword, breakout: true }));
}

async function supabaseReports(limit = 50) {
  const rows = await supabaseOpportunities(limit);
  return rows.map((row) => ({
    report_id: `${String(row.keyword || '').replace(/[^a-z0-9]+/gi, '-').replace(/^-+|-+$/g, '')}-${String(row.scanned_at || '').slice(0, 10)}`,
    store_slug: '__global__',
    seed_keywords: [row.keyword],
    opportunity_score: numeric(row.opportunity_score),
    primary_score: numeric(row.primary_score),
    primary_score_source: row.primary_score_source,
    demand_score: numeric(row.demand_score, 0),
    competition_score: numeric(row.competition_score, 0),
    margin_score: numeric(row.margin_score, 0),
    trend_velocity_score: numeric(row.trend_score, 0),
    generated_at: row.scanned_at || '',
    sources_used: [],
  }));
}

async function supabaseStoreIdeas(limit = 12) {
  const rows = await supabaseRows('keyword_store_idea_signals', {
    select: '*', order: 'signal_rank.desc,keyword.asc',
  }, 1000, 1000);
  return generateStoreIdeas(rows, limit);
}

function generateStoreIdeas(rows, limit = 12) {
  const candidates = [process.env.PIPELINE_PYTHON,
    path.join(__dirname, '..', '..', 'venv', 'Scripts', 'python.exe'),
    process.platform === 'win32' ? 'python' : 'python3'].filter(Boolean);
  for (const command of candidates) {
    const result = spawnSync(command, [path.join(__dirname, 'generate-store-ideas.py'), String(limit)], {
      input: JSON.stringify(rows), encoding: 'utf8', maxBuffer: 20 * 1024 * 1024,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    });
    if (result.error?.code === 'ENOENT') continue;
    if (result.status !== 0) throw new Error(`Store generator failed: ${result.stderr}`);
    return JSON.parse(result.stdout);
  }
  throw new Error('Python is required for the shared recommendation generator. Set PIPELINE_PYTHON.');
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const endpoints = [
    ['stats.json', '/api/stats'], ['opportunities.json', '/api/keywords/opportunities?limit=500'],
    ['store-ideas.json', '/api/store-ideas/profitable?limit=12&signal_limit=1000'],
    ['gaps.json', '/api/gaps?limit=500'], ['keywords.json', '/api/keywords?limit=25000'],
    ['breakouts.json', '/api/keywords/breakouts?limit=100'], ['reports.json', '/api/research/reports?limit=50'],
  ];
  if (process.env.REQUIRE_SUPABASE === '1' && !hasSupabaseSource()) {
    throw new Error('This release requires Supabase build credentials.');
  }
  const source = hasSupabaseSource() ? 'supabase' : API ? 'api' : 'bundled';
  const snapshots = {};
  for (const [filename, endpoint] of endpoints) {
    // Never combine new and fallback snapshots in one release.
    const data = source === 'supabase' ? await generateSupabaseSnapshot(filename)
      : source === 'api' ? await fetch(`${API}${endpoint}`)
      : JSON.parse(fs.readFileSync(path.join(FALLBACK, filename), 'utf8'));
    snapshots[filename] = data;
  }
  if (snapshots['keywords.json'].length !== Number(snapshots['stats.json'].total_seeds)) {
    throw new Error('Keyword rows do not match the snapshot statistics.');
  }
  const { validateStoreIdeas } = require('./snapshot-contract.cjs');
  validateStoreIdeas(snapshots['store-ideas.json']);
  for (const [filename, data] of Object.entries(snapshots)) {
    const target = path.join(OUT, filename);
    fs.writeFileSync(target + '.tmp', JSON.stringify(data));
    fs.renameSync(target + '.tmp', target);
    console.log(`${filename}: ${Array.isArray(data) ? data.length : Object.keys(data).length} entries`);
  }
  const { execFileSync } = require('child_process');
  const { createHash } = require('crypto');
  const files = Object.fromEntries(Object.keys(snapshots).map(name => [name,
    createHash('sha256').update(fs.readFileSync(path.join(OUT, name))).digest('hex')]));
  fs.writeFileSync(path.join(OUT, 'release.json'), JSON.stringify({
    schema_version: 1, source, pipeline_commit: process.env.PIPELINE_COMMIT || null, generated_at: new Date().toISOString(),
    commit: execFileSync('git', ['rev-parse', 'HEAD'], {cwd:path.join(__dirname,'..'),encoding:'utf8'}).trim(), files,
  }, null, 2));
})().catch(error => { console.error(error.message); process.exitCode = 1; });

async function generateSupabaseSnapshot(filename) {
  switch (filename) {
    case 'stats.json':
      return supabaseStats();
    case 'opportunities.json':
      return supabaseOpportunities(500);
    case 'store-ideas.json':
      return supabaseStoreIdeas(12);
    case 'gaps.json':
      return supabaseGaps(500);
    case 'keywords.json':
      return supabaseKeywords();
    case 'breakouts.json':
      return supabaseBreakouts(100);
    case 'reports.json':
      return supabaseReports(50);
    default:
      throw new Error(`No Supabase snapshot generator for ${filename}`);
  }
}
