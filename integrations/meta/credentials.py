"""Per-request Meta credentials; never mutate process environment across tenants."""
from contextlib import contextmanager
from contextvars import ContextVar
import os

_active_key=ContextVar('frontiersight_meta_key',default=None)


def api_key():
    return _active_key.get() or os.environ.get('MODEL_API_KEY','').strip()


@contextmanager
def using_key(value):
    token=_active_key.set(value)
    try:yield
    finally:_active_key.reset(token)
