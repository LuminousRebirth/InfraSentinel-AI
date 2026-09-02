from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AlertRuleWrite(BaseModel):
    code: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    name_zh: str = Field(min_length=1, max_length=200)
    name_en: str = Field(min_length=1, max_length=200)
    project_id: uuid.UUID | None = None
    class_name: str = Field(min_length=1, max_length=100)
    min_confidence: float = Field(default=0.01, ge=0, le=1)
    risk_level: Literal["low", "medium", "high"]
    merge_window_ms: int = Field(default=3000, ge=0, le=600000)
    iou_threshold: float = Field(default=0.3, ge=0, le=1)
    cooldown_seconds: int = Field(default=60, ge=0, le=86400)
    priority: int = Field(default=100, ge=-10000, le=10000)
    enabled: bool = True


class AlertRuleOut(AlertRuleWrite, OrmModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class AlertOut(OrmModel):
    id: uuid.UUID
    event_id: uuid.UUID
    project_id: uuid.UUID
    owner_id: uuid.UUID
    final_level: Literal["low", "medium", "high"]
    status: Literal["pending_confirmation", "assigned", "processing", "resolved", "false_positive"]
    title_zh: str
    title_en: str
    summary: str | None
    assignee_id: uuid.UUID | None
    response_due_at: datetime | None
    close_due_at: datetime | None
    resolution_note: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class EventOut(OrmModel):
    id: uuid.UUID
    job_id: uuid.UUID
    class_name: str
    first_timestamp_ms: int
    last_timestamp_ms: int
    observation_count: int
    max_confidence: float
    keyframe_media_id: uuid.UUID | None


class AlertActionOut(OrmModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    before_state: dict | None
    after_state: dict | None
    detail: str | None
    created_at: datetime


class AlertAttachmentOut(OrmModel):
    id: uuid.UUID
    uploader_id: uuid.UUID
    original_name: str
    mime_type: str
    byte_size: int
    sha256: str
    created_at: datetime


class AlertDetailOut(AlertOut):
    event: EventOut
    actions: list[AlertActionOut]
    attachments: list[AlertAttachmentOut]
    analysis: AnalysisOut | None


class AlertUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    status: (
        Literal["pending_confirmation", "assigned", "processing", "resolved", "false_positive"]
        | None
    ) = None
    assignee_id: uuid.UUID | None = None
    final_level: Literal["low", "medium", "high"] | None = None
    note: str | None = Field(default=None, max_length=1000)
    response_due_at: datetime | None = None
    close_due_at: datetime | None = None


class ProviderWrite(BaseModel):
    code: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    provider: Literal["qwen", "deepseek", "glm"]
    endpoint: str = Field(min_length=1, max_length=2048)
    model_name: str = Field(min_length=1, max_length=200)
    supports_vision: bool = True
    timeout_seconds: int = Field(default=60, ge=1, le=300)
    max_retries: int = Field(default=2, ge=0, le=5)
    enabled: bool = True
    is_default: bool = False


class ProviderOut(ProviderWrite, OrmModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CredentialWrite(BaseModel):
    api_key: str = Field(min_length=8, max_length=4096)


class AnalysisRequest(BaseModel):
    prefer_personal: bool = False


class AnalysisOut(OrmModel):
    id: uuid.UUID
    job_id: uuid.UUID | None
    event_id: uuid.UUID | None
    status: Literal[
        "waiting_configuration", "queued", "running", "succeeded", "failed", "cancelled"
    ]
    prefer_personal: bool
    result_json: dict | None
    error_code: str | None
    requested_at: datetime
    finished_at: datetime | None


class ObjectAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: uuid.UUID
    severity: Literal["low", "medium", "high", "unknown"]
    explanation: str = Field(min_length=1, max_length=1000)
    possible_causes: list[str] = Field(default_factory=list, max_length=10)
    repair_suggestions: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("possible_causes", "repair_suggestions")
    @classmethod
    def bound_items(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 500 for item in value):
            raise ValueError("analysis list items must contain 1-500 characters")
        return value


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objects: list[ObjectAnalysis] = Field(default_factory=list, max_length=100)
    global_risk: Literal["low", "medium", "high", "unknown"]
    conclusion: str = Field(min_length=1, max_length=2000)
    priorities: list[str] = Field(default_factory=list, max_length=20)
    associations: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("priorities", "associations")
    @classmethod
    def bound_items(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 500 for item in value):
            raise ValueError("analysis list items must contain 1-500 characters")
        return value
