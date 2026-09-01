from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from .auth import enforce_rate_limit, hash_password, rate_limit_key, verify_password
from .dependencies import (
    AdminDep,
    AuthDep,
    DbDep,
    SettingsDep,
    client_ip,
    require_same_origin,
    user_agent,
)
from .errors import InfraError
from .models import (
    AuditEvent,
    AuditResult,
    Project,
    ProjectMembership,
    ProjectStatus,
    User,
    UserStatus,
)
from .schemas import (
    AuditOut,
    LoginRequest,
    PasswordChange,
    ProfileUpdate,
    ProjectCreate,
    ProjectOut,
    RegisterRequest,
    UserOut,
    UserStatusUpdate,
)
from .services import (
    assign_project,
    authenticate_user,
    create_project,
    record_audit,
    register_user,
    remove_project,
    revoke_user_sessions,
    update_user_status,
)

router = APIRouter(tags=["identity-access"])


def _projects_for_user(db: Session, user: User) -> list[Project]:
    if user.role.value == "admin":
        return list(
            db.scalars(
                select(Project).where(Project.status == ProjectStatus.ACTIVE).order_by(Project.code)
            )
        )
    return list(
        db.scalars(
            select(Project)
            .join(ProjectMembership, ProjectMembership.project_id == Project.id)
            .where(
                ProjectMembership.user_id == user.id,
                Project.status == ProjectStatus.ACTIVE,
            )
            .order_by(Project.code)
        )
    )


def _user_out(db: Session, user: User) -> UserOut:
    result = UserOut.model_validate(user)
    result.projects = [ProjectOut.model_validate(item) for item in _projects_for_user(db, user)]
    return result


def _users_out(db: Session, users: list[User]) -> list[UserOut]:
    if not users:
        return []
    active_projects = list(
        db.scalars(
            select(Project).where(Project.status == ProjectStatus.ACTIVE).order_by(Project.code)
        )
    )
    projects_by_id = {project.id: project for project in active_projects}
    assigned: dict[uuid.UUID, set[uuid.UUID]] = {user.id: set() for user in users}
    memberships = db.execute(
        select(ProjectMembership.user_id, ProjectMembership.project_id).where(
            ProjectMembership.user_id.in_(assigned),
            ProjectMembership.project_id.in_(projects_by_id),
        )
    )
    for user_id, project_id in memberships:
        assigned[user_id].add(project_id)

    output = []
    for user in users:
        projects = (
            active_projects
            if user.role.value == "admin"
            else [project for project in active_projects if project.id in assigned[user.id]]
        )
        result = UserOut.model_validate(user)
        result.projects = [ProjectOut.model_validate(project) for project in projects]
        output.append(result)
    return output


def _audit_rate_limit_failure(
    db: Session, request: Request, *, action: str, error: InfraError
) -> None:
    record_audit(
        db,
        action=action,
        target_type="user",
        source_ip=client_ip(request),
        user_agent=user_agent(request),
        result=AuditResult.FAILURE,
        detail=error.code,
    )
    db.commit()


@router.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    db: DbDep,
    settings: SettingsDep,
) -> UserOut:
    try:
        enforce_rate_limit(
            settings.redis_url.get_secret_value(),
            rate_limit_key("register", client_ip(request)),
            limit=5,
            window_seconds=900,
        )
        user = register_user(
            db,
            payload,
            source_ip=client_ip(request),
            user_agent=user_agent(request),
        )
    except InfraError as exc:
        _audit_rate_limit_failure(db, request, action="auth.register", error=exc)
        raise
    return _user_out(db, user)


@router.post("/auth/login", response_model=UserOut)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
) -> UserOut:
    try:
        enforce_rate_limit(
            settings.redis_url.get_secret_value(),
            rate_limit_key("login", client_ip(request), payload.identifier),
            limit=10,
            window_seconds=900,
        )
    except InfraError as exc:
        _audit_rate_limit_failure(db, request, action="auth.login", error=exc)
        raise
    user, token = authenticate_user(
        db,
        identifier=payload.identifier,
        password=payload.password,
        source_ip=client_ip(request),
        user_agent=user_agent(request),
        absolute_days=settings.session_absolute_days,
    )
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_absolute_days * 86400,
        httponly=True,
        secure=settings.infrasentinel_env == "production",
        samesite="lax",
        path="/",
    )
    return _user_out(db, user)


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
def logout(
    response: Response,
    context: AuthDep,
    db: DbDep,
    settings: SettingsDep,
) -> None:
    context.session.revoked_at = datetime.now(UTC)
    record_audit(
        db,
        action="auth.logout",
        target_type="user",
        target_id=context.user.id,
        actor_id=context.user.id,
    )
    db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/auth/me", response_model=UserOut)
