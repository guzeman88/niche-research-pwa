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

function integer(value) {
  return Math.round(value).toLocaleString('en-US');
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
    const row = totals[provider] ||= {eligible:0, processed:0, usable:0, providerRows:0, coveredRows:0, newRows:0, latestProviderRows:null};
    const metadata = event?.metadata && typeof event.metadata === 'object' ? event.metadata : {};
    for (const [key, target] of [['eligible_keywords','eligible'],['processed_keywords','processed'],['usable_keywords','usable'],['provider_rows','providerRows'],['covered_rows','coveredRows'],['new_rows','newRows']]) {
      const value = number(metadata[key]);
      if (value !== null) row[target] += value;
    }
    const latestProviderRows = number(metadata.provider_rows);
    if (latestProviderRows !== null) row.latestProviderRows = latestProviderRows;
  }
  return totals;
}

function maximum(source, denominator, totals) {
  if (source.id === 'etsy_open_api') {
    return denominator === null
      ? {headline:'TBD from live provider quota', detail:'EtGen does not substitute a default quota when Etsy has not reported one.'}
      : {headline:`${integer(denominator * 100)} listing rows/day*`, detail:`${integer(denominator)} verified requests/day × 100 listings per response. Provider ceiling: 5 requests/second. Operating goal: ${integer(denominator * TARGET_MIN_PCT / 100)} requests (${TARGET_MIN_PCT}%).`};
  }
  if (source.id === 'google_suggest') return {headline:'125,000 suggestions/day*', detail:`5,000 keyword cycles × up to 25 stored suggestions. Four prefixed queries run per cycle, requiring up to 20,000 requests/day. ${denominator === null ? 'Google publishes no stable quota; results vary and are deduplicated.' : `${integer(denominator)} eligible cycles were measured in the rolling window.`}`};
  if (source.id === 'google_trends') return {headline:'5,000 keyword series/day*', detail:`Five keywords per batch, or up to 1,000 batch runs/day. Points per series vary, and the unofficial provider path can be throttled. ${denominator === null ? 'The provider publishes no stable quota.' : `${integer(denominator)} eligible series were measured in the rolling window.`}`};
  if (source.id === 'google_daily_trends') {
    const perPoll = number(totals.latestProviderRows);
    return perPoll === null
      ? {headline:'Estimated feed capacity TBD', detail:'The estimate will appear after a provider feed is observed.'}
      : {headline:'24 feed snapshots/day*', detail:`Hourly polling × ${integer(perPoll)} rows in the latest feed = ${integer(perPoll * 24)} returned rows/day*. Google controls the feed size; ${integer(denominator ?? 0)} rows were measured in the rolling window.`};
  }
  if (source.id === 'pinterest_trends') return {headline:'200 trend keywords/day*', detail:'Four useful daily pulls × 50 results after approval. Trial capacity can allow 1,000 requests/day, but additional pulls would mostly repeat unchanged daily data.'};
  if (source.id === 'reddit_etsy') return {headline:'5,000 keyword aggregates/day*', detail:'After commercial approval: up to 250,000 posts across five subreddits using 25,000 searches/day. Approved terms control actual capacity; published OAuth capacity is 100 requests/minute.'};
  if (source.id === 'etsy_marketplace_insights') return {headline:'15 searches/week verified', detail:'Planning goal: use at least 12 searches/week (80%) and import every valid exported row.'};
  if (source.id === 'google_keyword_planner') return {headline:'2,880–15,000 operations/day*', detail:'Future API capacity: 2,880 operations/day with Explorer access or 15,000/day with Basic access; planning requests are also capped at 1/second. The current manual import path has no EtGen row cap.'};
  if (source.id === 'erank') return {headline:'No EtGen import cap', detail:'Automatic capacity is unavailable because eRank has no generally available public API. File volume and the user’s plan determine the usable maximum.'};
  if (source.id === 'marmalead') return {headline:'No EtGen import cap', detail:'Automatic capacity is unavailable because Marmalead has no generally available public API. File volume and account access determine the usable maximum.'};
  if (source.id === 'google_trends_csv') return {headline:'No EtGen import cap', detail:'Manual file size controls the rate; this remains separate from the automatic collector.'};
  return {headline:'No EtGen import cap', detail:'Limited by the rows present in the supplied source export.'};
}

function stateFor(source, state) {
  if (source.mode === 'manual') return {label:'Manual', tone:'manual', detail:state?.last_attempt_at ? 'Last import attempt' : 'No automatic collection schedule', last_attempt_at:state?.last_attempt_at || null};
  if (!state) return {label:'TBD', tone:'neutral', detail:'No verified runtime state is available'};
  if (state.configured === false) return {label:'Not configured', tone:'gated', detail:'Provider access or credentials are required'};
  if (state.status === 'failed') return {label:'Attention', tone:'gated', detail:'Latest attempt failed', last_attempt_at:state.last_attempt_at || null};
  if (state.configured === true) {
    const status = state.status === 'no_data' ? 'no-data' : state.status || 'recorded';
    return {label:'Running', tone:'running', detail:`Latest ${status} attempt`, last_attempt_at:state.last_attempt_at || null};
  }
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
    const providerTotals = totals[source.id] || {eligible:0,processed:0,usable:0,providerRows:0,coveredRows:0,newRows:0,latestProviderRows:null};
    const rate = rateFor(source, state, providerTotals);
    return {
      id:source.id, name:source.name, purpose:source.purpose,
      stored_24h:sumParts(source, counts, '24h'), stored_24h_parts:detailParts(source, counts, '24h'),
      total_stored:sumParts(source, counts, 'total'), total_parts:detailParts(source, counts, 'total'),
      maximum:maximum(source, rate.denominator, providerTotals), rate, state:stateFor(source, state),
    };
  });
  return {generated_at:new Date(now).toISOString(), window_hours:24, refresh_seconds:3600, target_min_pct:TARGET_MIN_PCT, data_status:dataStatus, sources:rows};
}
