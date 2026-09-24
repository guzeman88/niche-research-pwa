export const TARGET_MIN_PCT = 80;

export const SOURCES = [
  {id:'etsy_open_api', name:'Etsy Open API', purpose:'Supply, prices, shops, favorites, tags and materials', parts:['etsy_listings','etsy_observations'], metric:'quota', mode:'automatic'},
  {id:'google_suggest', name:'Google Shopping Suggest', purpose:'Buyer phrasing and long-tail keyword expansion', parts:['google_suggest'], metric:'eligible', mode:'automatic'},
  {id:'google_trends', name:'Google Trends automatic', purpose:'Relative interest, trend history and related queries', parts:['google_trend_points','google_trend_observations'], metric:'eligible', mode:'automatic'},
  {id:'google_daily_trends', name:'Google Daily Search Trends', purpose:'Current searches, traffic lower bounds and linked news', parts:['google_daily_observations'], metric:'feed', mode:'automatic'},
  {id:'pinterest_trends', name:'Pinterest Trends', purpose:'Visual demand, growth, seasonality and relative-interest history', parts:['pinterest_trend_points','pinterest_observations'], metric:'feed', mode:'automatic'},
  {id:'reddit_etsy', name:'Reddit Data API', purpose:'Customer language, complaints, post activity and engagement', parts:['reddit_observations'], metric:'eligible', mode:'automatic'},
  {id:'etsy_marketplace_insights', name:'Etsy Marketplace Insights', purpose:'Etsy search counts, related terms and competing-listing counts', parts:['etsy_marketplace_observations'], metric:'import', mode:'manual'},
  {id:'etsy_shop_stats', name:'Etsy Shop Stats', purpose:'Own-shop visits, views, orders and revenue', parts:['etsy_shop_observations'], metric:'import', mode:'manual'},
  {id:'google_keyword_planner', name:'Google Keyword Planner', purpose:'Monthly demand estimates, competition and bid ranges', parts:['google_planner_observations'], metric:'import', mode:'manual'},
  {id:'erank', name:'eRank', purpose:'Etsy searches, clicks, click rate and competition', parts:['erank_observations'], metric:'import', mode:'manual'},
  {id:'marmalead', name:'Marmalead', purpose:'Keyword demand, engagement and competition metrics', parts:['marmalead_observations'], metric:'import', mode:'manual'},
  {id:'google_trends_csv', name:'Google Trends CSV', purpose:'User-selected trend series, dates and geography', parts:['google_trends_csv_points','google_trends_csv_observations'], metric:'import', mode:'manual'},
];

const PART_LABELS = {
  etsy_listings:'listing snapshots', etsy_observations:'metric rows', google_suggest:'suggestions',
  google_trend_points:'dated trend points', google_trend_observations:'series summaries',
  google_daily_observations:'metric rows', pinterest_trend_points:'trend points',
  pinterest_observations:'metric rows', reddit_observations:'metric rows',
  etsy_marketplace_observations:'metric rows', etsy_shop_observations:'metric rows',
  google_planner_observations:'metric rows', erank_observations:'metric rows',
  marmalead_observations:'metric rows', google_trends_csv_points:'dated trend points',
  google_trends_csv_observations:'metric rows',
};

function number(value) {
  return typeof value === 'number' && Number.isFinite(value) ? Math.max(0, value) : null;
}

function sumParts(source, counts, suffix) {
  const values = source.parts.map(part => number(counts[`${part}_${suffix}`]));
  return values.some(value => value === null) ? null : values.reduce((sum, value) => sum + value, 0);
}

function detailParts(source, counts, suffix) {
  return source.parts.map(part => ({label:PART_LABELS[part], value:number(counts[`${part}_${suffix}`])}));
}

function percent(numerator, denominator) {
  if (number(numerator) === null || number(denominator) === null || denominator <= 0) return null;
  return Math.round(Math.min(100, numerator / denominator * 100) * 10) / 10;
}

function eventTotals(events) {
  const totals = {};
  for (const event of events || []) {
    const provider = String(event?.provider || '');
    if (!provider) continue;
    const row = totals[provider] ||= {eligible:0, processed:0, usable:0, providerRows:0, coveredRows:0, newRows:0};
    const metadata = event?.metadata && typeof event.metadata === 'object' ? event.metadata : {};
    for (const [key, target] of [['eligible_keywords','eligible'],['processed_keywords','processed'],['usable_keywords','usable'],['provider_rows','providerRows'],['covered_rows','coveredRows'],['new_rows','newRows']]) {
      const value = number(metadata[key]);
      if (value !== null) row[target] += value;
    }
  }
  return totals;
}

