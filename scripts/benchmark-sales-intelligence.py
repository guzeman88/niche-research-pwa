"""Isolated synthetic workload; never imports the installed ledger or native data."""
from datetime import timedelta
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
directory = Path(tempfile.mkdtemp(prefix='etgen-intelligence-benchmark-'))
os.environ['SALES_INTELLIGENCE_ROOT'] = str(directory / 'archive')
os.environ['VALIDATION_DB_PATH'] = str(directory / 'absent-ledger.sqlite')
os.environ['APP_KEYWORD_FEED_ROOT'] = str(directory / 'absent-native')
from services.sales_intelligence import store, service, registry  # noqa: E402

at = store.now() - timedelta(minutes=5)
start = (at - timedelta(days=30)).isoformat()
end = at.isoformat()
store.counts()
(store.root() / 'access.json').write_text(json.dumps({s: {'reference': 'Synthetic benchmark only', 'account_ref': 'fixture',
    'issued_at': (at - timedelta(days=1)).isoformat(), 'expires_at': (at + timedelta(days=1)).isoformat(),
    'free_only': True, 'capabilities': ['storage', 'comparison']} for s in ('muadzo', 'hive')}))
began = time.perf_counter()
with store.database(True) as con:
    con.execute('INSERT INTO artifacts VALUES(?,?,?,?)', ('benchmark', 'muadzo', end, '{}'))
    for first in range(0, 100000, 1000):
        for i in range(first, first + 1000):
            store.add_metadata(con, {'listing_id': str(1000000 + i), 'title': f'Synthetic benchmark product {i}',
                'shop': 'Synthetic benchmark shop', 'shop_id': str(1000 + i // 10), 'category': str(i % 20),
                'product_type': 'digital', 'captured_at': end, 'available_at': end, 'price': 8, 'currency': 'USD'})
    for first in range(0, 1000000, 1000):
        batch = []
        for i in range(first, first + 1000):
            listing = str(1000000 + i // 10)
            source = 'muadzo' if i % 2 else 'hive'
            payload = {'source_id': source, 'listing_id': listing, 'metric': 'estimated_sales', 'value': i % 50,
                'basis': 'period', 'unit': 'purchases', 'period_start': start, 'period_end': end, 'captured_at': end,
                'available_at': end, 'precision': 'point', 'status': 'observed', 'source_ref': 'Synthetic benchmark',
                'provider_updated_at': None}
            batch.append((f'{i:064x}', source, listing, 'estimated_sales', 'period', 'purchases', end, end, start, end,
                'benchmark', None, store.encoded(payload)))
        con.executemany('INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', batch)
populate_seconds = time.perf_counter() - began

measurements = {}
for name, action in [('browse', lambda: service.overview()), ('search', lambda: service.overview('product 99')),
                     ('comparison', lambda: service.comparison('1000000'))]:
    times = []
    for _ in range(20):
        began = time.perf_counter()
        action()
        times.append((time.perf_counter() - began) * 1000)
    measurements[name] = {'p50_ms': statistics.median(times), 'p95_ms': sorted(times)[18], 'runs': len(times)}
result = {'synthetic': True, 'listings': 100000, 'observations': 1000000, 'external_requests': 0,
    'machine': platform.platform(), 'cpu': platform.processor(), 'populate_seconds': populate_seconds,
    'database_bytes': (store.root() / 'intelligence.sqlite').stat().st_size, 'measurements': measurements,
    'all_browse_comparison_p95_under_1s': all(v['p95_ms'] < 1000 for v in measurements.values())}
(directory / 'benchmark.json').write_text(json.dumps(result, indent=2))
print(json.dumps({'evidence': str(directory / 'benchmark.json'), **result}, indent=2))
