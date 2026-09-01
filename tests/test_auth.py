from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from infrasentinel.auth import (
    digest_session_token,
    hash_password,
    new_session_token,
    session_is_expired,
    verify_password,
)
from infrasentinel.schemas import PasswordChange, RegisterRequest


def test_password_and_session_primitives() -> None:
    encoded = hash_password("correct horse battery staple")
    valid, _ = verify_password("correct horse battery staple", encoded)
    invalid, _ = verify_password("wrong password", encoded)
    token = new_session_token()

    assert valid is True
    assert invalid is False
    assert token not in digest_session_token(token)
    assert len(digest_session_token(token)) == 64


def test_session_idle_and_absolute_expiry() -> None:
    now = datetime.now(UTC)
    assert session_is_expired(
        last_seen_at=now - timedelta(minutes=31),
        expires_at=now + timedelta(days=1),
        idle_minutes=30,
        now=now,
    )
    assert not session_is_expired(
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        idle_minutes=30,
        now=now,
    )


def test_password_policy_accepts_six_characters_and_rejects_five() -> None:
    registration = RegisterRequest(
        email="six@example.com",
        username="six-user",
        display_name="Six",
        password="123456",
    )
    change = PasswordChange(current_password="old", new_password="123456")

    assert registration.password == "123456"
    assert change.new_password == "123456"
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="five@example.com",
            username="five-user",
            display_name="Five",
            password="12345",
        )
