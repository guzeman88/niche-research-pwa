// Fetches data from the Render backend and saves as static JSON files
// Run before each deploy: node scripts/build-data.cjs
const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const API = process.env.VITE_API_URL || '';
const OUT = path.join(__dirname, '..', 'public', 'data');
const FALLBACK = path.join(__dirname, '..', 'backend', 'seed_data', 'static');
const MIN_KEYWORD_SNAPSHOT_COUNT = Number(process.env.MIN_KEYWORD_SNAPSHOT_COUNT || 13000);
const MIN_SCORED_KEYWORD_COUNT = Number(process.env.MIN_SCORED_KEYWORD_COUNT || 1000);

loadEnvFiles([
  path.join(__dirname, '..', '.env.local'),
  path.join(__dirname, '..', '.env'),
  path.join(__dirname, '..', '..', '.env.local'),
  path.join(__dirname, '..', '..', '.env'),
]);

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
    }).on('error', reject);
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
  const seedDomains = await supabaseRows('keyword_seeds', { select: 'domain' }, 25000, 1000);
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
    }, 25000, 1000),
    supabaseRows('keyword_latest_scans', {
      select: 'keyword,scanned_at,opportunity_score,gap_score,trajectory,profitability_index',
    }, 25000, 1000),
    supabaseRows('keyword_gap_scores', {
      select: 'keyword,gap_score,trajectory,breakout_flag',
    }, 25000, 1000),
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
    order: 'primary_score.desc.nullslast',
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
  }, 15000, 1000);
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
    opportunity_score: numeric(row.opportunity_score, 0),
    demand_score: numeric(row.demand_score, 0),
    competition_score: numeric(row.competition_score, 0),
    margin_score: numeric(row.margin_score, 0),
    trend_velocity_score: numeric(row.trend_score, 0),
    generated_at: row.scanned_at || '',
    sources_used: [],
  }));
}

async function supabaseStoreIdeas(limit = 12) {
  const opportunities = await supabaseOpportunities(1000);
  const groups = new Map();
  for (const row of opportunities) {
    const domain = row.domain || 'general';
    if (!groups.has(domain)) groups.set(domain, []);
    groups.get(domain).push(row);
  }
  return Array.from(groups.entries())
    .map(([domain, rows]) => {
      const selected = rows.slice(0, 8);
      const avg = selected.reduce((sum, row) => sum + numeric(row.primary_score, 0), 0) / Math.max(1, selected.length);
      const title = domain.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
      return {
        id: `${domain.replace(/[^a-z0-9]+/gi, '-').replace(/^-+|-+$/g, '').toLowerCase() || 'store'}-supabase`,
        name: `${title} Studio`,
        focus: title,
        anchorType: 'supabase_signal',
        keywords: selected.map((row) => ({
          keyword: row.keyword,
          opportunity: numeric(row.opportunity_score),
          gap: numeric(row.gap_score),
          demand: numeric(row.demand_score),
          margin: numeric(row.margin_score),
          product: inferProduct(row.keyword),
          estimatedRevenue: numeric(row.monthly_revenue_usd),
          revenuePerListing: null,
          avgPrice: numeric(row.avg_price_usd),
          competitionEase: row.competition_quality == null ? null : Math.max(0, 100 - numeric(row.competition_quality, 0)),
          marketEvidenceScore: null,
          profitabilityIndex: numeric(row.profitability_index),
          avgFavorites: null,
        })),
        productTypes: Array.from(new Set(selected.map((row) => inferProduct(row.keyword)))).slice(0, 4),
        listingBlueprints: selected.slice(0, 4).map((row, index) => ({
          id: `${domain}-${index + 1}`,
          title: `${String(row.keyword || '').replace(/\b\w/g, (c) => c.toUpperCase())} ${inferProduct(row.keyword)}`,
          primaryKeyword: row.keyword,
          supportingKeywords: selected.filter((item) => item.keyword !== row.keyword).slice(0, 4).map((item) => item.keyword),
          productType: inferProduct(row.keyword).toLowerCase().replace(/\s+/g, '_'),
          listingQualityScore: Math.round(numeric(row.primary_score, 0)),
          profitabilityScore: Math.round(numeric(row.primary_score, 0)),
        })),
        listingIdeas: [],
        opportunity_score: Math.round(avg),
        avgOpportunity: avg,
        avgGap: selected.reduce((sum, row) => sum + numeric(row.gap_score, 0), 0) / Math.max(1, selected.length),
        demandScore: selected.reduce((sum, row) => sum + numeric(row.demand_score, 0), 0) / Math.max(1, selected.length),
        marginScore: selected.reduce((sum, row) => sum + numeric(row.margin_score, 0), 0) / Math.max(1, selected.length),
        storeQualityScore: Math.round(avg),
        profitScore: Math.round(avg),
        recommendationScore: Math.round(avg),
        confidenceScore: Math.round(avg),
        commercialPotentialScore: Math.round(avg),
        rationale: `Built from the current Supabase keyword snapshot for ${title}.`,
        evidence: selected.map((row) => row.keyword).slice(0, 5),
        risks: [],
        validationChecklist: selected.slice(0, 3).map((row) => `Validate current Etsy competition for ${row.keyword}`),
        scoreBreakdown: {},
        profitDrivers: [],
        profitabilityEvidence: [],
        storeRecommendation: {},
      };
    })
    .sort((a, b) => b.avgOpportunity - a.avgOpportunity)
    .slice(0, limit);
}

