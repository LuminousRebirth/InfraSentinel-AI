from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base, utc_now


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EventStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"


class AlertStatus(str, enum.Enum):
    PENDING_CONFIRMATION = "pending_confirmation"
    ASSIGNED = "assigned"
    PROCESSING = "processing"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class AnalysisStatus(str, enum.Enum):
    WAITING_CONFIGURATION = "waiting_configuration"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LlmProvider(str, enum.Enum):
    QWEN = "qwen"
    DEEPSEEK = "deepseek"
    GLM = "glm"


class AlertRule(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (
        CheckConstraint("min_confidence BETWEEN 0 AND 1", name="ck_alert_rules_confidence"),
        CheckConstraint("merge_window_ms BETWEEN 0 AND 600000", name="ck_alert_rules_window"),
        CheckConstraint("iou_threshold BETWEEN 0 AND 1", name="ck_alert_rules_iou"),
        CheckConstraint("cooldown_seconds BETWEEN 0 AND 86400", name="ck_alert_rules_cooldown"),
        Index("ix_alert_rules_match", "project_id", "class_name", "enabled", "priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name_zh: Mapped[str] = mapped_column(String(200))
    name_en: Mapped[str] = mapped_column(String(200))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    class_name: Mapped[str] = mapped_column(String(100), index=True)
    min_confidence: Mapped[float] = mapped_column(Float, default=0.01)
    risk_level: Mapped[RiskLevel] = mapped_column(String(16))
    merge_window_ms: Mapped[int] = mapped_column(Integer, default=3000)
    iou_threshold: Mapped[float] = mapped_column(Float, default=0.30)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=60)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DetectionEvent(Base):
    __tablename__ = "detection_events"
    __table_args__ = (
        CheckConstraint("first_timestamp_ms >= 0", name="ck_events_first_time"),
        CheckConstraint("last_timestamp_ms >= first_timestamp_ms", name="ck_events_last_time"),
        CheckConstraint("observation_count > 0", name="ck_events_count"),
        CheckConstraint("max_confidence BETWEEN 0 AND 1", name="ck_events_confidence"),
        Index("ix_events_project_created", "project_id", "created_at"),
        Index("ix_events_job_class_time", "job_id", "class_name", "first_timestamp_ms"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("detection_jobs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vision_models.id"))
    class_name: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[EventStatus] = mapped_column(String(16), default=EventStatus.CLOSED)
    first_frame: Mapped[int] = mapped_column(Integer)
    last_frame: Mapped[int] = mapped_column(Integer)
    first_timestamp_ms: Mapped[int] = mapped_column(BigInteger)
    last_timestamp_ms: Mapped[int] = mapped_column(BigInteger)
    observation_count: Mapped[int] = mapped_column(Integer)
    max_confidence: Mapped[float] = mapped_column(Float)
    representative_observation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("detection_observations.id", ondelete="RESTRICT")
    )
    keyframe_media_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("detection_media.id", ondelete="SET NULL"), nullable=True
    )
    last_box_json: Mapped[list[float]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_alerts_version"),
        Index("ix_alerts_project_status_created", "project_id", "status", "created_at"),
        Index("ix_alerts_assignee_status", "assignee_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("detection_events.id", ondelete="CASCADE"), unique=True
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("alert_rules.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    final_level: Mapped[RiskLevel] = mapped_column(String(16), index=True)
    status: Mapped[AlertStatus] = mapped_column(
        String(32), default=AlertStatus.PENDING_CONFIRMATION, index=True
    )
    title_zh: Mapped[str] = mapped_column(String(250))
    title_en: Mapped[str] = mapped_column(String(250))
    summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    response_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AlertAction(Base):
    __tablename__ = "alert_actions"
    __table_args__ = (Index("ix_alert_actions_alert_created", "alert_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100))
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    detail: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AlertAttachment(Base):
    __tablename__ = "alert_attachments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), index=True
    )
    uploader_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LlmProviderConfig(Base):
    __tablename__ = "llm_provider_configs"
    __table_args__ = (
        CheckConstraint("timeout_seconds BETWEEN 1 AND 300", name="ck_llm_provider_timeout"),
        CheckConstraint("max_retries BETWEEN 0 AND 5", name="ck_llm_provider_retries"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    provider: Mapped[LlmProvider] = mapped_column(String(20))
    endpoint: Mapped[str] = mapped_column(String(2048))
    model_name: Mapped[str] = mapped_column(String(200))
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=60)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class LlmCredential(Base):
    __tablename__ = "llm_credentials"
    __table_args__ = (UniqueConstraint("provider_config_id", "scope_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider_config_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("llm_provider_configs.id", ondelete="CASCADE"), index=True
    )
    scope_key: Mapped[str] = mapped_column(String(50))
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    encrypted_key: Mapped[bytes] = mapped_column(LargeBinary)
    key_hint: Mapped[str] = mapped_column(String(20))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LlmAnalysis(Base):
    __tablename__ = "llm_analyses"
    __table_args__ = (
        CheckConstraint(
            "(job_id IS NOT NULL AND event_id IS NULL) OR "
            "(job_id IS NULL AND event_id IS NOT NULL)",
            name="ck_llm_analysis_target",
        ),
        CheckConstraint("attempt >= 1 AND max_attempts >= attempt", name="ck_llm_attempts"),
        UniqueConstraint("job_id"),
        UniqueConstraint("event_id"),
        Index("ix_llm_analysis_queue", "status", "requested_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("detection_jobs.id", ondelete="CASCADE"), nullable=True
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("detection_events.id", ondelete="CASCADE"), nullable=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    provider_config_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("llm_provider_configs.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[AnalysisStatus] = mapped_column(
        String(32), default=AnalysisStatus.WAITING_CONFIGURATION, index=True
    )
    prefer_personal: Mapped[bool] = mapped_column(Boolean, default=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    claimed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class LlmCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("llm_analyses.id", ondelete="CASCADE"), index=True
    )
    provider_config_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("llm_provider_configs.id"))
    succeeded: Mapped[bool] = mapped_column(Boolean)
    duration_ms: Mapped[int] = mapped_column(Integer)
    request_bytes: Mapped[int] = mapped_column(BigInteger)
    response_bytes: Mapped[int] = mapped_column(BigInteger)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


__all__ = [
    "Alert",
    "AlertAction",
    "AlertAttachment",
    "AlertRule",
    "AlertStatus",
    "AnalysisStatus",
    "DetectionEvent",
    "EventStatus",
    "LlmAnalysis",
    "LlmCall",
    "LlmCredential",
    "LlmProvider",
    "LlmProviderConfig",
    "RiskLevel",
]
