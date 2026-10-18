"""Frozen teacher datasets and a distinct consensus-student model lane."""
from datetime import timedelta
import json
import math
from statistics import median
from . import consensus, features, registry, store
from services.sales_model import ridge, predict

VERSION = 'consensus-student-v1'


def active_key(model):
    prefix = 'active:outcome:' if model.get('lane') == 'actual_outcome' else 'active:'
    return f"{prefix}{model['days']}:{model['unit']}"


def persist_dataset(result):
    identity = store.digest(result)
    with store.database(True) as con:
        con.execute('INSERT OR IGNORE INTO datasets VALUES(?,?,?)', (identity, store.now().isoformat(), store.encoded(result)))
    return {'id': identity, **result}


def outcome_dataset(days=30, unit='purchases'):
    if days not in (7, 30) or unit not in ('purchases', 'units'):
        raise ValueError('Choose a separate 7/30-day purchases or units target')
    with store.database() as con:
        con.execute('BEGIN')
        samples = []
        for row in con.execute('SELECT id,payload FROM outcomes ORDER BY period_end LIMIT 10000'):
            item = json.loads(row['payload'])
            if item['unit'] != unit or not item.get('shop_id'):
                continue
            start, end = store.stamp(item['period_start']), store.stamp(item['period_end'])
            if abs((end - start).total_seconds() - days * 86400) > 1:
                continue
            feature = features.snapshot(con, item['listing_id'], end.isoformat())
            if (not feature or feature['metadata'].get('shop_id') != item['shop_id']
                    or store.stamp(feature['metadata']['captured_at']) < end - timedelta(days=7)):
                continue
            samples.append({'id': row['id'], 'listing_id': item['listing_id'], 'shop': item['shop_id'],
                'start': start.isoformat(), 'end': end.isoformat(), 'label': item['actual'],
                'feature': feature, 'teacher_sources': []})
        result = {'feature_version': features.VERSION, 'days': days, 'unit': unit, 'objective': 'actual_sales',
            'samples': samples, 'policy_fingerprint': store.digest({}),
            'correction_epoch': store.get_control(con, 'outcome_epoch', 0)}
    return persist_dataset(result)


def dataset(days=30, unit='purchases'):
    if days not in (7, 30) or unit not in ('purchases', 'units'):
        raise ValueError('Train a separate 7/30-day purchases or units model')
    samples = {}
    with store.database() as con:
        con.execute('BEGIN')
        captures = con.execute("SELECT DISTINCT listing_id,available_at FROM observations WHERE metric='estimated_sales' AND basis='period' ORDER BY available_at DESC LIMIT 5000").fetchall()
        for item in captures:
            report = consensus.build(con, item['listing_id'], item['available_at'])
            for cohort in report['cohorts']:
                if not cohort['training_eligible'] or cohort['basis'] != 'period' or cohort['unit'] != unit:
                    continue
                start, end = store.stamp(cohort['period_start']), store.stamp(cohort['period_end'])
                if abs((end - start).total_seconds() - days * 86400) > 1:
                    continue
                feature = features.snapshot(con, item['listing_id'], end.isoformat())
                if not feature or not feature['metadata'].get('shop_id') or store.stamp(feature['metadata']['captured_at']) < end - timedelta(days=7):
                    continue
                key = (item['listing_id'], cohort['period_start'], cohort['period_end'])
                # Descending availability means the first currently eligible version wins.
                samples.setdefault(key, {'id': store.digest(key), 'listing_id': item['listing_id'],
                    'shop': feature['metadata']['shop_id'], 'start': start.isoformat(), 'end': end.isoformat(),
                    'label': cohort['center'], 'label_fingerprint': cohort['fingerprint'],
                    'teacher_sources': sorted({r['source_id'] for r in cohort['readings']}), 'feature': feature})
        values, last = [], {}
        for item in sorted(samples.values(), key=lambda x: (x['start'], x['listing_id'])):
            if item['start'] < last.get(item['listing_id'], ''):
                continue
            values.append(item)
            last[item['listing_id']] = item['end']
        result = {'feature_version': features.VERSION, 'consensus_version': consensus.VERSION,
                  'days': days, 'unit': unit, 'samples': values,
                  'source_policy': {s: registry.grants().get(s, {}) for item in values for s in item['teacher_sources']}}
        # Protected policy content is used only in the hash, never returned/exported.
        policy_fingerprint = store.digest(result.pop('source_policy'))
        result['policy_fingerprint'] = policy_fingerprint
        result['correction_epoch'] = store.get_control(con, 'correction_epoch', 0)
    return persist_dataset(result)


