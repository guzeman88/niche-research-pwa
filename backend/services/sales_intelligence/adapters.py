"""Supported HTTPS canonical-export contract, enabled only by protected evidence.

There are no guessed provider endpoints. A source must document this contract and
have its exact approved endpoint recorded before network dispatch is possible.
"""
import ipaddress
import json
import socket
from datetime import timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
import httpx
from . import ingestion, quotas, registry, store


def configuration(source_id):
    grant = registry.grants().get(source_id, {})
    if not registry.permission(source_id, 'automated') or not registry.permission(source_id, 'storage'):
        raise ValueError('Source automated collection and storage are not eligible')
    if grant.get('adapter') != 'canonical_json_v1' or not grant.get('endpoint_reference'):
        raise ValueError('A documented supported export/API contract is required')
    endpoint = grant.get('endpoint', '')
    parsed = urlparse(endpoint)
    seed = next((s for s in registry.SEEDS if s[0] == source_id), None)
    host = urlparse(seed[5]).hostname if seed else None
    if (parsed.scheme != 'https' or not parsed.hostname or not host or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.port not in (None, 443)
            or not (parsed.hostname == host or parsed.hostname.endswith('.' + host))):
        raise ValueError('Endpoint must be an HTTPS URL on the documented source host, without credentials or query')
    return grant


def public_addresses(host):
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('Source host must resolve to public addresses')


def fetch(source_id, listing_id, job_id):
    if not str(listing_id).isdecimal():
        raise ValueError('Use a numeric listing ID')
    grant = configuration(source_id)
    if registry.source(source_id)['paused']:
        raise ValueError('Source collection is paused')
    with store.database() as con:
        health = store.get_control(con, 'source_health:' + source_id, {})
        if store.get_control(con, 'paused', False):
            raise ValueError('Research worker is paused')
    if health.get('retry_at') and store.stamp(health['retry_at']) > store.now():
        raise ValueError('Source is in a persisted cooldown; inspect its health before retrying')
    endpoint = grant['endpoint']
    public_addresses(urlparse(endpoint).hostname)
    secret_path = store.root() / 'credentials.json'
    secrets = json.loads(secret_path.read_text()) if secret_path.is_file() else {}
    headers = secrets.get(source_id, {}).get('headers', {})
    if any(k.lower() not in ('authorization', 'x-api-key', 'x-apikey') for k in headers):
        raise ValueError('Only scoped API authentication headers are supported')
    with store.database(True) as con:
        if store.get_control(con, 'paused', False) or not registry.permission(source_id, 'automated'):
            raise ValueError('Collection paused or access changed before reservation')
        if con.execute('SELECT 1 FROM quota_events WHERE id=?', (job_id,)).fetchone():
            raise ValueError('This request was already reserved; reconcile before retrying')
        quotas.reserve(con, source_id, job_id, grant.get('cost_per_request', 1))
    try:
        # No redirect, proxy/session-cookie fallback or retries that spend hidden quota.
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
            with client.stream('GET', endpoint, params={'listing_id': listing_id}, headers=headers) as response:
                response.raise_for_status()
                content = bytearray()
                for block in response.iter_bytes():
                    content.extend(block)
                    if len(content) > ingestion.MAX_BYTES:
                        raise ValueError('Provider response exceeds import budget')
        payload = json.loads(content)
        rows = payload.get('observations') if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or any(str(r.get('listing_id')) != str(listing_id) for r in rows if isinstance(r, dict)):
            raise ValueError('Provider response does not match the requested listing/export contract')
        data = {'source_id': source_id, 'format': 'json', 'content': json.dumps(rows)}
        preview = ingestion.preview(data)
        result = ingestion.commit({**data, 'expected_fingerprint': preview['fingerprint']})
        with store.database(True) as con:
            con.execute("UPDATE quota_events SET status='completed' WHERE id=?", (job_id,))
            store.set_control(con, 'source_health:' + source_id, {'status': 'ok', 'last_success': store.now().isoformat(),
                'last_output_rows': result['inserted'], 'retry_at': None})
        return result
    except BaseException as exc:
        at = store.now()
        reason, delay = 'invalid_or_unavailable_output', 3600
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code
            reason = 'rate_limited' if code == 429 else 'access_denied' if code in (401, 403) else 'provider_http_error'
            delay = 86400 if code in (401, 403) else 3600
            if code == 429:
                header = exc.response.headers.get('Retry-After', '')
                try:
                    delay = float(header)
                except ValueError:
                    try:
                        delay = (parsedate_to_datetime(header) - at).total_seconds()
                    except (ValueError, TypeError, OverflowError):
                        delay = 3600
                delay = min(86400, max(900, delay))
        elif isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
            reason, delay = 'network_or_charge_unknown', 900
        with store.database(True) as con:
            con.execute("UPDATE quota_events SET status='failed_or_charge_unknown' WHERE id=?", (job_id,))
            previous = store.get_control(con, 'source_health:' + source_id, {})
            store.set_control(con, 'source_health:' + source_id, {**previous, 'status': reason,
                'last_failure': at.isoformat(), 'retry_at': (at + timedelta(seconds=delay)).isoformat()})
        raise
