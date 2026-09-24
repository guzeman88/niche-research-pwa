import {createClient} from '@supabase/supabase-js';
import {buildCollectionReport} from './lib/collection-report.mjs';

const COUNT_SPECS = {
  etsy_listings:['keyword_listing_snapshots','etsy_open_api','observed_at'],
  etsy_observations:['keyword_observations','etsy_open_api','observed_at'],
  google_suggest:['keyword_suggestions','google_suggest','observed_at'],
  google_trend_points:['keyword_trend_points','google_trends','collected_at'],
  google_trend_observations:['keyword_observations','google_trends','observed_at'],
  google_daily_observations:['keyword_observations','google_daily_trends','observed_at'],
  pinterest_trend_points:['keyword_trend_points','pinterest_trends','collected_at'],
  pinterest_observations:['keyword_observations','pinterest_trends','observed_at'],
  reddit_observations:['keyword_observations','reddit_etsy','observed_at'],
  etsy_marketplace_observations:['keyword_observations','etsy_marketplace_insights','observed_at'],
  etsy_shop_observations:['keyword_observations','etsy_shop_stats','observed_at'],
  google_planner_observations:['keyword_observations','google_keyword_planner','observed_at'],
  erank_observations:['keyword_observations','erank','observed_at'],
  marmalead_observations:['keyword_observations','marmalead','observed_at'],
  google_trends_csv_points:['keyword_trend_points','google_trends_csv','collected_at'],
  google_trends_csv_observations:['keyword_observations','google_trends_csv','observed_at'],
};

const options = {global:{fetch:(input, init = {}) => fetch(input,{...init,signal:init.signal ? AbortSignal.any([init.signal,AbortSignal.timeout(12000)]) : AbortSignal.timeout(12000)})},auth:{persistSession:false,autoRefreshToken:false,detectSessionInUrl:false}};

export default async function handler(request) {
  const headers = {'Content-Type':'application/json; charset=utf-8','Cache-Control':'public, max-age=0, s-maxage=3600, stale-while-revalidate=120','Netlify-CDN-Cache-Control':'public, durable, s-maxage=3600, stale-while-revalidate=120','X-Content-Type-Options':'nosniff'};
  if (request.method !== 'GET') return new Response(JSON.stringify({error:'Method not allowed.'}),{status:405,headers});
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) return new Response(JSON.stringify({error:'Live collection data is not configured.'}),{status:503,headers:{...headers,'Cache-Control':'no-store','Netlify-CDN-Cache-Control':'no-store'}});
  try {
    const service = createClient(url,key,options);
    const since = new Date(Date.now() - 86400000).toISOString();
    const failures = [];
    const countEntries = await Promise.all(Object.entries(COUNT_SPECS).flatMap(([name,[table,source,timeColumn]]) => [
      [name+'_total',table,source,timeColumn,null], [name+'_24h',table,source,timeColumn,since],
    ]).map(async ([name,table,source,timeColumn,after]) => {
      let query = service.from(table).select('*',{count:'exact',head:true}).eq('source',source);
      if (after) query = query.gte(timeColumn,after);
      const {count,error} = await query;
      if (error) { failures.push(name); return [name,null]; }
      return [name,typeof count === 'number' ? count : null];
    }));
    const [stateResult,eventResult] = await Promise.all([
      service.from('provider_runtime_state').select('provider,configured,status,last_attempt_at,last_success_at,rate_limit,metadata,updated_at'),
      service.from('provider_collection_events').select('provider,status,completed_at,keyword_count,row_count,rate_limit,metadata').gte('completed_at',since).order('completed_at',{ascending:true}).limit(10000),
    ]);
    if (stateResult.error) failures.push('provider_runtime_state');
    if (eventResult.error) failures.push('provider_collection_events');
    if (failures.length > Object.keys(COUNT_SPECS).length) throw new Error('Production evidence query failed.');
    const report = buildCollectionReport({counts:Object.fromEntries(countEntries),states:stateResult.data || [],events:eventResult.data || [],dataStatus:failures.length ? 'partial' : 'complete'});
    return new Response(JSON.stringify(report),{status:200,headers});
  } catch {
    return new Response(JSON.stringify({error:'Live collection data is temporarily unavailable. No fallback values were used.'}),{status:503,headers:{...headers,'Cache-Control':'no-store','Netlify-CDN-Cache-Control':'no-store'}});
  }
}

export const config = {path:'/api/collection-rates'};