def split(samples, actual=False):
    shops = sorted({r['shop'] for r in samples}, key=store.digest)
    if actual and (len(samples) < 200 or len(shops) < 25):
        raise ValueError('Outcome model needs 200 nonoverlapping windows across 25 canonical shops, including later zero sellers; minimums do not establish general accuracy')
    if len(samples) < 100 or len(shops) < 20:
        raise ValueError('Experimental student needs 100 nonoverlapping listing/window labels across 20 shops; this is not proof of accuracy')
    count = max(5 if actual else 3, len(shops) // 5)
    test_shops = set(shops[:count])
    validation_shops = set(shops[count:2 * count])
    boundaries = sorted({r['start'] for r in samples})
    for test_start in reversed(boundaries):
        tests = [r for r in samples if r['shop'] in test_shops and r['start'] >= test_start]
        if len(tests) < (30 if actual else 15):
            continue
        for valid_start in reversed([b for b in boundaries if b < test_start]):
            validation = [r for r in samples if r['shop'] in validation_shops and r['start'] >= valid_start and r['end'] <= test_start]
            training = [r for r in samples if r['shop'] not in test_shops | validation_shops and r['end'] <= valid_start]
            if (len(training) >= (80 if actual else 40) and len(validation) >= (30 if actual else 15)
                    and (not actual or (len({x['shop'] for x in tests}) >= 5 and len({x['shop'] for x in validation}) >= 5))):
                return training, validation, tests
    raise ValueError('Need disjoint shops and earlier training, intermediate validation and later test periods without overlapping target windows')


def metrics(rows, predictions, baseline):
    errors = [abs(x['label'] - y) for x, y in zip(rows, predictions)]
    return {'cases': len(rows), 'shops': len({x['shop'] for x in rows}),
            'mae': sum(errors) / len(errors), 'median_absolute_error': median(errors),
            'log_mae': sum(abs(math.log1p(x['label']) - math.log1p(y)) for x, y in zip(rows, predictions)) / len(rows),
            'baseline_mae': sum(abs(x['label'] - baseline) for x in rows) / len(rows),
            'bias': sum(y - x['label'] for x, y in zip(rows, predictions)) / len(rows),
            'zero_cases': sum(x['label'] == 0 for x in rows),
            'objective': 'provider_consensus_agreement_not_actual_sales_accuracy'}


def guardrails(rows, predictions, baseline):
    """Predeclared actual-outcome gates, fixed before any validation/test inspection."""
    bias = sum(y - x['label'] for x, y in zip(rows, predictions)) / len(rows)
    zeros = [y for x, y in zip(rows, predictions) if x['label'] == 0]
    slices = {}
    for category in {x['feature']['metadata'].get('category', '') for x in rows}:
        pairs = [(x, y) for x, y in zip(rows, predictions) if x['feature']['metadata'].get('category', '') == category]
        if len(pairs) < 10:
            continue
        mae = sum(abs(x['label'] - y) for x, y in pairs) / len(pairs)
        base = sum(abs(x['label'] - baseline) for x, _ in pairs) / len(pairs)
        slices[category] = {'cases': len(pairs), 'mae': mae, 'baseline_mae': base, 'passed': mae <= max(1, base * 1.1)}
    result = {'bias': bias, 'bias_limit': max(1, sum(x['label'] for x in rows) / len(rows) * .2),
        'zero_cases': len(zeros), 'zero_mean_prediction': sum(zeros) / len(zeros) if zeros else None,
        'zero_limit': 1, 'minimum_zero_cases': 10, 'category_slices': slices}
    result['passed'] = (abs(bias) <= result['bias_limit'] and len(zeros) >= 10
        and result['zero_mean_prediction'] <= 1 and bool(slices) and all(s['passed'] for s in slices.values()))
    return result


def fit(days=30, unit='purchases', objective='consensus'):
    if objective not in ('consensus', 'actual'):
        raise ValueError('Unknown model objective')
    actual = objective == 'actual'
    frozen = outcome_dataset(days, unit) if actual else dataset(days, unit)
    try:
        train, validation, tests = split(frozen['samples'], actual=actual)
    except ValueError as exc:
        return {'status': 'insufficient_data', 'reason': str(exc), 'dataset_id': frozen['id'],
                'cases': len(frozen['samples']), 'shops': len({s['shop'] for s in frozen['samples']})}
    coefficients = ridge([(x['feature']['values'], math.log1p(x['label'])) for x in train])
    artifact = {'coefficients': coefficients}
    baseline = median(x['label'] for x in train)
    valid_predictions = [predict(artifact, x['feature']['values']) for x in validation]
    test_predictions = [predict(artifact, x['feature']['values']) for x in tests]
    report = metrics(tests, test_predictions, baseline)
    validation_report = metrics(validation, valid_predictions, baseline)
    # Model/config is fixed before evaluating tests; these results cannot tune it.
    qualified = report['mae'] < report['baseline_mae'] and validation_report['mae'] < validation_report['baseline_mae']
    if actual:
        report['objective'] = validation_report['objective'] = 'actual_sales_accuracy_on_retained_outcomes'
        report['guardrails'] = guardrails(tests, test_predictions, baseline)
        validation_report['guardrails'] = guardrails(validation, valid_predictions, baseline)
        qualified = qualified and report['guardrails']['passed'] and validation_report['guardrails']['passed']
    artifact.update(version=VERSION, lane='actual_outcome' if actual else 'consensus_student', days=days, unit=unit, dataset_id=frozen['id'],
                    feature_version=features.VERSION, policy_fingerprint=frozen['policy_fingerprint'], correction_epoch=frozen['correction_epoch'],
                    training_cases=len(train), baseline=baseline, validation=validation_report, evaluation=report,
                    source_ids=sorted({s for r in frozen['samples'] for s in r['teacher_sources']}),
                    train_ids=[x['id'] for x in train], validation_ids=[x['id'] for x in validation], test_ids=[x['id'] for x in tests],
                    test_results=[{'listing_id': x['listing_id'], 'teacher': x['label'], 'prediction': y} for x, y in zip(tests, test_predictions)],
                    categories=sorted({x['feature']['metadata'].get('category', '') for x in train}),
                    types=sorted({x['feature']['metadata'].get('product_type', 'unknown') for x in train}),
                    trained_at=store.now().isoformat(), qualified=qualified, actual_accuracy=report if actual else None)
    identity = store.digest(artifact)
    with store.database(True) as con:
        con.execute('INSERT OR IGNORE INTO models VALUES(?,?,?,?)',
                    (identity, artifact['trained_at'], ('qualified_outcome_tested' if actual else 'qualified_experimental') if qualified else 'retained_unqualified', store.encoded(artifact)))
        store.set_control(con, 'last_train', {'at': artifact['trained_at'], 'id': identity, 'status': 'completed'})
        store.audit(con, 'model_fit', {'id': identity, 'dataset': frozen['id'], 'qualified_experimental': qualified})
    return {'id': identity, **artifact}


def eligible(artifact):
    if artifact.get('feature_version') != features.VERSION:
        return False
    with store.database() as con:
        epoch_key = 'outcome_epoch' if artifact.get('lane') == 'actual_outcome' else 'correction_epoch'
        if artifact.get('correction_epoch') != store.get_control(con, epoch_key, 0):
            return False
    if not all(registry.permission(s, 'training') for s in artifact.get('source_ids', [])):
        return False
    policies = {s: registry.grants().get(s, {}) for s in artifact.get('source_ids', [])}
    return store.digest(policies) == artifact.get('policy_fingerprint')


def activate(identity, rollback=False):
    with store.database(True) as con:
        row = con.execute('SELECT payload FROM models WHERE id=?', (identity,)).fetchone()
        if not row:
            raise ValueError('Model not found')
        artifact = json.loads(row[0])
        if not artifact.get('qualified') or not eligible(artifact):
            raise ValueError('Model is unqualified, stale or no longer eligible for use')
        key = active_key(artifact)
        previous = store.get_control(con, key)
        if previous:
            store.set_control(con, 'previous:' + key, previous)
        store.set_control(con, key, identity)
        store.audit(con, 'model_rollback' if rollback else 'model_activate', {'id': identity, 'previous': previous, 'lane': artifact['lane']})
        return {'active': identity, 'previous': previous, 'lane': artifact['lane'], 'actual_accuracy': artifact['actual_accuracy']}


def rollback(days=30, unit='purchases', lane='consensus_student'):
    with store.database() as con:
        previous = store.get_control(con, 'previous:' + active_key({'lane': lane, 'days': days, 'unit': unit}))
    if not previous:
        raise ValueError('No previously active model is available')
    return activate(previous, True)


def list_models():
    with store.database() as con:
        rows = con.execute('SELECT * FROM models ORDER BY created_at DESC LIMIT 50').fetchall()
        result = []
        for row in rows:
            item = json.loads(row['payload'])
            active = store.get_control(con, active_key(item)) == row['id']
            result.append({'id': row['id'], 'created_at': row['created_at'], 'status': row['status'],
                           'active': active, 'eligible': eligible(item), 'model': item,
                           'actual_evaluation': store.get_control(con, 'actual_evaluation:' + row['id'])})
        return result


def prediction(listing_id, days=30, unit='purchases', as_of=None, lane='consensus_student'):
    at = store.stamp(as_of) if as_of else store.now()
    if at > store.now():
        raise ValueError('Predictions estimate completed historical periods, not future cutoffs')
    with store.database() as con:
        con.execute('BEGIN')
        identity = store.get_control(con, active_key({'lane': lane, 'days': days, 'unit': unit}))
        row = con.execute('SELECT payload FROM models WHERE id=?', (identity,)).fetchone() if identity else None
        if not row:
            return {'status': 'no_active_model', 'value': None}
        model = json.loads(row[0])
        if not eligible(model) or store.stamp(model['trained_at']) > at:
            return {'status': 'stale_or_unavailable_as_of', 'value': None}
        vector = features.snapshot(con, listing_id, at.isoformat())
        if not vector:
            return {'status': 'metadata_unknown', 'value': None}
        if store.stamp(vector['metadata']['captured_at']) < at - timedelta(days=7):
            return {'status': 'metadata_stale', 'value': None}
        if (vector['metadata'].get('category', '') not in model['categories'] or
                vector['metadata'].get('product_type', 'unknown') not in model['types']):
            return {'status': 'outside_training_domain', 'value': None}
        result = {'listing_id': listing_id, 'model_id': identity, 'as_of': at.isoformat(),
                  'period_start': (at - timedelta(days=days)).isoformat(), 'period_end': at.isoformat(),
                  'days': days, 'unit': unit, 'value': predict(model, vector['values']),
                  'status': 'outcome_tested_estimate' if lane == 'actual_outcome' else 'experimental_consensus_prediction',
                  'actual_accuracy': model.get('actual_accuracy'),
                  'feature_fingerprint': vector['fingerprint'], 'range': None}
        ident = store.digest(result)
    with store.database(True) as con:
        if store.get_control(con, active_key(model)) != identity or not eligible(model):
            return {'status': 'model_changed_during_prediction', 'value': None}
        con.execute('INSERT OR IGNORE INTO predictions VALUES(?,?,?,?,?)',
                    (ident, listing_id, identity, at.isoformat(), store.encoded(result)))
        return result


def evaluate_actual(identity):
    """Audit on later outcome windows; never fit or claim validation on training shops."""
    with store.database() as con:
        con.execute('BEGIN')
        model_row = con.execute('SELECT payload FROM models WHERE id=?', (identity,)).fetchone()
        if not model_row:
            raise ValueError('Model not found')
        model = json.loads(model_row[0])
        if not eligible(model):
            raise ValueError('Model is stale or no longer eligible for evaluation')
        frozen = json.loads(con.execute('SELECT payload FROM datasets WHERE id=?', (model['dataset_id'],)).fetchone()[0])
        trained_shops = {x['shop'] for x in frozen['samples'] if x['id'] in model['train_ids'] + model['validation_ids']}
        results = []
        for row in con.execute('SELECT id,payload FROM outcomes ORDER BY period_end'):
            item = json.loads(row['payload'])
            if item['unit'] != model['unit'] or item.get('shop_id') in trained_shops or not item.get('shop_id') or item['period_start'] <= model['trained_at']:
                continue
            if abs((store.stamp(item['period_end']) - store.stamp(item['period_start'])).total_seconds() - model['days'] * 86400) > 1:
                continue
            vector = features.snapshot(con, item['listing_id'], item['period_end'])
            if vector and vector['metadata'].get('shop_id') == item['shop_id']:
                results.append({'outcome_id': row['id'], 'shop': item['shop_id'], 'actual': item['actual'], 'prediction': predict(model, vector['values'])})
        report = {'model_id': identity, 'objective': 'actual_sales_audit', 'cases': len(results),
                  'shops': len({x['shop'] for x in results}), 'results': results,
                  'status': 'insufficient_outcomes' if len(results) < 30 or len({x['shop'] for x in results}) < 5 else 'audit_available_not_auto_promotion',
                  'mae': sum(abs(x['actual'] - x['prediction']) for x in results) / len(results) if results else None,
                  'baseline_mae': sum(abs(x['actual'] - model['baseline']) for x in results) / len(results) if results else None,
                  'actual_promotion_enabled': False}
    with store.database(True) as con:
        store.set_control(con, 'actual_evaluation:' + identity, report)
    return report
