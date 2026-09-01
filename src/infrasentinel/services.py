from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import (
    digest_session_token,
    hash_password,
    new_session_token,
    run_dummy_verification,
    session_deadlines,
    verify_password,
)
from .errors import InfraError, redact_secrets
from .models import (
    AuditEvent,
    AuditResult,
    AuthSession,
    Project,
    ProjectMembership,
    User,
    UserRole,
    UserStatus,
)
from .schemas import ProjectCreate, RegisterRequest, UserStatusUpdate


def record_audit(
    db: Session,
    *,
    action: str,
    target_type: str,
    actor_id: uuid.UUID | None = None,
    target_id: uuid.UUID | None = None,
    source_ip: str | None = None,
    user_agent: str | None = None,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    result: AuditResult = AuditResult.SUCCESS,
    detail: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_id=actor_id,
        source_ip=source_ip,
        user_agent=(user_agent or "")[:512] or None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_state=redact_secrets(before_state),
        after_state=redact_secrets(after_state),
        result=result,
        detail=(detail or "")[:1000] or None,
    )
    db.add(event)
    return event


def register_user(
    db: Session,
    payload: RegisterRequest,
    *,
    source_ip: str | None,
    user_agent: str | None,
) -> User:
    existing = db.scalar(
        select(User.id).where(or_(User.email == payload.email, User.username == payload.username))
    )
    if existing:
        raise InfraError(409, "auth.identity_conflict")
    user = User(
        email=payload.email,
        username=payload.username,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role=UserRole.USER,
        status=UserStatus.PENDING,
        locale=payload.locale,
    )
    db.add(user)
    try:
        db.flush()
        record_audit(
            db,
            action="auth.register",
            target_type="user",
            target_id=user.id,
            source_ip=source_ip,
            user_agent=user_agent,
            after_state={"status": user.status.value, "role": user.role.value},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise InfraError(409, "auth.identity_conflict") from exc
    db.refresh(user)
    return user


def bootstrap_admin(
    db: Session,
    *,
    email: str,
    username: str,
    password: str,
    display_name: str,
    locale: str,
) -> tuple[User, bool]:
    normalized_email = email.strip().lower()
    normalized_username = username.strip().lower()
    existing = db.scalar(
        select(User).where(
            or_(User.email == normalized_email, User.username == normalized_username)
        )
    )
    if existing:
        if (
            existing.email == normalized_email
            and existing.username == normalized_username
            and existing.role == UserRole.ADMIN
            and existing.status == UserStatus.ENABLED
        ):
            return existing, False
        raise InfraError(409, "auth.identity_conflict")
    payload = RegisterRequest(
        email=normalized_email,
        username=normalized_username,
        display_name=display_name,
        password=password,
        locale=locale,
    )
    user = User(
        email=payload.email,
        username=payload.username,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role=UserRole.ADMIN,
        status=UserStatus.ENABLED,
        locale=payload.locale,
        reviewed_at=datetime.now(UTC),
    )
    db.add(user)
    db.flush()
    record_audit(
        db,
        action="auth.bootstrap_admin",
        target_type="user",
        target_id=user.id,
        after_state={"status": user.status.value, "role": user.role.value},
    )
    db.commit()
    db.refresh(user)
    return user, True


def authenticate_user(
    db: Session,
    *,
    identifier: str,
    password: str,
    source_ip: str | None,
    user_agent: str | None,
    absolute_days: int,
) -> tuple[User, str]:
    user = db.scalar(select(User).where(or_(User.email == identifier, User.username == identifier)))
    if user is None:
        run_dummy_verification(password)
        record_audit(
            db,
            action="auth.login",
            target_type="user",
            source_ip=source_ip,
            user_agent=user_agent,
            result=AuditResult.FAILURE,
            detail="invalid_credentials",
        )
        db.commit()
        raise InfraError(401, "auth.invalid_credentials")

    valid, updated_hash = verify_password(password, user.password_hash)
    if not valid:
        record_audit(
            db,
            action="auth.login",
            target_type="user",
            target_id=user.id,
            source_ip=source_ip,
            user_agent=user_agent,
            result=AuditResult.FAILURE,
            detail="invalid_credentials",
        )
        db.commit()
        raise InfraError(401, "auth.invalid_credentials")
    if user.status != UserStatus.ENABLED:
        record_audit(
            db,
            action="auth.login",
            target_type="user",
            target_id=user.id,
            source_ip=source_ip,
            user_agent=user_agent,
            result=AuditResult.FAILURE,
            detail=user.status.value,
        )
        db.commit()
        raise InfraError(403, f"auth.{user.status.value}")

    now = datetime.now(UTC)
    _, absolute_expiry = session_deadlines(now=now, absolute_days=absolute_days)
    token = new_session_token()
    if updated_hash:
        user.password_hash = updated_hash
    user.last_login_at = now
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=digest_session_token(token),
        source_ip=source_ip,
        user_agent=(user_agent or "")[:512] or None,
        created_at=now,
        last_seen_at=now,
        expires_at=absolute_expiry,
    )
    db.add(auth_session)
    record_audit(
        db,
        action="auth.login",
        target_type="user",
        target_id=user.id,
        actor_id=user.id,
        source_ip=source_ip,
        user_agent=user_agent,
    )
    db.commit()
    db.refresh(user)
    return user, token


