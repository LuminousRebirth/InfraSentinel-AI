from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from .database import utc_now
from .detection_models import (
    DetectionJob,
    DetectionKind,
    DetectionMedia,
    DetectionObservation,
    JobStatus,
    MediaRole,
)
from .errors import InfraError
from .intelligence_models import (
    Alert,
    AlertAction,
    AlertRule,
    AlertStatus,
    AnalysisStatus,
    DetectionEvent,
    EventStatus,
    LlmAnalysis,
    LlmCredential,
    LlmProviderConfig,
    RiskLevel,
)
from .llm_adapter import encrypt_api_key
from .models import ProjectMembership, User, UserRole, UserStatus
from .services import record_audit

DEFAULT_RULES = (
    ("CK", RiskLevel.MEDIUM, "管道裂缝", "Pipeline crack"),
    ("PL", RiskLevel.MEDIUM, "管道修补", "Pipeline repair"),
    ("SG", RiskLevel.MEDIUM, "管道沉积", "Pipeline deposit"),
    ("SL", RiskLevel.MEDIUM, "管道表面破损", "Pipeline surface damage"),
    ("TL", RiskLevel.MEDIUM, "管道树根", "Pipeline root intrusion"),
    ("ZW", RiskLevel.MEDIUM, "管道障碍物", "Pipeline obstruction"),
    ("no_helmet", RiskLevel.HIGH, "未佩戴安全帽", "Missing safety helmet"),
)


def _value(item) -> str:
    return item.value if hasattr(item, "value") else str(item)


@dataclass(frozen=True)
class EventGroup:
    observations: tuple[DetectionObservation, ...]

    @property
    def first(self) -> DetectionObservation:
        return self.observations[0]

    @property
    def last(self) -> DetectionObservation:
        return self.observations[-1]

    @property
    def representative(self) -> DetectionObservation:
        return max(self.observations, key=lambda item: (item.confidence, str(item.id)))


def box_iou(left: DetectionObservation, right: DetectionObservation) -> float:
    x1 = max(left.x1, right.x1)
    y1 = max(left.y1, right.y1)
    x2 = min(left.x2, right.x2)
    y2 = min(left.y2, right.y2)
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, left.x2 - left.x1) * max(0.0, left.y2 - left.y1)
    right_area = max(0.0, right.x2 - right.x1) * max(0.0, right.y2 - right.y1)
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def group_observations(
    observations: list[DetectionObservation],
    *,
    image: bool,
    merge_window_ms: int = 3000,
    iou_threshold: float = 0.30,
) -> list[EventGroup]:
    ordered = sorted(
        observations,
        key=lambda item: (item.class_name, item.timestamp_ms, item.frame_index, str(item.id)),
    )
    if image:
        return [EventGroup((item,)) for item in ordered]
    groups: list[list[DetectionObservation]] = []
    for item in ordered:
        current = groups[-1] if groups else []
        if (
            current
            and current[-1].class_name == item.class_name
            and item.timestamp_ms - current[-1].timestamp_ms <= merge_window_ms
            and box_iou(current[-1], item) >= iou_threshold
        ):
            current.append(item)
        else:
            groups.append([item])
    return [EventGroup(tuple(items)) for items in groups]


def seed_default_rules(db: Session) -> list[AlertRule]:
    rules: list[AlertRule] = []
    for class_name, level, name_zh, name_en in DEFAULT_RULES:
        code = f"default-{class_name.lower()}"
        rule = db.scalar(select(AlertRule).where(AlertRule.code == code))
        if rule is None:
            rule = AlertRule(
                code=code,
                name_zh=name_zh,
                name_en=name_en,
                class_name=class_name,
                min_confidence=0.01,
                risk_level=level,
                merge_window_ms=3000,
                iou_threshold=0.30,
                cooldown_seconds=60,
                priority=100,
                enabled=True,
            )
            db.add(rule)
        rules.append(rule)
    db.commit()
    for rule in rules:
        db.refresh(rule)
    return rules


def rule_for_class(db: Session, project_id: uuid.UUID, class_name: str) -> AlertRule | None:
    return db.scalar(
        select(AlertRule)
        .where(
            AlertRule.enabled.is_(True),
            AlertRule.class_name == class_name,
            (AlertRule.project_id == project_id) | AlertRule.project_id.is_(None),
        )
        .order_by(
            case((AlertRule.project_id == project_id, 1), else_=0).desc(),
            AlertRule.priority.desc(),
            AlertRule.created_at,
        )
        .limit(1)
    )


def _fingerprint(job_id: uuid.UUID, group: EventGroup) -> str:
    value = f"{job_id}:{group.first.class_name}:{group.first.id}"
    return hashlib.sha256(value.encode()).hexdigest()


