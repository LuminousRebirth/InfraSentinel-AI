from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import cv2
from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import exists, or_, select

from .dependencies import AdminDep, AuthDep, DbDep, SettingsDep, require_same_origin
from .detection_media import resolve_storage_key, safe_display_name
from .errors import InfraError
from .intelligence_models import (
    Alert,
    AlertAction,
    AlertAttachment,
    AlertRule,
    AlertStatus,
    DetectionEvent,
    LlmAnalysis,
    LlmCredential,
    LlmProviderConfig,
    RiskLevel,
)
from .intelligence_schemas import (
    AlertAttachmentOut,
    AlertDetailOut,
    AlertOut,
    AlertRuleOut,
    AlertRuleWrite,
    AlertUpdate,
    AnalysisOut,
    AnalysisRequest,
    CredentialWrite,
    ProviderOut,
    ProviderWrite,
)
from .intelligence_service import (
    credential_scope,
    queue_analysis,
    require_alert_access,
    set_llm_credential,
    update_alert_workflow,
)
from .llm_adapter import validate_endpoint
from .models import Project, ProjectMembership, UserRole
from .services import record_audit

router = APIRouter(tags=["alert-intelligence"])


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    context: AuthDep,
    db: DbDep,
    alert_status: Annotated[AlertStatus | None, Query(alias="status")] = None,
    level: RiskLevel | None = None,
    project_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Alert]:
    query = select(Alert)
    if context.user.role != UserRole.ADMIN:
        query = query.where(
            or_(Alert.owner_id == context.user.id, Alert.assignee_id == context.user.id),
            exists().where(
                ProjectMembership.user_id == context.user.id,
                ProjectMembership.project_id == Alert.project_id,
            ),
        )
    if alert_status:
        query = query.where(Alert.status == alert_status)
    if level:
        query = query.where(Alert.final_level == level)
    if project_id:
        query = query.where(Alert.project_id == project_id)
    return list(db.scalars(query.order_by(Alert.created_at.desc()).limit(limit)))


@router.get("/alerts/{alert_id}", response_model=AlertDetailOut)
def get_alert(alert_id: uuid.UUID, context: AuthDep, db: DbDep) -> AlertDetailOut:
    alert = require_alert_access(db, context.user, alert_id)
    event = db.get(DetectionEvent, alert.event_id)
    if event is None:
        raise InfraError(404, "alert.event_not_found")
    result = AlertDetailOut.model_validate(
        {
            **AlertOut.model_validate(alert).model_dump(),
            "event": event,
            "actions": list(
                db.scalars(
                    select(AlertAction)
                    .where(AlertAction.alert_id == alert.id)
                    .order_by(AlertAction.created_at)
                )
            ),
            "attachments": list(
                db.scalars(
                    select(AlertAttachment)
                    .where(AlertAttachment.alert_id == alert.id)
                    .order_by(AlertAttachment.created_at)
                )
            ),
            "analysis": db.scalar(
                select(LlmAnalysis).where(LlmAnalysis.event_id == alert.event_id)
            ),
        }
    )
    return result


ATTACHMENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}
ATTACHMENT_MAX_BYTES = 20 * 1024 * 1024


