export function normalizeDashboardSnapshot(row, refreshIntervalSeconds = 60) {
  if (!row || typeof row !== 'object' || !row.payload || typeof row.payload !== 'object') {
    throw new Error('Dashboard snapshot is unavailable.');
  }
  const stats = row.payload.stats;
  if (!stats || typeof stats !== 'object' || !Number.isFinite(Number(stats.total_seeds))) {
    throw new Error('Dashboard snapshot is incomplete.');
  }
  return {
    ...row.payload,
    snapshot_version: Number(row.snapshot_version),
    generated_at: row.generated_at,
    data_status: row.data_status,
    input_fingerprint: row.input_fingerprint,
    source_watermarks: row.source_watermarks || {},
    duration_ms: Number(row.duration_ms || 0),
    delivery: {
      mode: 'live',
      refresh_interval_seconds: refreshIntervalSeconds,
    },
  };
}

export function dashboardEtag(row) {
  return `W/"dashboard-${Number(row.snapshot_version)}-${String(row.input_fingerprint || '').slice(0, 12)}"`;
}
