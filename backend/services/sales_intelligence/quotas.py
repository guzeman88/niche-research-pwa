"""Durable reservations; unknown charge status stays spent, and restart never resets it."""
from zoneinfo import ZoneInfo
from datetime import datetime, time, timedelta, timezone
from . import registry, store


def state(con, source_id, at=None):
    at = at or store.now()
    if not registry.permission(source_id, 'automated', at):
        raise ValueError('Automated source access is not recorded or has expired')
    grant = registry.grants()[source_id]
    quota = grant.get('quota', {})
    limit = quota.get('limit')
    if isinstance(limit, bool) or not isinstance(limit, (int, float)) or not 0 < limit <= 1e6:
        raise ValueError('A verified finite free allowance is required')
    local = at.astimezone(ZoneInfo(quota.get('timezone', 'UTC')))
    period = quota.get('period')
    if period == 'daily':
        bucket = local.date().isoformat()
        reset = datetime.combine(local.date() + timedelta(days=1), time(), local.tzinfo)
    elif period == 'monthly':
        bucket = local.strftime('%Y-%m')
        reset = datetime(local.year + (local.month == 12), local.month % 12 + 1, 1, tzinfo=local.tzinfo)
    elif period == 'one_time':
        bucket = 'one_time'
        reset = None
    else:
        raise ValueError('Unknown allowance reset rule')
    account = grant['account_ref']
    # Shared quota group prevents duplicate brands sharing one account from overspending.
    group = next((s[3] for s in registry.SEEDS if s[0] == source_id), source_id)
    quota_source = grant.get('quota_group', group)
    used = con.execute('SELECT coalesce(sum(cost),0) FROM quota_events WHERE source_id=? AND account_ref=? AND bucket=?',
                       (quota_source, account, bucket)).fetchone()[0]
    return {'bucket': bucket, 'remaining': max(0, limit - used), 'used': used, 'limit': limit,
            'period': period, 'timezone': quota.get('timezone', 'UTC'),
            'next_reset': reset.astimezone(timezone.utc).isoformat() if reset else None,
            'quota_source': quota_source, 'account_ref': account}


def reserve(con, source_id, identity, cost=1, at=None):
    at = at or store.now()
    current = state(con, source_id, at)
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not 0 < cost <= current['remaining']:
        raise ValueError('Free allowance exhausted; wait for its documented reset')
    con.execute('INSERT INTO quota_events VALUES(?,?,?,?,?,?,?)', (identity, current['quota_source'], current['account_ref'], current['bucket'], cost, at.isoformat(), 'reserved'))
    return {'bucket': current['bucket'], 'remaining': current['remaining'] - cost}


def eligible_free_account(source_id):
    grant = registry.grants().get(source_id, {})
    return bool(grant.get('free_only') is True and registry.permission(source_id, 'automated'))