@router.post(
    "/alerts/{alert_id}/attachments",
    response_model=AlertAttachmentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_same_origin)],
)
async def upload_attachment(
    alert_id: uuid.UUID,
    upload: Annotated[UploadFile, File()],
    context: AuthDep,
    db: DbDep,
    settings: SettingsDep,
) -> AlertAttachment:
    alert = require_alert_access(db, context.user, alert_id)
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    if (
        shutil.disk_usage(settings.storage_root).free
        < settings.infrasentinel_storage_critical_gb * 1024**3
    ):
        raise InfraError(507, "alert.storage_full")
    original_name = safe_display_name(upload.filename)
    suffix = Path(original_name).suffix.lower()
    mime_type = ATTACHMENT_TYPES.get(suffix)
    if mime_type is None:
        raise InfraError(422, "alert.attachment_type_invalid")
    attachment_id = uuid.uuid4()
    now = datetime.now(UTC)
    storage_key = f"attachments/{now:%Y/%m}/{alert.id}/{attachment_id.hex}{suffix}"
    path = resolve_storage_key(settings.storage_root, storage_key)
    temporary = path.with_suffix(path.suffix + ".part")
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("xb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > ATTACHMENT_MAX_BYTES:
                    raise InfraError(413, "alert.attachment_too_large")
                digest.update(chunk)
                output.write(chunk)
        if size == 0:
            raise InfraError(422, "alert.attachment_empty")
        if mime_type == "application/pdf":
            if temporary.read_bytes()[:5] != b"%PDF-":
                raise InfraError(422, "alert.attachment_content_invalid")
        elif cv2.imread(str(temporary)) is None:
            raise InfraError(422, "alert.attachment_content_invalid")
        os.replace(temporary, path)
        attachment = AlertAttachment(
            id=attachment_id,
            alert_id=alert.id,
            uploader_id=context.user.id,
            storage_key=storage_key,
            original_name=original_name,
            mime_type=mime_type,
            byte_size=size,
            sha256=digest.hexdigest(),
        )
        db.add(attachment)
        db.add(
            AlertAction(
                alert_id=alert.id,
                actor_id=context.user.id,
                action="attachment.added",
                detail=original_name,
            )
        )
        record_audit(
            db,
            action="alert.attachment.add",
            target_type="alert",
            target_id=alert.id,
            actor_id=context.user.id,
            after_state={"attachment_id": str(attachment.id), "sha256": attachment.sha256},
        )
        db.commit()
        db.refresh(attachment)
        return attachment
    except Exception:
        temporary.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise


@router.get("/alerts/attachments/{attachment_id}", response_class=FileResponse)
def download_attachment(
    attachment_id: uuid.UUID, context: AuthDep, db: DbDep, settings: SettingsDep
) -> FileResponse:
    attachment = db.get(AlertAttachment, attachment_id)
    if attachment is None:
        raise InfraError(404, "alert.attachment_not_found")
    require_alert_access(db, context.user, attachment.alert_id)
    path = resolve_storage_key(settings.storage_root, attachment.storage_key)
    if not path.is_file():
        raise InfraError(404, "alert.attachment_missing")
    return FileResponse(path, media_type=attachment.mime_type, filename=attachment.original_name)


@router.patch(
    "/alerts/{alert_id}",
    response_model=AlertOut,
    dependencies=[Depends(require_same_origin)],
)
def update_alert(alert_id: uuid.UUID, payload: AlertUpdate, context: AuthDep, db: DbDep) -> Alert:
    alert = require_alert_access(db, context.user, alert_id)
    return update_alert_workflow(
        db,
        actor=context.user,
        alert=alert,
        expected_version=payload.expected_version,
        status=AlertStatus(payload.status) if payload.status else None,
        assignee_id=payload.assignee_id,
        final_level=RiskLevel(payload.final_level) if payload.final_level else None,
        note=payload.note,
        response_due_at=payload.response_due_at,
        close_due_at=payload.close_due_at,
    )


@router.post(
    "/alerts/{alert_id}/analyze",
    response_model=AnalysisOut,
    dependencies=[Depends(require_same_origin)],
)
def analyze_alert(
    alert_id: uuid.UUID,
    payload: AnalysisRequest,
    context: AuthDep,
    db: DbDep,
) -> LlmAnalysis:
    alert = require_alert_access(db, context.user, alert_id)
    analysis = db.scalar(select(LlmAnalysis).where(LlmAnalysis.event_id == alert.event_id))
    if analysis is None:
        raise InfraError(404, "llm.analysis_not_found")
    return queue_analysis(db, analysis, prefer_personal=payload.prefer_personal)


@router.get("/analyses/{analysis_id}", response_model=AnalysisOut)
def get_analysis(analysis_id: uuid.UUID, context: AuthDep, db: DbDep) -> LlmAnalysis:
    analysis = db.get(LlmAnalysis, analysis_id)
    if analysis is None:
        raise InfraError(404, "llm.analysis_not_found")
    if context.user.role != UserRole.ADMIN and analysis.owner_id != context.user.id:
        raise InfraError(403, "auth.forbidden")
    return analysis


@router.get("/admin/alert-rules", response_model=list[AlertRuleOut])
def list_rules(_context: AdminDep, db: DbDep) -> list[AlertRule]:
    return list(db.scalars(select(AlertRule).order_by(AlertRule.priority.desc(), AlertRule.code)))


@router.post(
    "/admin/alert-rules",
    response_model=AlertRuleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_same_origin)],
)
def create_rule(payload: AlertRuleWrite, context: AdminDep, db: DbDep) -> AlertRule:
    if db.scalar(select(AlertRule.id).where(AlertRule.code == payload.code)):
        raise InfraError(409, "alert.rule_code_exists")
    if payload.project_id and db.get(Project, payload.project_id) is None:
        raise InfraError(422, "alert.project_not_found")
    rule = AlertRule(**payload.model_dump(), created_by=context.user.id)
    db.add(rule)
    db.flush()
    record_audit(
        db,
        action="alert.rule.create",
        target_type="alert_rule",
        target_id=rule.id,
        actor_id=context.user.id,
        after_state=payload.model_dump(mode="json"),
    )
    db.commit()
    db.refresh(rule)
    return rule


