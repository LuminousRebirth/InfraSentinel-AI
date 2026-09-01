from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from pwdlib import PasswordHash
from redis import Redis
from redis.exceptions import RedisError

from .errors import InfraError

PASSWORD_HASH = PasswordHash.recommended()
DUMMY_HASH = PASSWORD_HASH.hash("infrasentinel-dummy-password")
RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


def hash_password(password: str) -> str:
    return PASSWORD_HASH.hash(password)


def verify_password(password: str, encoded_hash: str) -> tuple[bool, str | None]:
    try:
        return PASSWORD_HASH.verify_and_update(password, encoded_hash)
    except Exception:
        return False, None


def run_dummy_verification(password: str) -> None:
    PASSWORD_HASH.verify(password, DUMMY_HASH)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def digest_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_deadlines(
    *,
    now: datetime | None = None,
    idle_minutes: int = 30,
    absolute_days: int = 7,
) -> tuple[datetime, datetime]:
    current = now or datetime.now(UTC)
    return current + timedelta(minutes=idle_minutes), current + timedelta(days=absolute_days)


def session_is_expired(
    *,
    last_seen_at: datetime,
    expires_at: datetime,
    idle_minutes: int,
    now: datetime | None = None,
) -> bool:
    current = now or datetime.now(UTC)
    return current >= expires_at or current >= last_seen_at + timedelta(minutes=idle_minutes)


def rate_limit_key(prefix: str, source_ip: str, identifier: str = "") -> str:
    subject = hashlib.sha256(f"{source_ip}|{identifier}".encode()).hexdigest()
    return f"infrasentinel:rate:{prefix}:{subject}"


def enforce_rate_limit(redis_url: str, key: str, *, limit: int, window_seconds: int) -> None:
    client = Redis.from_url(redis_url, decode_responses=True, socket_timeout=2)
    try:
        count = int(client.eval(RATE_LIMIT_SCRIPT, 1, key, window_seconds))
        if count > limit:
            raise InfraError(429, "auth.rate_limited")
    except InfraError:
        raise
    except RedisError as exc:
        raise InfraError(503, "auth.rate_limit_unavailable") from exc
    finally:
        client.close()
