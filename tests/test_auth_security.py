from __future__ import annotations

import uuid

import pytest
from redis import Redis

from infrasentinel.auth import enforce_rate_limit
from infrasentinel.config import get_settings
from infrasentinel.errors import InfraError


def test_redis_rate_limit_and_outage_fail_closed() -> None:
    settings = get_settings()
    key = f"infrasentinel:test:{uuid.uuid4().hex}"
    redis_url = settings.redis_url.get_secret_value()
    enforce_rate_limit(redis_url, key, limit=2, window_seconds=60)
    client = Redis.from_url(redis_url)
    assert 0 < client.ttl(key) <= 60
    client.close()
    enforce_rate_limit(redis_url, key, limit=2, window_seconds=60)
    with pytest.raises(InfraError, match="auth.rate_limited"):
        enforce_rate_limit(redis_url, key, limit=2, window_seconds=60)
    with pytest.raises(InfraError, match="auth.rate_limit_unavailable"):
        enforce_rate_limit("redis://127.0.0.1:1/0", key, limit=2, window_seconds=60)
