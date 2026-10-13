"""Bounded batch-scoped HTTP pools; provider credentials never cross pools."""
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
import httpx

_POOLS = ContextVar('collection_http_pools', default={})


def transport(name):
    return _POOLS.get().get(name)


@contextmanager
def pooled_transports():
    with ExitStack() as stack:
        pools = {name: stack.enter_context(httpx.Client(timeout=timeout, follow_redirects=name == 'etsy'))
                 for name, timeout in [('etsy', 20), ('suggest', 8), ('mirror', 10)]}
        token = _POOLS.set(pools)
        try:
            yield
        finally:
            _POOLS.reset(token)
