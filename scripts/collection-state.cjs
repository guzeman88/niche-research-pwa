function parseSources(value) {
  if (Array.isArray(value)) return value.filter(Boolean);
  if (!value) return [];
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed.filter(Boolean) : [];
    } catch {
      return value.split(',').map((item) => item.trim()).filter(Boolean);
    }
  }
  return [];
}

function summarizeCollectionStates(states, totalSeeds, now = new Date()) {
  const staleBefore = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
  let successful = 0;
  let evidenceBacked = 0;
  let failed = 0;
  let noData = 0;
  let stale = 0;

  for (const state of states) {
    const evidenceStatus = state.evidence_status || 'unverified';
    const sources = parseSources(state.sources);
    if (evidenceStatus === 'verified') evidenceBacked += 1;
    if (evidenceStatus === 'failed') failed += 1;
    if (evidenceStatus !== 'failed' && (['partial', 'verified'].includes(evidenceStatus) || sources.length)) {
      successful += 1;
    }
    if (evidenceStatus === 'unverified' && !sources.length) noData += 1;
    const collectedAt = state.last_collected_at ? new Date(state.last_collected_at) : null;
    if (collectedAt && !Number.isNaN(collectedAt.getTime()) && collectedAt < staleBefore) stale += 1;
  }

  const attempted = states.length;
  return {
    attempted,
    successful,
    evidence_backed: evidenceBacked,
    failed,
    no_data: noData,
    stale,
    scanned: attempted,
    unscanned: Math.max(0, totalSeeds - attempted),
    coverage_pct: totalSeeds ? Math.round(attempted / totalSeeds * 1000) / 10 : null,
  };
}

function collectionScanStatus(state) {
  if (!state?.last_collected_at) return null;
  if (state.evidence_status === 'failed') return 'failed';
  if (state.evidence_status === 'unverified' && !parseSources(state.sources).length) return 'no_data';
  return 'signals';
}

module.exports = { collectionScanStatus, parseSources, summarizeCollectionStates };
