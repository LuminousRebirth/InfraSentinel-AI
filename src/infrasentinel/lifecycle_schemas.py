from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CategoryOut(OrmModel):
    id: uuid.UUID
    code: str
    name_zh: str
    name_en: str
    color: str
    enabled: bool


class CategoryWrite(BaseModel):
    code: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    name_zh: str = Field(min_length=1, max_length=200)
    name_en: str = Field(min_length=1, max_length=200)
    color: str = Field(default="#4f7f79", pattern=r"^#[0-9A-Fa-f]{6}$")
    enabled: bool = True


class CategoryUpdate(BaseModel):
    name_zh: str | None = Field(default=None, min_length=1, max_length=200)
    name_en: str | None = Field(default=None, min_length=1, max_length=200)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    enabled: bool | None = None


class DatasetCreate(BaseModel):
    project_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class VersionCreate(BaseModel):
    source: str = Field(default="upload", min_length=1, max_length=100)
    train_ratio: int = Field(default=80, ge=0, le=100)
    val_ratio: int = Field(default=10, ge=0, le=100)
    test_ratio: int = Field(default=10, ge=0, le=100)

    @model_validator(mode="after")
    def ratios_total_100(self) -> VersionCreate:
        if self.train_ratio + self.val_ratio + self.test_ratio != 100:
            raise ValueError("split ratios must total 100")
        return self


class VersionOut(OrmModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    version_number: int
    status: Literal["draft", "frozen", "training", "published", "archived"]
    source: str
    train_ratio: int
    val_ratio: int
    test_ratio: int
    sample_count: int
    annotation_count: int
    byte_size: int
    revision: int
    frozen_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DatasetOut(OrmModel):
    id: uuid.UUID
    project_id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    status: Literal["active", "archived"]
    created_at: datetime
    updated_at: datetime
    versions: list[VersionOut] = Field(default_factory=list)


class AnnotationWrite(BaseModel):
    category_id: uuid.UUID
    cx: float = Field(ge=0, le=1)
    cy: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


class AnnotationReplace(BaseModel):
    expected_revision: int = Field(ge=1)
    annotations: list[AnnotationWrite] = Field(max_length=1000)


class RevisionRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class ReviewWrite(RevisionRequest):
    status: Literal["approved", "changes_requested"]


class AnnotationOut(AnnotationWrite, OrmModel):
    id: uuid.UUID


class SampleOut(OrmModel):
    id: uuid.UUID
    version_id: uuid.UUID
    original_name: str
    mime_type: str
    byte_size: int
    sha256: str
    width: int | None
    height: int | None
    split: Literal["unassigned", "train", "val", "test"]
    review_status: Literal["unreviewed", "approved", "changes_requested"]
    duplicate_group: str | None
    revision: int
    annotations: list[AnnotationOut] = Field(default_factory=list)


class QualityFindingOut(OrmModel):
    id: uuid.UUID
    version_id: uuid.UUID
    sample_id: uuid.UUID | None
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    suggestion: str | None
    resolved: bool
    created_at: datetime


class ImportResult(BaseModel):
    imported_samples: int
    imported_annotations: int
    duplicate_samples: int
    version: VersionOut


class LifecycleJobCreate(BaseModel):
    version_id: uuid.UUID
    kind: Literal["extract", "validate", "export", "train", "evaluate"] = "train"
    config: dict = Field(default_factory=dict)


class LifecycleJobOut(OrmModel):
    id: uuid.UUID
    kind: Literal["extract", "validate", "export", "train", "evaluate"]
    status: Literal["queued", "running", "cancelling", "cancelled", "succeeded", "failed"]
    project_id: uuid.UUID
    owner_id: uuid.UUID
    version_id: uuid.UUID | None
    model_version_id: uuid.UUID | None
    config_json: dict
    result_json: dict | None
    progress: int
    progress_detail: str | None
    error_code: str | None
    error_detail: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class TrainingMetricOut(OrmModel):
    epoch: int
    train_loss: float | None
    val_loss: float | None
    map50: float | None
    map50_95: float | None
    precision: float | None
    recall: float | None
    f1: float | None
    created_at: datetime


class ManagedModelOut(OrmModel):
    id: uuid.UUID
    code: str
    version_number: int
    scene: str
    size_variant: Literal["n", "s", "m", "l", "x"]
    status: Literal["draft", "evaluating", "published", "archived"]
    training_job_id: uuid.UUID | None
    dataset_version_id: uuid.UUID | None
    weight_artifact_id: uuid.UUID
    model_card: str
    class_map_json: list[str]
    metrics_json: dict
    published_at: datetime | None
    created_at: datetime


class TrustedModelImport(BaseModel):
    version_id: uuid.UUID
    code: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    scene: Literal["pipeline", "ppe"]
    size_variant: Literal["n", "s", "m", "l", "x"] = "n"
    storage_key: str = Field(min_length=4, max_length=500)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    model_card: str = Field(min_length=1, max_length=10_000)
    class_map: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        min_length=1, max_length=100
    )
    metrics: dict[str, float] = Field(default_factory=dict, max_length=100)


class DeploymentWrite(BaseModel):
    project_id: uuid.UUID
    rollout_percent: int = Field(default=100, ge=0, le=100)


class DeploymentOut(OrmModel):
    id: uuid.UUID
    project_id: uuid.UUID
    scene: str
    model_version_id: uuid.UUID
    previous_model_version_id: uuid.UUID | None
    rollout_percent: int
    deployed_by: uuid.UUID
    updated_at: datetime
