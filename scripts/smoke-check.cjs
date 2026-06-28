const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const MIN_KEYWORDS = Number(process.env.MIN_KEYWORD_SNAPSHOT_COUNT || 13000);
const MIN_SCORED_KEYWORDS = Number(process.env.MIN_SCORED_KEYWORD_COUNT || 1000);
const BLOCKED_BACKEND_URLS = [
  ['https://niche-research-api', 'onrender.com'].join('.'),
  ['https://niche-research-api-kqlt', 'onrender', 'com'].join('.'),
];
const CURRENT_BACKEND_URL = process.env.VITE_API_URL || '';

const failures = [];

function fail(message) {
  failures.push(message);
}

function readJson(relativePath) {
  const fullPath = path.join(ROOT, relativePath);
  if (!fs.existsSync(fullPath)) {
    fail(`${relativePath} is missing`);
    return null;
  }

  try {
    return JSON.parse(fs.readFileSync(fullPath, 'utf8'));
  } catch (error) {
    fail(`${relativePath} is not valid JSON: ${error.message}`);
    return null;
  }
}

function walkFiles(dir, files = []) {
  if (!fs.existsSync(dir)) return files;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name === '.git' || entry.name === 'dist') continue;
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) walkFiles(fullPath, files);
    else files.push(fullPath);
  }
  return files;
}

const keywords = readJson('public/data/keywords.json');
if (Array.isArray(keywords)) {
  if (keywords.length < MIN_KEYWORDS) {
    fail(`public/data/keywords.json has ${keywords.length} rows; expected at least ${MIN_KEYWORDS}`);
  }
  const scoredKeywords = keywords.filter((item) => Number(item && (item.opportunity_score ?? item.gap_score)) > 0);
  if (scoredKeywords.length < MIN_SCORED_KEYWORDS) {
    fail(`public/data/keywords.json has ${scoredKeywords.length} scored rows; expected at least ${MIN_SCORED_KEYWORDS}`);
  }
} else if (keywords) {
  fail('public/data/keywords.json must be an array');
}

const stats = readJson('public/data/stats.json');
if (stats && Number(stats.total_seeds || 0) < MIN_KEYWORDS) {
  fail(`public/data/stats.json reports ${stats.total_seeds || 0} seeds; expected at least ${MIN_KEYWORDS}`);
}
if (stats && Number(stats.avg_opportunity || 0) <= 0) {
  fail('public/data/stats.json must include real opportunity scoring');
}

const opportunities = readJson('public/data/opportunities.json');
if (Array.isArray(opportunities)) {
  if (opportunities.length === 0) {
    fail('public/data/opportunities.json must include real keyword opportunities');
  }
} else if (opportunities) {
  fail('public/data/opportunities.json must be an array');
}

const storeIdeas = readJson('public/data/store-ideas.json');
if (Array.isArray(storeIdeas)) {
  if (storeIdeas.length === 0) {
    console.warn('public/data/store-ideas.json is empty; no market-evidence-backed store ideas are currently available');
  } else {
    const firstIdea = storeIdeas[0] || {};
    if (!Array.isArray(firstIdea.keywordClusters) || firstIdea.keywordClusters.length === 0) {
      fail('public/data/store-ideas.json must include keywordClusters for store recommendations');
    }
    if (!Array.isArray(firstIdea.listingBlueprints) || firstIdea.listingBlueprints.length === 0) {
      fail('public/data/store-ideas.json must include listingBlueprints based on real keywords');
    }
    const firstBlueprint = firstIdea.listingBlueprints?.[0] || {};
    if (!firstBlueprint.primaryKeyword || !Array.isArray(firstBlueprint.supportingKeywords)) {
      fail('store idea listing blueprints must include a primaryKeyword and supportingKeywords');
    }
    if (!firstIdea.evidenceDepth || typeof firstIdea.evidenceDepth.score !== 'number') {
      fail('store ideas must include evidenceDepth scoring');
    }
    if (!firstIdea.profitabilityEvidence || typeof firstIdea.profitabilityEvidence.evidenceScore !== 'number') {
      fail('store ideas must include profitabilityEvidence with evidenceScore');
    }
    if (!firstIdea.scoreBreakdown || typeof firstIdea.scoreBreakdown !== 'object') {
      fail('store ideas must include scoreBreakdown for profit scoring transparency');
    }
    if (typeof firstIdea.storeQualityScore !== 'number' || typeof firstIdea.recommendationScore !== 'number') {
      fail('store ideas must include source-backed storeQualityScore and recommendationScore');
    }
    for (const idea of storeIdeas) {
      const evidence = idea.profitabilityEvidence || {};
      const hasProfitEvidence = Boolean(
        evidence.observedPriceBand
        || evidence.sampledMonthlyRevenue
        || evidence.revenuePerListing
        || evidence.marketTractionScore
      );
      if (idea.profitScore != null && !hasProfitEvidence) {
        fail(`store idea ${idea.name || idea.id || 'unknown'} has profitScore without profit evidence`);
      }
    }
    if (!firstBlueprint.profitInputs || typeof firstBlueprint.profitInputs !== 'object') {
      fail('listing blueprints must include profitInputs for future listing optimization');
    }
    if (typeof firstBlueprint.listingQualityScore !== 'number' || !firstBlueprint.qualityInputs) {
      fail('listing blueprints must include listingQualityScore and qualityInputs');
    }
  }
} else if (storeIdeas) {
  fail('public/data/store-ideas.json must be an array');
}

const sourceFiles = walkFiles(path.join(ROOT, 'src'))
  .concat(walkFiles(path.join(ROOT, 'scripts')))
  .concat([path.join(ROOT, '.github', 'workflows', 'deploy-pwa.yml')]);

for (const file of sourceFiles) {
  const content = fs.readFileSync(file, 'utf8');
  for (const url of BLOCKED_BACKEND_URLS) {
    if (content.includes(url)) {
      fail(`${path.relative(ROOT, file)} still references the suspended backend URL ${url}`);
    }
  }
}

if (CURRENT_BACKEND_URL) {
  console.warn(`Smoke check using custom backend URL: ${CURRENT_BACKEND_URL}`);
}

if (failures.length) {
  console.error('Smoke check failed:');
  for (const message of failures) console.error(`- ${message}`);
  process.exit(1);
}

console.log(`Smoke check passed: ${keywords?.length || 0} static keywords, ${storeIdeas?.length || 0} store ideas`);