@router.put(
    "/admin/alert-rules/{rule_id}",
    response_model=AlertRuleOut,
    dependencies=[Depends(require_same_origin)],
)
def replace_rule(
    rule_id: uuid.UUID, payload: AlertRuleWrite, context: AdminDep, db: DbDep
) -> AlertRule:
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise InfraError(404, "alert.rule_not_found")
    duplicate = db.scalar(
        select(AlertRule.id).where(AlertRule.code == payload.code, AlertRule.id != rule.id)
    )
    if duplicate:
        raise InfraError(409, "alert.rule_code_exists")
    if payload.project_id and db.get(Project, payload.project_id) is None:
        raise InfraError(422, "alert.project_not_found")
    before = AlertRuleOut.model_validate(rule).model_dump(mode="json")
    for key, value in payload.model_dump().items():
        setattr(rule, key, value)
    record_audit(
        db,
        action="alert.rule.update",
        target_type="alert_rule",
        target_id=rule.id,
        actor_id=context.user.id,
        before_state=before,
        after_state=payload.model_dump(mode="json"),
    )
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/llm/providers", response_model=list[ProviderOut])
def list_providers(_context: AuthDep, db: DbDep) -> list[LlmProviderConfig]:
    return list(
        db.scalars(
            select(LlmProviderConfig)
            .where(LlmProviderConfig.enabled.is_(True))
            .order_by(LlmProviderConfig.is_default.desc(), LlmProviderConfig.code)
        )
    )


@router.post(
    "/admin/llm/providers",
    response_model=ProviderOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_same_origin)],
)
def create_provider(payload: ProviderWrite, context: AdminDep, db: DbDep) -> LlmProviderConfig:
    if db.scalar(select(LlmProviderConfig.id).where(LlmProviderConfig.code == payload.code)):
        raise InfraError(409, "llm.provider_code_exists")
    values = payload.model_dump()
    values["endpoint"] = validate_endpoint(payload.endpoint)
    if payload.is_default:
        for item in db.scalars(select(LlmProviderConfig)):
            item.is_default = False
    provider = LlmProviderConfig(**values, created_by=context.user.id)
    db.add(provider)
    db.flush()
    record_audit(
        db,
        action="llm.provider.create",
        target_type="llm_provider",
        target_id=provider.id,
        actor_id=context.user.id,
        after_state={
            key: value
            for key, value in payload.model_dump(mode="json").items()
            if key != "endpoint"
        }
        | {"endpoint": provider.endpoint},
    )
    db.commit()
    db.refresh(provider)
    return provider


@router.put(
    "/admin/llm/providers/{provider_id}",
    response_model=ProviderOut,
    dependencies=[Depends(require_same_origin)],
)
def replace_provider(
    provider_id: uuid.UUID, payload: ProviderWrite, context: AdminDep, db: DbDep
) -> LlmProviderConfig:
    provider = db.get(LlmProviderConfig, provider_id)
    if provider is None:
        raise InfraError(404, "llm.provider_not_found")
    duplicate = db.scalar(
        select(LlmProviderConfig.id).where(
            LlmProviderConfig.code == payload.code,
            LlmProviderConfig.id != provider.id,
        )
    )
    if duplicate:
        raise InfraError(409, "llm.provider_code_exists")
    before = ProviderOut.model_validate(provider).model_dump(mode="json")
    values = payload.model_dump()
    values["endpoint"] = validate_endpoint(payload.endpoint)
    if payload.is_default:
        for item in db.scalars(
            select(LlmProviderConfig).where(LlmProviderConfig.id != provider.id)
        ):
            item.is_default = False
    for key, value in values.items():
        setattr(provider, key, value)
    record_audit(
        db,
        action="llm.provider.update",
        target_type="llm_provider",
        target_id=provider.id,
        actor_id=context.user.id,
        before_state=before,
        after_state=ProviderOut.model_validate(provider).model_dump(mode="json"),
    )
    db.commit()
    db.refresh(provider)
    return provider


def _save_credential(
    provider_id: uuid.UUID,
    payload: CredentialWrite,
    owner_id: uuid.UUID | None,
    db: DbDep,
    settings: SettingsDep,
    actor_id: uuid.UUID,
) -> Response:
    set_llm_credential(
        db,
        provider_config_id=provider_id,
        owner_id=owner_id,
        api_key=payload.api_key,
        application_secret=settings.infrasentinel_secret_key.get_secret_value(),
        actor_id=actor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/llm/providers/{provider_id}/credentials/personal",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
def save_personal_credential(
    provider_id: uuid.UUID,
    payload: CredentialWrite,
    context: AuthDep,
    db: DbDep,
    settings: SettingsDep,
) -> Response:
    return _save_credential(provider_id, payload, context.user.id, db, settings, context.user.id)


@router.delete(
    "/llm/providers/{provider_id}/credentials/personal",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
def delete_personal_credential(provider_id: uuid.UUID, context: AuthDep, db: DbDep) -> Response:
    credential = db.scalar(
        select(LlmCredential).where(
            LlmCredential.provider_config_id == provider_id,
            LlmCredential.scope_key == credential_scope(context.user.id),
        )
    )
    if credential:
        db.delete(credential)
        record_audit(
            db,
            action="llm.credential.delete",
            target_type="llm_provider",
            target_id=provider_id,
            actor_id=context.user.id,
            before_state={"scope": credential.scope_key, "key_hint": credential.key_hint},
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/admin/llm/providers/{provider_id}/credentials/system",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
def save_system_credential(
    provider_id: uuid.UUID,
    payload: CredentialWrite,
    _context: AdminDep,
    db: DbDep,
    settings: SettingsDep,
) -> Response:
    return _save_credential(provider_id, payload, None, db, settings, _context.user.id)
