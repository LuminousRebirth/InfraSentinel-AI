from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .detection_models import (
    DetectionKind,
    JobStatus,
    MediaRole,
    MediaType,
    ModelAvailability,
    ModelBackend,
    VisionScene,
)


class DetectionParameters(BaseModel):
    confidence: float = Field(default=0.35, ge=0.01, le=1)
    iou: float = Field(default=0.70, ge=0.01, le=1)
    input_size: int | None = Field(default=None, ge=320, le=1280)
    device: str = Field(default="auto", max_length=32)
    detection_fps: float | None = Field(default=None, ge=0.5, le=30)
    output_quality: Literal["standard", "high"] = "standard"
    resolution: Literal["640p", "720p"] | None = None

    @field_validator("input_size")
    @classmethod
    def input_size_multiple(cls, value: int | None) -> int | None:
        if value is not None and value % 32:
            raise ValueError("input size must be a multiple of 32")
        return value


class VisionModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name_zh: str
    name_en: str
    scene: VisionScene
    classes_json: list[str]
    input_size: int
    preferred_backend: ModelBackend
    availability: ModelAvailability
    unavailable_reason: str | None
    version_label: str
    engine_configured: bool = False


class DetectionMediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MediaRole
    media_type: MediaType
    original_name: str
    mime_type: str
    byte_size: int
    sha256: str
    width: int | None
    height: int | None
    duration_seconds: float | None
    fps: float | None
    frame_count: int | None


class DetectionObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    frame_index: int
    timestamp_ms: int
    class_name: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float
    inference_ms: float


class DetectionMetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sample_at: datetime
    processed_frames: int
    effective_fps: float
    inference_p50_ms: float
    gpu_percent: float | None
    gpu_memory_used_mb: int | None
    gpu_memory_total_mb: int | None


class DetectionJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: DetectionKind
    status: JobStatus
    project_id: uuid.UUID
    owner_id: uuid.UUID
    model_id: uuid.UUID
    scene: VisionScene
    parameters_json: dict
    result_json: dict | None
    progress_percent: int
    progress_detail: str | None
    attempt: int
    max_attempts: int
    retry_of_id: uuid.UUID | None
    error_code: str | None
    error_detail: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    media: list[DetectionMediaOut] = Field(default_factory=list)
    observations: list[DetectionObservationOut] = Field(default_factory=list)
    metrics: list[DetectionMetricOut] = Field(default_factory=list)


class ObsStartRequest(BaseModel):
    project_id: uuid.UUID
    model_id: uuid.UUID
    parameters: DetectionParameters = Field(default_factory=DetectionParameters)


class ObsUpdateRequest(BaseModel):
    confidence: float | None = Field(default=None, ge=0.01, le=1)
    iou: float | None = Field(default=None, ge=0.01, le=1)
    detection_fps: float | None = Field(default=None, ge=1, le=30)
    resolution: Literal["640p", "720p"] | None = None
