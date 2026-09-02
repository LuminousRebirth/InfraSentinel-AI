from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base, utc_now


class VisionScene(str, enum.Enum):
    PIPELINE = "pipeline"
    PPE = "ppe"


class ModelBackend(str, enum.Enum):
    AUTO = "auto"
    TRT = "trt"
    PT = "pt"


class ModelAvailability(str, enum.Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class DetectionKind(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"
    OBS = "obs"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class MediaRole(str, enum.Enum):
    ORIGINAL = "original"
    ANNOTATED = "annotated"
    KEYFRAME = "keyframe"


class MediaType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"


class VisionModel(Base):
    __tablename__ = "vision_models"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name_zh: Mapped[str] = mapped_column(String(100))
    name_en: Mapped[str] = mapped_column(String(100))
    scene: Mapped[VisionScene] = mapped_column(String(16), index=True)
    pt_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    engine_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    asset_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    classes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    input_size: Mapped[int] = mapped_column(Integer)
    preferred_backend: Mapped[ModelBackend] = mapped_column(String(16), default=ModelBackend.AUTO)
    availability: Mapped[ModelAvailability] = mapped_column(
        String(16), default=ModelAvailability.UNAVAILABLE
    )
    unavailable_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version_label: Mapped[str] = mapped_column(String(100), default="local")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DetectionJob(Base):
    __tablename__ = "detection_jobs"
    __table_args__ = (
        CheckConstraint("point_id = project_id", name="ck_detection_jobs_provisional_point"),
        CheckConstraint("progress_percent BETWEEN 0 AND 100", name="ck_detection_jobs_progress"),
        CheckConstraint(
            "attempt >= 1 AND max_attempts >= attempt", name="ck_detection_jobs_attempts"
        ),
        Index("ix_detection_jobs_queue", "status", "queued_at"),
        Index("ix_detection_jobs_owner_created", "owner_id", "created_at"),
        Index("ix_detection_jobs_project_created", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[DetectionKind] = mapped_column(String(16), index=True)
    status: Mapped[JobStatus] = mapped_column(String(16), default=JobStatus.QUEUED)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    point_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vision_models.id"), index=True)
    scene: Mapped[VisionScene] = mapped_column(String(16))
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    progress_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    retry_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("detection_jobs.id", ondelete="SET NULL"), nullable=True
    )
    claimed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DetectionMedia(Base):
    __tablename__ = "detection_media"
    __table_args__ = (Index("ix_detection_media_job_role", "job_id", "role"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("detection_jobs.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MediaRole] = mapped_column(String(16))
    media_type: Mapped[MediaType] = mapped_column(String(16))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    frame_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DetectionObservation(Base):
    __tablename__ = "detection_observations"
    __table_args__ = (Index("ix_detection_observations_job_time", "job_id", "timestamp_ms"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("detection_jobs.id", ondelete="CASCADE"), index=True
    )
    media_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("detection_media.id", ondelete="SET NULL"), nullable=True
    )
    frame_index: Mapped[int] = mapped_column(Integer, default=0)
    timestamp_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    class_name: Mapped[str] = mapped_column(String(100), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    x1: Mapped[float] = mapped_column(Float)
    y1: Mapped[float] = mapped_column(Float)
    x2: Mapped[float] = mapped_column(Float)
    y2: Mapped[float] = mapped_column(Float)
    inference_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DetectionMetric(Base):
    __tablename__ = "detection_metrics"
    __table_args__ = (Index("ix_detection_metrics_job_sample", "job_id", "sample_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("detection_jobs.id", ondelete="CASCADE"), index=True
    )
    sample_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    processed_frames: Mapped[int] = mapped_column(Integer)
    effective_fps: Mapped[float] = mapped_column(Float)
    inference_p50_ms: Mapped[float] = mapped_column(Float)
    gpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpu_memory_used_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gpu_memory_total_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)


__all__ = [
    "DetectionJob",
    "DetectionKind",
    "DetectionMedia",
    "DetectionMetric",
    "DetectionObservation",
    "JobStatus",
    "MediaRole",
    "MediaType",
    "ModelAvailability",
    "ModelBackend",
    "VisionModel",
    "VisionScene",
]