def _ensure_analysis(
    db: Session,
    *,
    owner_id: uuid.UUID,
    job_id: uuid.UUID | None = None,
    event_id: uuid.UUID | None = None,
) -> LlmAnalysis:
    target = LlmAnalysis.job_id == job_id if job_id else LlmAnalysis.event_id == event_id
    analysis = db.scalar(select(LlmAnalysis).where(target))
    if analysis is None:
        analysis = LlmAnalysis(
            job_id=job_id,
            event_id=event_id,
            owner_id=owner_id,
            status=AnalysisStatus.WAITING_CONFIGURATION,
        )
        db.add(analysis)
        configured = db.execute(
            select(LlmProviderConfig, LlmCredential)
            .join(LlmCredential, LlmCredential.provider_config_id == LlmProviderConfig.id)
            .where(
                LlmProviderConfig.enabled.is_(True),
                LlmProviderConfig.supports_vision.is_(True),
                LlmCredential.scope_key == "system",
            )
            .order_by(LlmProviderConfig.is_default.desc(), LlmProviderConfig.created_at)
            .limit(1)
        ).first()
        if configured:
            analysis.provider_config_id = configured[0].id
            analysis.max_attempts = configured[0].max_retries + 1
            analysis.status = AnalysisStatus.QUEUED
    return analysis


def _upsert_event(
    db: Session,
    job: DetectionJob,
    group: EventGroup,
    keyframes: list[DetectionMedia],
) -> DetectionEvent:
    fingerprint = _fingerprint(job.id, group)
    event = db.scalar(select(DetectionEvent).where(DetectionEvent.fingerprint == fingerprint))
    representative = group.representative
    keyframe_id = None
    nearest = None
    for media in keyframes:
        matches = re.findall(r"(\d{10})", media.original_name)
        if matches:
            distance = abs(int(matches[-1]) - representative.timestamp_ms)
            if nearest is None or distance < nearest:
                nearest = distance
                keyframe_id = media.id
    values = {
        "last_frame": group.last.frame_index,
        "last_timestamp_ms": group.last.timestamp_ms,
        "observation_count": len(group.observations),
        "max_confidence": representative.confidence,
        "representative_observation_id": representative.id,
        "keyframe_media_id": keyframe_id,
        "last_box_json": [group.last.x1, group.last.y1, group.last.x2, group.last.y2],
        "status": EventStatus.CLOSED,
    }
    if event is None:
        event = DetectionEvent(
            fingerprint=fingerprint,
            job_id=job.id,
            project_id=job.project_id,
            owner_id=job.owner_id,
            model_id=job.model_id,
            class_name=group.first.class_name,
            first_frame=group.first.frame_index,
            first_timestamp_ms=group.first.timestamp_ms,
            **values,
        )
        db.add(event)
        db.flush()
    else:
        for key, value in values.items():
            setattr(event, key, value)
    return event


def _ensure_alert(db: Session, event: DetectionEvent, rule: AlertRule) -> Alert:
    alert = db.scalar(select(Alert).where(Alert.event_id == event.id))
    if alert is not None:
        return alert
    alert = Alert(
        event_id=event.id,
        rule_id=rule.id,
        project_id=event.project_id,
        owner_id=event.owner_id,
        final_level=rule.risk_level,
        title_zh=f"{rule.name_zh}预警",
        title_en=f"{rule.name_en} alert",
        summary=f"{event.class_name} · {event.max_confidence:.1%}",
    )
    db.add(alert)
    db.flush()
    db.add(
        AlertAction(
            alert_id=alert.id,
            action="alert.created",
            after_state={"level": _value(rule.risk_level), "rule_id": str(rule.id)},
        )
    )
    record_audit(
        db,
        action="alert.create",
        target_type="alert",
        target_id=alert.id,
        actor_id=event.owner_id,
        after_state={"event_id": str(event.id), "level": _value(rule.risk_level)},
    )
    return alert


def refresh_job_intelligence(db: Session, job: DetectionJob) -> list[Alert]:
    observations = list(
        db.scalars(
            select(DetectionObservation)
            .where(DetectionObservation.job_id == job.id)
            .order_by(DetectionObservation.timestamp_ms, DetectionObservation.frame_index)
        )
    )
    keyframes = list(
        db.scalars(
            select(DetectionMedia).where(
                DetectionMedia.job_id == job.id,
                DetectionMedia.role == MediaRole.KEYFRAME,
            )
        )
    )
    alerts: list[Alert] = []
    for class_name in sorted({item.class_name for item in observations}):
        rule = rule_for_class(db, job.project_id, class_name)
        class_items = [item for item in observations if item.class_name == class_name]
        groups = group_observations(
            class_items,
            image=job.kind == DetectionKind.IMAGE,
            merge_window_ms=rule.merge_window_ms if rule else 3000,
            iou_threshold=rule.iou_threshold if rule else 0.30,
        )
        for group in groups:
            event = _upsert_event(db, job, group, keyframes)
            if rule and event.max_confidence >= rule.min_confidence:
                alerts.append(_ensure_alert(db, event, rule))
            if job.kind != DetectionKind.IMAGE:
                _ensure_analysis(db, owner_id=job.owner_id, event_id=event.id)
    if observations and job.kind == DetectionKind.IMAGE:
        _ensure_analysis(db, owner_id=job.owner_id, job_id=job.id)
    db.commit()
    return alerts


