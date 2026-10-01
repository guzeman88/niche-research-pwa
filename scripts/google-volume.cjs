// Select the newest exact Google Ads monthly-search observation for each keyword.
function latestGoogleVolumes(rows) {
  const volumes = new Map();
  for (const row of rows) {
    const keyword = String(row.keyword || '').trim().toLowerCase();
    const value = row.value == null ? NaN : Number(row.value);
    if (!keyword || !Number.isFinite(value) || value < 0) continue;
    const observedAt = String(row.observed_at || '');
    const previous = volumes.get(keyword);
    if (!previous || observedAt > previous.observedAt) {
      volumes.set(keyword, { value, observedAt });
    }
  }
  return volumes;
}

module.exports = { latestGoogleVolumes };
