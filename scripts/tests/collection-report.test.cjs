const test = require('node:test');
const assert = require('node:assert/strict');

test('collection report uses measured counts and coverage without defaults', async () => {
  const {buildCollectionReport} = await import('../../netlify/functions/lib/collection-report.mjs');
  const counts = {
    etsy_listings_24h:100, etsy_observations_24h:10, etsy_listings_total:1000, etsy_observations_total:100,
    google_suggest_24h:12, google_suggest_total:120,
  };
  const states = [
    {provider:'etsy_open_api',configured:true,status:'completed',last_attempt_at:'2026-09-24T12:00:00Z',rate_limit:{limit_per_day:5000,remaining_today:1000}},
    {provider:'google_suggest',configured:true,status:'completed',last_attempt_at:'2026-09-24T12:00:00Z'},
    {provider:'pinterest_trends',configured:false,status:'not_configured'},
  ];
  const events = [{provider:'google_suggest',metadata:{eligible_keywords:10,processed_keywords:8,usable_keywords:6}}];
  const report = buildCollectionReport({counts,states,events,now:new Date('2026-09-24T13:00:00Z')});
  const byId = Object.fromEntries(report.sources.map(source => [source.id,source]));
  assert.equal(byId.etsy_open_api.stored_24h,110);
  assert.equal(byId.etsy_open_api.total_stored,1100);
  assert.equal(byId.etsy_open_api.rate.value,80);
  assert.match(byId.etsy_open_api.maximum.detail,/500,000 listing rows\/day\*/);
  assert.equal(byId.google_suggest.rate.value,80);
  assert.equal(byId.google_suggest.rate.yield_pct,75);
  assert.match(byId.google_suggest.maximum.headline,/4,000 keyword cycles\/day\*/);
  assert.equal(report.sources.some(source => source.maximum.headline.includes('≈')),false);
  assert.equal(byId.pinterest_trends.rate.value,null);
  assert.equal(byId.pinterest_trends.state.label,'Not configured');
  assert.equal(byId.erank.total_stored,null);
  assert.equal(byId.erank.rate.value,null);
});

test('zero is retained only when it was actually measured', async () => {
  const {buildCollectionReport} = await import('../../netlify/functions/lib/collection-report.mjs');
  const counts = {reddit_observations_24h:0,reddit_observations_total:0};
  const report = buildCollectionReport({counts});
  const reddit = report.sources.find(source => source.id === 'reddit_etsy');
  assert.equal(reddit.stored_24h,0);
  assert.equal(reddit.total_stored,0);
  assert.equal(reddit.rate.value,null);
});
