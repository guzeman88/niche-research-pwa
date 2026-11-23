export function validateDashboardStats(stats) {
  const count=value=>typeof value==='number'&&Number.isSafeInteger(value)&&value>=0;
  if(!stats||!count(stats.total_seeds))throw new Error('Dashboard snapshot is incomplete.');
  for(const field of ['scanned','unscanned','attempted','successful','evidence_backed','failed','no_data','stale','total_scans']){
    if(stats[field]!=null&&!count(stats[field]))throw new Error('Dashboard snapshot contains invalid counts.');
  }
  if(stats.scanned!=null&&stats.scanned>stats.total_seeds)throw new Error('Dashboard counts have inconsistent scopes.');
  if(stats.coverage_pct!=null&&(typeof stats.coverage_pct!=='number'||!Number.isFinite(stats.coverage_pct)||stats.coverage_pct<0||stats.coverage_pct>100))throw new Error('Dashboard coverage is invalid.');
  if(stats.domains!=null&&(!Array.isArray(stats.domains)||stats.domains.some(row=>typeof row.domain!=='string'||!count(row.cnt))))throw new Error('Dashboard categories are incomplete.');
}

export function normalizeOperationalSnapshot(row,at=Date.now()) {
  if(!row?.payload||row.payload.schema_version!==2)throw new Error('Operational report is unavailable.');
  validateDashboardStats(row.payload.stats);
  const generated=Date.parse(row.generated_at);
  if(!Number.isFinite(generated)||generated>at+30000||!Number.isSafeInteger(Number(row.snapshot_version)))throw new Error('Operational report metadata is invalid.');
  if(row.payload.generated_at&&Date.parse(row.payload.generated_at)!==generated)throw new Error('Operational report versions do not match.');
  if(row.payload.snapshot_version!=null&&Number(row.payload.snapshot_version)!==Number(row.snapshot_version))throw new Error('Operational report versions do not match.');
  if(row.payload.input_fingerprint&&row.input_fingerprint!==row.payload.input_fingerprint)throw new Error('Operational report fingerprints do not match.');
  const stale=at-generated>150000;
  return {...row.payload,snapshot_version:row.snapshot_version,generated_at:row.generated_at,
    data_status:stale?'degraded':row.payload.data_status,
    delivery:{mode:'live',refresh_interval_seconds:60,stale,scope:'native_collection_library'}};
}

export function normalizeDashboardSnapshot(row, refreshIntervalSeconds = 60) {
  if (!row || typeof row !== 'object' || !row.payload || typeof row.payload !== 'object') {
    throw new Error('Dashboard snapshot is unavailable.');
  }
  const stats = row.payload.stats;
  validateDashboardStats(stats);
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