def revoke_user_sessions(db: Session, user_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    sessions = db.scalars(
        select(AuthSession).where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        )
    )
    for auth_session in sessions:
        auth_session.revoked_at = now


def update_user_status(
    db: Session,
    *,
    actor: User,
    target: User,
    payload: UserStatusUpdate,
    source_ip: str | None,
    user_agent: str | None,
) -> User:
    new_status = UserStatus(payload.status)
    if (
        target.role == UserRole.ADMIN
        and target.status == UserStatus.ENABLED
        and new_status != UserStatus.ENABLED
    ):
        enabled_admin_ids = list(
            db.scalars(
                select(User.id)
                .where(User.role == UserRole.ADMIN, User.status == UserStatus.ENABLED)
                .with_for_update()
            )
        )
        if len(enabled_admin_ids) <= 1:
            raise InfraError(409, "admin.last_admin")
    before = {"status": target.status.value, "rejection_reason": target.rejection_reason}
    target.status = new_status
    target.reviewed_by = actor.id
    target.reviewed_at = datetime.now(UTC)
    target.rejection_reason = (
        payload.rejection_reason.strip()
        if new_status == UserStatus.REJECTED and payload.rejection_reason
        else None
    )
    if new_status != UserStatus.ENABLED:
        revoke_user_sessions(db, target.id)
    record_audit(
        db,
        action="admin.user_status",
        target_type="user",
        target_id=target.id,
        actor_id=actor.id,
        source_ip=source_ip,
        user_agent=user_agent,
        before_state=before,
        after_state={"status": target.status.value, "rejection_reason": target.rejection_reason},
    )
    db.commit()
    db.refresh(target)
    return target


def create_project(db: Session, *, actor: User, payload: ProjectCreate) -> Project:
    if db.scalar(select(Project.id).where(Project.code == payload.code)):
        raise InfraError(409, "project.code_conflict")
    project = Project(code=payload.code, name=payload.name)
    db.add(project)
    db.flush()
    record_audit(
        db,
        action="admin.project_create",
        target_type="project",
        target_id=project.id,
        actor_id=actor.id,
        after_state={"code": project.code, "name": project.name},
    )
    db.commit()
    db.refresh(project)
    return project


def assign_project(db: Session, *, actor: User, user: User, project: Project) -> ProjectMembership:
    membership = db.get(ProjectMembership, (user.id, project.id))
    if membership is None:
        membership = ProjectMembership(user_id=user.id, project_id=project.id, assigned_by=actor.id)
        db.add(membership)
        record_audit(
            db,
            action="admin.project_assign",
            target_type="user",
            target_id=user.id,
            actor_id=actor.id,
            after_state={"project_id": str(project.id)},
        )
        db.commit()
    return membership


def remove_project(db: Session, *, actor: User, user: User, project: Project) -> None:
    membership = db.get(ProjectMembership, (user.id, project.id))
    if membership is not None:
        db.delete(membership)
        record_audit(
            db,
            action="admin.project_remove",
            target_type="user",
            target_id=user.id,
            actor_id=actor.id,
            before_state={"project_id": str(project.id)},
        )
        db.commit()
