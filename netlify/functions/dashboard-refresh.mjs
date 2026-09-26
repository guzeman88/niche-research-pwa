import { createClient } from '@supabase/supabase-js';

const options = {
  global: {
    fetch: (input, init = {}) => fetch(input, {
      ...init,
      signal: init.signal
        ? AbortSignal.any([init.signal, AbortSignal.timeout(12000)])
        : AbortSignal.timeout(12000),
    }),
  },
  auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
};

export default async function handler() {
  const startedAt = Date.now();
  const headers = { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' };
  try {
    if (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY) {
      throw new Error('Dashboard refresh is not configured.');
    }
    const service = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY, options);
    const result = await service.rpc('refresh_research_dashboard_snapshot', { force_refresh: false });
    if (result.error) throw result.error;
    const snapshot = Array.isArray(result.data) ? result.data[0] : result.data;
    if (!snapshot?.snapshot_version) throw new Error('Dashboard refresh returned no snapshot.');
    console.log(JSON.stringify({
      event: 'dashboard_snapshot_refreshed',
      snapshot_version: snapshot.snapshot_version,
      data_status: snapshot.data_status,
      duration_ms: Date.now() - startedAt,
    }));
    return new Response(JSON.stringify({
      ok: true,
      snapshot_version: snapshot.snapshot_version,
      data_status: snapshot.data_status,
      generated_at: snapshot.generated_at,
    }), { status: 200, headers });
  } catch (error) {
    console.error(JSON.stringify({
      event: 'dashboard_snapshot_refresh_failed',
      duration_ms: Date.now() - startedAt,
      error: error instanceof Error ? error.message : 'Unknown error',
    }));
    return new Response(JSON.stringify({ error: 'Dashboard refresh failed.' }), { status: 503, headers });
  }
}

export const config = { schedule: '*/5 * * * *' };