def me(
    context: AuthDep,
    db: DbDep,
) -> UserOut:
    return _user_out(db, context.user)


@router.patch("/auth/me", response_model=UserOut, dependencies=[Depends(require_same_origin)])
def update_profile(
    payload: ProfileUpdate,
    request: Request,
    context: AuthDep,
    db: DbDep,
) -> UserOut:
    before = {"display_name": context.user.display_name, "locale": context.user.locale}
    if payload.display_name is not None:
        context.user.display_name = payload.display_name.strip()
    if payload.locale is not None:
        context.user.locale = payload.locale
    record_audit(
        db,
        action="auth.profile_update",
        target_type="user",
        target_id=context.user.id,
        actor_id=context.user.id,
        source_ip=client_ip(request),
        user_agent=user_agent(request),
        before_state=before,
        after_state={"display_name": context.user.display_name, "locale": context.user.locale},
    )
    db.commit()
    db.refresh(context.user)
    return _user_out(db, context.user)


@router.post(
    "/auth/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
def change_password(
    payload: PasswordChange,
    response: Response,
    request: Request,
    context: AuthDep,
    db: DbDep,
    settings: SettingsDep,
) -> None:
    valid, _ = verify_password(payload.current_password, context.user.password_hash)
    if not valid:
        raise InfraError(400, "auth.invalid_current_password")
    context.user.password_hash = hash_password(payload.new_password)
    revoke_user_sessions(db, context.user.id)
    record_audit(
        db,
        action="auth.password_change",
        target_type="user",
        target_id=context.user.id,
        actor_id=context.user.id,
        source_ip=client_ip(request),
        user_agent=user_agent(request),
    )
    db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    context: AuthDep,
    db: DbDep,
) -> list[ProjectOut]:
    return [ProjectOut.model_validate(item) for item in _projects_for_user(db, context.user)]


@router.post(
    "/admin/projects",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_same_origin)],
)
def admin_create_project(
    payload: ProjectCreate,
    context: AdminDep,
    db: DbDep,
) -> ProjectOut:
    return ProjectOut.model_validate(create_project(db, actor=context.user, payload=payload))


@router.get("/admin/users", response_model=list[UserOut])
def admin_list_users(
    context: AdminDep,
    db: DbDep,
    user_status: Literal["pending", "enabled", "disabled", "rejected"] | None = Query(
        default=None, alias="status"
    ),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[UserOut]:
    del context
    status_priority = case(
        (User.status == UserStatus.PENDING, 0),
        (User.status == UserStatus.ENABLED, 1),
        (User.status == UserStatus.DISABLED, 2),
        else_=3,
    )
    query = select(User).order_by(status_priority, User.created_at.desc()).limit(limit)
    if user_status:
        query = query.where(User.status == UserStatus(user_status))
    return _users_out(db, list(db.scalars(query)))


@router.patch(
    "/admin/users/{user_id}/status",
    response_model=UserOut,
    dependencies=[Depends(require_same_origin)],
)
def admin_update_user_status(
    user_id: uuid.UUID,
    payload: UserStatusUpdate,
    request: Request,
    context: AdminDep,
    db: DbDep,
) -> UserOut:
    target = db.get(User, user_id)
    if target is None:
        raise InfraError(404, "admin.user_not_found")
    target = update_user_status(
        db,
        actor=context.user,
        target=target,
        payload=payload,
        source_ip=client_ip(request),
        user_agent=user_agent(request),
    )
    return _user_out(db, target)


def _membership_entities(
    db: Session, user_id: uuid.UUID, project_id: uuid.UUID
) -> tuple[User, Project]:
    user = db.get(User, user_id)
    if user is None:
        raise InfraError(404, "admin.user_not_found")
    project = db.get(Project, project_id)
    if project is None:
        raise InfraError(404, "project.not_found")
    return user, project


@router.put(
    "/admin/users/{user_id}/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
def admin_assign_project(
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    context: AdminDep,
    db: DbDep,
) -> None:
    user, project = _membership_entities(db, user_id, project_id)
    assign_project(db, actor=context.user, user=user, project=project)


@router.delete(
    "/admin/users/{user_id}/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
def admin_remove_project(
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    context: AdminDep,
    db: DbDep,
) -> None:
    user, project = _membership_entities(db, user_id, project_id)
    remove_project(db, actor=context.user, user=user, project=project)


@router.get("/admin/audit-events", response_model=list[AuditOut])
def admin_list_audit_events(
    context: AdminDep,
    db: DbDep,
    action: str | None = None,
    before: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AuditOut]:
    del context
    query = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    if action:
        query = query.where(AuditEvent.action == action)
    if before:
        query = query.where(AuditEvent.created_at < before)
    return [AuditOut.model_validate(event) for event in db.scalars(query)]
