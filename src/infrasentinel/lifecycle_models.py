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
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base, utc_now


class DatasetStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class VersionStatus(str, enum.Enum):
    DRAFT = "draft"
    FROZEN = "frozen"
    TRAINING = "training"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class SampleSplit(str, enum.Enum):
    UNASSIGNED = "unassigned"
    TRAIN = "train"
    VAL = "val"
    TEST = "test"


class ReviewStatus(str, enum.Enum):
    UNREVIEWED = "unreviewed"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"


class FindingSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class LifecycleJobKind(str, enum.Enum):
    EXTRACT = "extract"
    VALIDATE = "validate"
    EXPORT = "export"
    TRAIN = "train"
    EVALUATE = "evaluate"


class LifecycleJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ManagedModelStatus(str, enum.Enum):
    DRAFT = "draft"
    EVALUATING = "evaluating"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class DatasetCategory(Base):
    __tablename__ = "dataset_categories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name_zh: Mapped[str] = mapped_column(String(200))
    name_en: Mapped[str] = mapped_column(String(200))
    color: Mapped[str] = mapped_column(String(7), default="#4f7f79")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint("status IN ('active','archived')", name="ck_datasets_status"),
        Index("ix_datasets_project_status", "project_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[DatasetStatus] = mapped_column(String(20), default=DatasetStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint("dataset_id", "version_number"),
        CheckConstraint("version_number > 0", name="ck_dataset_versions_number"),
        CheckConstraint(
            "status IN ('draft','frozen','training','published','archived')",
            name="ck_dataset_versions_status",
        ),
        CheckConstraint(
            "train_ratio BETWEEN 0 AND 100 AND val_ratio BETWEEN 0 AND 100 "
            "AND test_ratio BETWEEN 0 AND 100",
            name="ck_dataset_split_ranges",
        ),
        CheckConstraint("train_ratio + val_ratio + test_ratio = 100", name="ck_dataset_split_sum"),
        CheckConstraint(
            "sample_count >= 0 AND annotation_count >= 0 AND byte_size >= 0",
            name="ck_dataset_version_counters",
        ),
        CheckConstraint("revision > 0", name="ck_dataset_version_revision"),
        Index("ix_dataset_versions_dataset_status", "dataset_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[VersionStatus] = mapped_column(String(20), default=VersionStatus.DRAFT)
    source: Mapped[str] = mapped_column(String(100), default="upload")
    train_ratio: Mapped[int] = mapped_column(Integer, default=80)
    val_ratio: Mapped[int] = mapped_column(Integer, default=10)
    test_ratio: Mapped[int] = mapped_column(Integer, default=10)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    annotation_count: Mapped[int] = mapped_column(Integer, default=0)
    byte_size: Mapped[int] = mapped_column(BigInteger, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DatasetSample(Base):
    __tablename__ = "dataset_samples"
    __table_args__ = (
        CheckConstraint("media_type IN ('image','video')", name="ck_dataset_sample_media_type"),
        CheckConstraint("byte_size > 0", name="ck_dataset_sample_byte_size"),
        CheckConstraint(
            "(width IS NULL OR width > 0) AND (height IS NULL OR height > 0)",
            name="ck_dataset_sample_dimensions",
        ),
        CheckConstraint(
            "(frame_index IS NULL OR frame_index >= 0) "
            "AND (timestamp_ms IS NULL OR timestamp_ms >= 0)",
            name="ck_dataset_sample_frame_position",
        ),
        CheckConstraint(
            "split IN ('unassigned','train','val','test')", name="ck_dataset_sample_split"
        ),
        CheckConstraint(
            "review_status IN ('unreviewed','approved','changes_requested')",
            name="ck_dataset_sample_review_status",
        ),
        CheckConstraint("revision > 0", name="ck_dataset_sample_revision"),
        Index("ix_dataset_samples_version_split", "version_id", "split"),
        Index("ix_dataset_samples_version_hash", "version_id", "sha256"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(20), default="image")
    mime_type: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_video_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dataset_samples.id", ondelete="SET NULL"), nullable=True
    )
    frame_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    split: Mapped[SampleSplit] = mapped_column(String(20), default=SampleSplit.UNASSIGNED)
    review_status: Mapped[ReviewStatus] = mapped_column(String(30), default=ReviewStatus.UNREVIEWED)
    duplicate_group: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SampleAnnotation(Base):
    __tablename__ = "sample_annotations"
    __table_args__ = (
        CheckConstraint("cx BETWEEN 0 AND 1", name="ck_annotation_cx"),
        CheckConstraint("cy BETWEEN 0 AND 1", name="ck_annotation_cy"),
        CheckConstraint("width > 0 AND width <= 1", name="ck_annotation_width"),
        CheckConstraint("height > 0 AND height <= 1", name="ck_annotation_height"),
        CheckConstraint(
            "cx - width / 2 >= 0 AND cx + width / 2 <= 1 "
            "AND cy - height / 2 >= 0 AND cy + height / 2 <= 1",
            name="ck_annotation_within_image",
        ),
        Index("ix_annotations_sample", "sample_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sample_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_samples.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dataset_categories.id"))
    cx: Mapped[float] = mapped_column(Float)
    cy: Mapped[float] = mapped_column(Float)
    width: Mapped[float] = mapped_column(Float)
    height: Mapped[float] = mapped_column(Float)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DatasetChange(Base):
    __tablename__ = "dataset_changes"
    __table_args__ = (Index("ix_dataset_changes_sample_created", "sample_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dataset_versions.id"), index=True)
    sample_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dataset_samples.id", ondelete="CASCADE"), nullable=True
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100))
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class QualityFinding(Base):
    __tablename__ = "quality_findings"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('info','warning','error')", name="ck_quality_finding_severity"
        ),
        Index("ix_quality_version_code", "version_id", "code", "resolved"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"), index=True
    )
    sample_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dataset_samples.id", ondelete="CASCADE"), nullable=True
    )
    code: Mapped[str] = mapped_column(String(100))
    severity: Mapped[FindingSeverity] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(String(1000))
    suggestion: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LifecycleJob(Base):
    __tablename__ = "lifecycle_jobs"
    __table_args__ = (
        CheckConstraint("progress BETWEEN 0 AND 100", name="ck_lifecycle_job_progress"),
        CheckConstraint("attempt >= 1 AND max_attempts >= attempt", name="ck_lifecycle_attempts"),
        CheckConstraint(
            "kind IN ('extract','validate','export','train','evaluate')",
            name="ck_lifecycle_job_kind",
        ),
        CheckConstraint(
            "status IN ('queued','running','cancelling','cancelled','succeeded','failed')",
            name="ck_lifecycle_job_status",
        ),
        Index("ix_lifecycle_jobs_queue", "status", "queued_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[LifecycleJobKind] = mapped_column(String(20), index=True)
    status: Mapped[LifecycleJobStatus] = mapped_column(
        String(20), default=LifecycleJobStatus.QUEUED, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True
    )
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    progress_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, default=2)
    claimed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    log_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class TrainingMetric(Base):
    __tablename__ = "training_metrics"
    __table_args__ = (
        UniqueConstraint("job_id", "epoch"),
        CheckConstraint("epoch >= 0", name="ck_training_metric_epoch"),
        CheckConstraint(
            "(map50 IS NULL OR map50 BETWEEN 0 AND 1) "
            "AND (map50_95 IS NULL OR map50_95 BETWEEN 0 AND 1) "
            "AND (precision IS NULL OR precision BETWEEN 0 AND 1) "
            "AND (recall IS NULL OR recall BETWEEN 0 AND 1) "
            "AND (f1 IS NULL OR f1 BETWEEN 0 AND 1)",
            name="ck_training_metric_scores",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lifecycle_jobs.id", ondelete="CASCADE"), index=True, nullable=True
    )
    epoch: Mapped[int] = mapped_column(Integer)
    train_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    val_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    map50: Mapped[float | None] = mapped_column(Float, nullable=True)
    map50_95: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    f1: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LifecycleArtifact(Base):
    __tablename__ = "lifecycle_artifacts"
    __table_args__ = (CheckConstraint("byte_size >= 0", name="ck_lifecycle_artifact_byte_size"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lifecycle_jobs.id", ondelete="CASCADE"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(50))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ManagedModelVersion(Base):
    __tablename__ = "managed_model_versions"
    __table_args__ = (
        UniqueConstraint("code", "version_number"),
        CheckConstraint("version_number > 0", name="ck_managed_model_version_number"),
        CheckConstraint("scene IN ('pipeline','ppe')", name="ck_managed_model_scene"),
        CheckConstraint("size_variant IN ('n','s','m','l','x')", name="ck_model_size_variant"),
        CheckConstraint(
            "status IN ('draft','evaluating','published','archived')",
            name="ck_managed_model_status",
        ),
        Index("ix_managed_models_status", "status", "scene"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(100), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    scene: Mapped[str] = mapped_column(String(30))
    size_variant: Mapped[str] = mapped_column(String(1))
    status: Mapped[ManagedModelStatus] = mapped_column(
        String(20), default=ManagedModelStatus.DRAFT, index=True
    )
    training_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lifecycle_jobs.id", ondelete="SET NULL"), nullable=True
    )
    dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True
    )
    weight_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lifecycle_artifacts.id"))
    model_card: Mapped[str] = mapped_column(Text)
    class_map_json: Mapped[list[str]] = mapped_column(JSON)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ModelDeployment(Base):
    __tablename__ = "model_deployments"
    __table_args__ = (
        UniqueConstraint("project_id", "scene"),
        CheckConstraint("rollout_percent BETWEEN 0 AND 100", name="ck_deployment_rollout"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    scene: Mapped[str] = mapped_column(String(30))
    model_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("managed_model_versions.id"))
    previous_model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("managed_model_versions.id"), nullable=True
    )
    rollout_percent: Mapped[int] = mapped_column(Integer, default=100)
    deployed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
