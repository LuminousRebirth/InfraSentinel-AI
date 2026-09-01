from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import AuditResult, ProjectStatus, UserRole, UserStatus

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{3,32}$")
PROJECT_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,49}$")


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    username: str = Field(min_length=3, max_length=32)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=6, max_length=128)
    locale: Literal["zh-CN", "en"] = "zh-CN"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("invalid email")
        return normalized

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not USERNAME_PATTERN.fullmatch(normalized):
            raise ValueError("invalid username")
        return normalized

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str) -> str:
        return value.strip()


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("identifier")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        return value.strip().lower()


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    locale: Literal["zh-CN", "en"] | None = None


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


class UserStatusUpdate(BaseModel):
    status: Literal["enabled", "disabled", "rejected"]
    rejection_reason: str | None = Field(default=None, max_length=500)


class ProjectCreate(BaseModel):
    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=1, max_length=200)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not PROJECT_CODE_PATTERN.fullmatch(normalized):
            raise ValueError("invalid project code")
        return normalized

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip()


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    status: ProjectStatus


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    username: str
    display_name: str
    role: UserRole
    status: UserStatus
    locale: Literal["zh-CN", "en"]
    rejection_reason: str | None
    reviewed_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime
    projects: list[ProjectOut] = Field(default_factory=list)


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    source_ip: str | None
    action: str
    target_type: str
    target_id: uuid.UUID | None
    before_state: dict | None
    after_state: dict | None
    result: AuditResult
    detail: str | None
    created_at: datetime