function maximum(source, denominator) {
  if (source.id === 'etsy_open_api') {
    return denominator === null
      ? {headline:'TBD from live provider quota', detail:'EtGen does not substitute a default quota when Etsy has not reported one.'}
      : {headline:`${denominator} requests/provider quota day`, detail:`The operating target is ${Math.round(denominator * TARGET_MIN_PCT / 100)} requests (${TARGET_MIN_PCT}%), retaining the remainder as a safety reserve.`};
  }
  if (source.id === 'google_suggest') return {headline:'No published provider maximum', detail:denominator === null ? 'Capacity is measured from actual eligible keywords scheduled in the rolling window.' : `${denominator} eligible keywords were scheduled in the rolling window.`};
  if (source.id === 'google_trends') return {headline:'No published stable maximum', detail:denominator === null ? 'Coverage is measured from actual eligible marketplace-supported series.' : `${denominator} marketplace-supported keyword series were eligible in the rolling window.`};
  if (source.id === 'google_daily_trends') return {headline:'No fixed provider maximum', detail:denominator === null ? 'Capacity is the number of rows actually returned by the provider feed.' : `The measured feeds returned ${denominator} available rows.`};
  if (source.id === 'pinterest_trends') return {headline:'Up to 50 results/request after approval', detail:'Actual account capacity remains TBD until Pinterest assigns an approved access tier.'};
  if (source.id === 'reddit_etsy') return {headline:'TBD until commercial approval', detail:'Approved commercial terms control usable request capacity.'};
  if (source.id === 'etsy_marketplace_insights') return {headline:'15 manual searches/week free', detail:'Imported row volume depends on the actual dated export.'};
  if (source.id === 'google_keyword_planner') return {headline:'No EtGen import cap', detail:'The current path is a manual export; API capacity remains TBD until Google Ads access is configured.'};
  if (source.id === 'erank') return {headline:'No EtGen import cap', detail:'Usable volume depends on the supplied export and the user’s eRank plan.'};
  if (source.id === 'marmalead') return {headline:'No EtGen import cap', detail:'Usable volume depends on the supplied export and account access.'};
  if (source.id === 'google_trends_csv') return {headline:'No EtGen import cap', detail:'Manual file size controls the rate; this remains separate from the automatic collector.'};
  return {headline:'No EtGen import cap', detail:'Limited by the rows present in the supplied source export.'};
}

function stateFor(source, state) {
  if (source.mode === 'manual') return {label:'Manual', tone:'manual', detail:state?.last_attempt_at ? 'Last import attempt' : 'No automatic collection schedule', last_attempt_at:state?.last_attempt_at || null};
  if (!state) return {label:'TBD', tone:'neutral', detail:'No verified runtime state is available'};
  if (state.configured === false) return {label:'Not configured', tone:'gated', detail:'Provider access or credentials are required'};
  if (state.status === 'failed') return {label:'Attention', tone:'gated', detail:'Latest attempt failed', last_attempt_at:state.last_attempt_at || null};
  if (state.configured === true) return {label:'Running', tone:'running', detail:`Latest ${state.status || 'recorded'} attempt`, last_attempt_at:state.last_attempt_at || null};
  return {label:'TBD', tone:'neutral', detail:'Configuration state has not been verified'};
}

function rateFor(source, state, totals) {
  let numerator = null;
  let denominator = null;
  let yieldPct = null;
  if (source.metric === 'quota') {
    const limit = number(state?.rate_limit?.limit_per_day);
    const remaining = number(state?.rate_limit?.remaining_today);
    if (limit !== null && limit > 0 && remaining !== null) {
      denominator = limit;
      numerator = Math.min(limit, Math.max(0, limit - remaining));
    }
  } else if (source.metric === 'eligible') {
    if (totals.eligible > 0) {
      denominator = totals.eligible;
      numerator = totals.processed;
      yieldPct = percent(totals.usable, totals.processed);
    }
  } else if ((source.metric === 'feed' || source.metric === 'import') && totals.providerRows > 0) {
    denominator = totals.providerRows;
    numerator = totals.coveredRows;
  }
  const value = percent(numerator, denominator);
  return {value, numerator, denominator, yield_pct:yieldPct, target_status:value === null ? (state?.configured === false ? 'not_configured' : 'tbd') : value >= TARGET_MIN_PCT ? 'on_target' : 'below_target'};
}

export function buildCollectionReport({counts = {}, states = [], events = [], now = new Date(), dataStatus = 'complete'} = {}) {
  const stateMap = Object.fromEntries((states || []).filter(row => row?.provider).map(row => [row.provider, row]));
  const totals = eventTotals(events);
  const rows = SOURCES.map(source => {
    const state = stateMap[source.id];
    const rate = rateFor(source, state, totals[source.id] || {eligible:0,processed:0,usable:0,providerRows:0,coveredRows:0,newRows:0});
    return {
      id:source.id, name:source.name, purpose:source.purpose,
      stored_24h:sumParts(source, counts, '24h'), stored_24h_parts:detailParts(source, counts, '24h'),
      total_stored:sumParts(source, counts, 'total'), total_parts:detailParts(source, counts, 'total'),
      maximum:maximum(source, rate.denominator), rate, state:stateFor(source, state),
    };
  });
  return {generated_at:new Date(now).toISOString(), window_hours:24, refresh_seconds:3600, target_min_pct:TARGET_MIN_PCT, data_status:dataStatus, sources:rows};
}
