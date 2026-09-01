from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import digest_session_token, session_is_expired
from .config import Settings, get_settings
from .database import get_session
from .errors import InfraError
from .models import AuthSession, User, UserRole, UserStatus


@dataclass
class AuthContext:
    user: User
    session: AuthSession


DbDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def get_auth_context(
    request: Request,
    db: DbDep,
    settings: SettingsDep,
) -> AuthContext:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise InfraError(401, "auth.required")
    auth_session = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == digest_session_token(token))
    )
    if auth_session is None or auth_session.revoked_at is not None:
        raise InfraError(401, "auth.required")
    now = datetime.now(UTC)
    if session_is_expired(
        last_seen_at=auth_session.last_seen_at,
        expires_at=auth_session.expires_at,
        idle_minutes=settings.session_idle_minutes,
        now=now,
    ):
        auth_session.revoked_at = now
        db.commit()
        raise InfraError(401, "auth.required")
    user = db.get(User, auth_session.user_id)
    if user is None or user.status != UserStatus.ENABLED:
        auth_session.revoked_at = now
        db.commit()
        raise InfraError(401, "auth.required")
    if now - auth_session.last_seen_at >= timedelta(minutes=settings.session_touch_minutes):
        auth_session.last_seen_at = now
        db.commit()
    return AuthContext(user=user, session=auth_session)


AuthDep = Annotated[AuthContext, Depends(get_auth_context)]


def require_admin(context: AuthDep) -> AuthContext:
    if context.user.role != UserRole.ADMIN:
        raise InfraError(403, "auth.forbidden")
    return context


AdminDep = Annotated[AuthContext, Depends(require_admin)]


def require_same_origin(request: Request, settings: SettingsDep) -> None:
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        raise InfraError(403, "auth.cross_origin_denied")
    parsed = urlsplit(source)
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    allowed = {item.strip().rstrip("/") for item in settings.allowed_origins.split(",")}
    if origin not in allowed:
        raise InfraError(403, "auth.cross_origin_denied")