function inferProduct(keyword) {
  const value = String(keyword || '').toLowerCase();
  if (value.includes('mug')) return 'Mug';
  if (value.includes('shirt') || value.includes('tee')) return 'Shirt';
  if (value.includes('sticker')) return 'Sticker';
  if (value.includes('tote') || value.includes('bag')) return 'Tote';
  if (value.includes('planner') || value.includes('journal')) return 'Planner';
  if (value.includes('poster') || value.includes('print') || value.includes('wall art')) return 'Wall Art';
  return 'Digital Download';
}

function generateLocalStoreIdeas() {
  const script = `
import json
import sys
from pathlib import Path

root = Path.cwd()
backend = root / "backend"
sys.path.insert(0, str(backend))

from pipeline import keyword_database as kdb
from pipeline.store_idea_profitability import generate_profitable_store_ideas

kdb.ensure_seed_snapshot()
kdb.init_db()
kdb.load_seeds_from_library()
print(json.dumps(generate_profitable_store_ideas(limit=12, signal_limit=1000)))
`;
  const candidates = process.platform === 'win32'
    ? ['python', 'py']
    : ['python3', 'python'];

  for (const command of candidates) {
    const result = spawnSync(command, ['-c', script], {
      cwd: path.join(__dirname, '..'),
      encoding: 'utf8',
      env: { ...process.env, BACKEND_DIR: path.join(__dirname, '..', 'backend') },
      maxBuffer: 10 * 1024 * 1024,
    });
    if (result.status === 0) {
      const output = result.stdout.trim();
      const data = JSON.parse(output || '[]');
      if (!Array.isArray(data)) {
        throw new Error(`local store idea generator returned ${typeof data}`);
      }
      return data;
    }
  }

  throw new Error('Python is unavailable for local store idea generation');
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  console.log(hasSupabaseSource()
    ? `Building static data snapshots from Supabase ${SUPABASE_URL}...`
    : API
      ? `Fetching static data snapshots from ${API}...`
      : 'Building static data snapshots from the bundled real-data seed...');

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

  function scoredKeywordCount(data) {
    if (!Array.isArray(data)) return 0;
    return data.filter((item) => Number(item && (item.primary_score ?? item.opportunity_score ?? item.gap_score)) > 0).length;
  }

  function fallbackOrThrow(filename, message) {
    const fallback = readFallback(filename);
    if (!fallback) throw new Error(`${message}; fallback is missing`);
    return fallback;
  }

  for (const [filename, endpoint] of endpoints) {
    try {
      let data = hasSupabaseSource()
        ? await generateSupabaseSnapshot(filename)
        : filename === 'store-ideas.json'
          ? generateLocalStoreIdeas()
          : await fetch(`${API}${endpoint}`);
      if (filename === 'store-ideas.json' && !Array.isArray(data)) {
        throw new Error(`store ideas snapshot expected an array, got ${typeof data}`);
      }
      if (filename === 'store-ideas.json' && Array.isArray(data) && data.length === 0) {
        console.warn(`  ${filename}: backend returned 0 ideas; writing empty snapshot`);
      }
      if (!hasSupabaseSource() && filename === 'stats.json' && data && data.total_seeds < MIN_KEYWORD_SNAPSHOT_COUNT) {
        useSeedFallback = true;
        const fallback = readFallback(filename);
        if (!fallback || fallback.total_seeds < MIN_KEYWORD_SNAPSHOT_COUNT) {
          throw new Error(`stats snapshot only reports ${data.total_seeds} keywords; fallback is missing or too small`);
        }
        console.warn(`  ${filename}: backend only reports ${data.total_seeds} keywords; using seed snapshot stats`);
        data = fallback;
      } else if (!hasSupabaseSource() && filename === 'stats.json' && Number(data?.avg_opportunity || 0) <= 0) {
        const fallback = fallbackOrThrow(filename, `stats snapshot has no opportunity scoring`);
        if (Number(fallback.avg_opportunity || 0) <= 0) {
          throw new Error('stats snapshot and fallback both have no opportunity scoring');
        }
        console.warn(`  ${filename}: backend stats have no opportunity scoring; using seed snapshot stats`);
        data = fallback;
      } else if (useSeedFallback) {
        const fallback = readFallback(filename);
        if (fallback) {
          console.warn(`  ${filename}: using seed snapshot because backend stats are undersized`);
          data = fallback;
        }
      }
      if (!hasSupabaseSource() && filename === 'keywords.json' && Array.isArray(data) && data.length < MIN_KEYWORD_SNAPSHOT_COUNT) {
        const fallback = readFallback(filename);
        if (!Array.isArray(fallback) || fallback.length < MIN_KEYWORD_SNAPSHOT_COUNT) {
          throw new Error(`keyword snapshot only has ${data.length} rows; fallback is missing or too small`);
        }
        console.warn(`  ${filename}: backend only returned ${data.length}; using ${fallback.length}-row seed snapshot`);
        data = fallback;
      }
      if (!hasSupabaseSource() && filename === 'keywords.json' && scoredKeywordCount(data) < MIN_SCORED_KEYWORD_COUNT) {
        const fallback = fallbackOrThrow(filename, `keyword snapshot only has ${scoredKeywordCount(data)} scored rows`);
        const fallbackScored = scoredKeywordCount(fallback);
        if (fallbackScored < MIN_SCORED_KEYWORD_COUNT) {
          throw new Error(`keyword fallback only has ${fallbackScored} scored rows`);
        }
        console.warn(`  ${filename}: backend scoring is too sparse; using ${fallbackScored}-scored-row seed snapshot`);
        data = fallback;
      }
      if (filename === 'opportunities.json' && Array.isArray(data) && data.length === 0) {
        const fallback = fallbackOrThrow(filename, 'opportunities snapshot is empty');
        if (!Array.isArray(fallback) || fallback.length === 0) {
          throw new Error('opportunities snapshot and fallback are both empty');
        }
        console.warn(`  ${filename}: backend returned 0 opportunities; using ${fallback.length}-row seed snapshot`);
        data = fallback;
      }
      const filepath = path.join(OUT, filename);
      fs.writeFileSync(filepath, JSON.stringify(data));
      const kb = (fs.statSync(filepath).size / 1024).toFixed(1);
      console.log(`  ${filename}: ${Array.isArray(data) ? data.length : Object.keys(data).length} entries (${kb} KB)`);
    } catch (e) {
      if (hasSupabaseSource()) {
        console.error(`  ${filename}: FAILED from Supabase - ${e.message}`);
        failed = true;
        continue;
      }

      const fallback = filename === 'store-ideas.json'
        ? generateLocalStoreIdeas()
        : (readFallback(filename) || readExistingSnapshot(filename));
      if (fallback) {
        const filepath = path.join(OUT, filename);
        fs.writeFileSync(filepath, JSON.stringify(fallback));
        const kb = (fs.statSync(filepath).size / 1024).toFixed(1);
        console.warn(`  ${filename}: using bundled real-data snapshot after fetch failure - ${e.message}`);
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