def backfill_intelligence(db: Session) -> int:
    jobs = list(
        db.scalars(
            select(DetectionJob)
            .where(DetectionJob.status == JobStatus.SUCCEEDED)
            .order_by(DetectionJob.created_at)
        )
    )
    for job in jobs:
        refresh_job_intelligence(db, job)
    return len(jobs)


def credential_scope(owner_id: uuid.UUID | None) -> str:
    return f"user:{owner_id}" if owner_id else "system"


def set_llm_credential(
    db: Session,
    *,
    provider_config_id: uuid.UUID,
    owner_id: uuid.UUID | None,
    api_key: str,
    application_secret: str,
    actor_id: uuid.UUID,
) -> LlmCredential:
    provider = db.get(LlmProviderConfig, provider_config_id)
    if provider is None:
        raise InfraError(404, "llm.provider_not_found")
    scope = credential_scope(owner_id)
    credential = db.scalar(
        select(LlmCredential).where(
            LlmCredential.provider_config_id == provider_config_id,
            LlmCredential.scope_key == scope,
        )
    )
    encrypted = encrypt_api_key(application_secret, api_key)
    if credential is None:
        credential = LlmCredential(
            provider_config_id=provider_config_id,
            scope_key=scope,
            owner_id=owner_id,
            encrypted_key=encrypted,
            key_hint=f"…{api_key.strip()[-4:]}",
        )
        db.add(credential)
    else:
        credential.encrypted_key = encrypted
        credential.key_hint = f"…{api_key.strip()[-4:]}"
        credential.updated_at = utc_now()
    waiting = select(LlmAnalysis).where(LlmAnalysis.status == AnalysisStatus.WAITING_CONFIGURATION)
    if owner_id:
        waiting = waiting.where(LlmAnalysis.owner_id == owner_id, LlmAnalysis.prefer_personal)
    else:
        waiting = waiting.where(LlmAnalysis.prefer_personal.is_(False))
    for analysis in db.scalars(waiting):
        analysis.provider_config_id = provider_config_id
        analysis.max_attempts = provider.max_retries + 1
        analysis.status = AnalysisStatus.QUEUED
        analysis.requested_at = utc_now()
    record_audit(
        db,
        action="llm.credential.replace",
        target_type="llm_provider",
        target_id=provider.id,
        actor_id=actor_id,
        after_state={"scope": scope, "key_hint": credential.key_hint},
    )
    db.commit()
    db.refresh(credential)
    return credential


def provider_credential_for_analysis(
    db: Session, analysis: LlmAnalysis
) -> tuple[LlmProviderConfig, LlmCredential] | None:
    scopes = (
        [credential_scope(analysis.owner_id), "system"] if analysis.prefer_personal else ["system"]
    )
    for scope in scopes:
        row = db.execute(
            select(LlmProviderConfig, LlmCredential)
            .join(LlmCredential, LlmCredential.provider_config_id == LlmProviderConfig.id)
            .where(
                LlmProviderConfig.enabled.is_(True),
                LlmProviderConfig.supports_vision.is_(True),
                LlmCredential.scope_key == scope,
            )
            .order_by(LlmProviderConfig.is_default.desc(), LlmProviderConfig.created_at)
            .limit(1)
        ).first()
        if row:
            return row[0], row[1]
    return None


def queue_analysis(db: Session, analysis: LlmAnalysis, *, prefer_personal: bool) -> LlmAnalysis:
    analysis.prefer_personal = prefer_personal
    configured = provider_credential_for_analysis(db, analysis)
    if configured:
        analysis.provider_config_id = configured[0].id
        analysis.max_attempts = configured[0].max_retries + 1
        analysis.status = AnalysisStatus.QUEUED
        analysis.error_code = analysis.error_detail = None
        analysis.finished_at = None
        analysis.requested_at = utc_now()
    else:
        analysis.provider_config_id = None
        analysis.status = AnalysisStatus.WAITING_CONFIGURATION
        analysis.error_code = "llm.configuration_missing"
        analysis.error_detail = None
    db.commit()
    db.refresh(analysis)
    return analysis


