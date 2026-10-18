"""Comparable point estimates, one vote per provider and capped dependent group."""
from collections import defaultdict
from datetime import timedelta
import json
from statistics import median, mean
from . import registry, store

VERSION = 'group-median-v1'


def weighted_median(rows):
    ordered = sorted(rows, key=lambda x: x[0])
    half = sum(w for _, w in ordered) / 2
    total = 0.0
    for index, (value, weight) in enumerate(ordered):
        total += weight
        if total >= half:
            if abs(total - half) < 1e-12 and index + 1 < len(ordered):
                return (value + ordered[index + 1][0]) / 2
            return value
    return None


def build(con, listing_id, as_of=None, save=False):
    at = store.stamp(as_of) if as_of else store.now()
    records = con.execute('''SELECT o.id,o.payload FROM observations o
      WHERE listing_id=? AND metric='estimated_sales' AND available_at<=?
      AND NOT EXISTS(SELECT 1 FROM observations n WHERE n.supersedes=o.id AND n.available_at<=?)
      ORDER BY o.captured_at DESC,o.available_at DESC,o.id''', (listing_id, at.isoformat(), at.isoformat())).fetchall()
    groups, excluded = defaultdict(dict), []
    method_groups = {s[0]: s[3] for s in registry.SEEDS}
    for row in records:
        item = json.loads(row['payload'])
        reason = None
        if not registry.permission(item['source_id'], 'comparison'):
            reason = 'source_comparison_not_eligible'
        elif item['status'] != 'observed' or item['value'] is None:
            reason = item['status']
        elif item['precision'] != 'point':
            reason = 'bounded_value_not_point_estimate'
        elif store.stamp(item.get('provider_updated_at') or item['captured_at']) < at - timedelta(days=7):
            reason = 'stale_reference'
        key = (item['basis'], item['unit'], item['period_start'], item['period_end'])
        if reason:
            excluded.append({'id': row['id'], 'source_id': item['source_id'], 'reason': reason})
            continue
        if item['source_id'] not in groups[key]:
            groups[key][item['source_id']] = {'id': row['id'], **item, 'group': method_groups[item['source_id']]}
    cohorts = []
    for key, readings in sorted(groups.items(), key=lambda x: str(x[0])):
        items = list(readings.values())
        sizes = {g: sum(r['group'] == g for r in items) for g in {r['group'] for r in items}}
        for item in items:
            item['weight'] = 1 / sizes[item['group']]
        center = weighted_median([(x['value'], x['weight']) for x in items])
        values = [x['value'] for x in items]
        cohort = {'basis': key[0], 'unit': key[1], 'period_start': key[2], 'period_end': key[3],
            'center': center, 'mean': mean(values), 'median': median(values), 'minimum': min(values), 'maximum': max(values),
            'source_count': len(items), 'group_count': len(sizes), 'readings': items,
            'status': 'single_source' if len(sizes) < 2 else 'provisional_consensus',
            'range_kind': 'source_disagreement_not_confidence', 'independence': 'grouping_is_conservative_not_proven',
            'training_eligible': len(sizes) >= 2 and all(registry.permission(x['source_id'], 'training') for x in items)}
        cohort['fingerprint'] = store.digest(cohort)
        cohorts.append(cohort)
    result = {'version': VERSION, 'listing_id': listing_id, 'as_of': at.isoformat(), 'cohorts': cohorts, 'excluded': excluded}
    result['fingerprint'] = store.digest(result)
    if save:
        con.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?,?)', (result['fingerprint'], listing_id, 'consensus', at.isoformat(), store.encoded(result)))
    return result