def claim_next_analysis(db: Session, worker_id: str, lease_seconds: int) -> LlmAnalysis | None:
    now = utc_now()
    candidate = db.scalar(
        select(LlmAnalysis)
        .where(
            (LlmAnalysis.status == AnalysisStatus.QUEUED)
            | (
                (LlmAnalysis.status == AnalysisStatus.RUNNING)
                & (LlmAnalysis.lease_expires_at < now)
                & (LlmAnalysis.attempt < LlmAnalysis.max_attempts)
            )
        )
        .order_by(LlmAnalysis.requested_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if candidate is None:
        return None
    if candidate.status == AnalysisStatus.RUNNING:
        candidate.attempt += 1
    candidate.status = AnalysisStatus.RUNNING
    candidate.claimed_by = worker_id[:100]
    candidate.started_at = candidate.started_at or now
    candidate.lease_expires_at = now + timedelta(seconds=lease_seconds)
    db.commit()
    db.refresh(candidate)
    return candidate


def require_alert_access(db: Session, user: User, alert_id: uuid.UUID) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise InfraError(404, "alert.not_found")
    if user.role != UserRole.ADMIN:
        if db.get(ProjectMembership, (user.id, alert.project_id)) is None:
            raise InfraError(403, "auth.project_access_denied")
        if user.id not in {alert.owner_id, alert.assignee_id}:
            raise InfraError(403, "auth.forbidden")
    return alert


TRANSITIONS = {
    AlertStatus.PENDING_CONFIRMATION: {AlertStatus.ASSIGNED},
    AlertStatus.ASSIGNED: {AlertStatus.PROCESSING},
    AlertStatus.PROCESSING: {AlertStatus.RESOLVED, AlertStatus.FALSE_POSITIVE},
}


def update_alert_workflow(
    db: Session,
    *,
    actor: User,
    alert: Alert,
    expected_version: int,
    status: AlertStatus | None = None,
    assignee_id: uuid.UUID | None = None,
    final_level: RiskLevel | None = None,
    note: str | None = None,
    response_due_at: datetime | None = None,
    close_due_at: datetime | None = None,
) -> Alert:
    if alert.version != expected_version:
        raise InfraError(409, "alert.version_conflict")
    before = {
        "status": _value(alert.status),
        "assignee_id": str(alert.assignee_id) if alert.assignee_id else None,
        "level": _value(alert.final_level),
        "version": alert.version,
    }
    if assignee_id is not None:
        if actor.role != UserRole.ADMIN:
            raise InfraError(403, "auth.forbidden")
        assignee = db.get(User, assignee_id)
        if assignee is None or assignee.status != UserStatus.ENABLED:
            raise InfraError(422, "alert.invalid_assignee")
        if (
            assignee.role != UserRole.ADMIN
            and db.get(ProjectMembership, (assignee.id, alert.project_id)) is None
        ):
            raise InfraError(422, "alert.invalid_assignee")
        alert.assignee_id = assignee.id
    if final_level is not None and final_level != alert.final_level:
        if actor.role != UserRole.ADMIN or not (note or "").strip():
            raise InfraError(422, "alert.override_reason_required")
        alert.final_level = final_level
    if status is not None and status != alert.status:
        current = AlertStatus(alert.status)
        if status not in TRANSITIONS.get(current, set()):
            raise InfraError(409, "alert.invalid_transition")
        if status == AlertStatus.ASSIGNED and alert.assignee_id is None:
            raise InfraError(422, "alert.assignee_required")
        if (
            status in {AlertStatus.RESOLVED, AlertStatus.FALSE_POSITIVE}
            and not (note or "").strip()
        ):
            raise InfraError(422, "alert.resolution_note_required")
        alert.status = status
        if status == AlertStatus.PROCESSING:
            alert.acknowledged_at = utc_now()
        if status in {AlertStatus.RESOLVED, AlertStatus.FALSE_POSITIVE}:
            alert.resolved_at = utc_now()
            alert.resolution_note = note.strip()
    alert.response_due_at = response_due_at or alert.response_due_at
    alert.close_due_at = close_due_at or alert.close_due_at
    alert.version += 1
    after = {
        "status": _value(alert.status),
        "assignee_id": str(alert.assignee_id) if alert.assignee_id else None,
        "level": _value(alert.final_level),
        "version": alert.version,
    }
    db.add(
        AlertAction(
            alert_id=alert.id,
            actor_id=actor.id,
            action="alert.updated",
            before_state=before,
            after_state=after,
            detail=(note or "")[:1000] or None,
        )
    )
    record_audit(
        db,
        action="alert.update",
        target_type="alert",
        target_id=alert.id,
        actor_id=actor.id,
        before_state=before,
        after_state=after,
    )
    db.commit()
    db.refresh(alert)
    return alert
