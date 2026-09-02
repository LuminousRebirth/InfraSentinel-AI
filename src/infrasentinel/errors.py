from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

MESSAGES: dict[str, dict[str, str]] = {
    "zh-CN": {
        "validation.failed": "请求内容无效",
        "http.not_found": "请求的资源不存在",
        "auth.invalid_credentials": "用户名或密码错误",
        "auth.pending": "账号正在等待管理员审核",
        "auth.disabled": "账号已停用",
        "auth.rejected": "账号申请已被拒绝",
        "auth.required": "请先登录",
        "auth.forbidden": "没有执行此操作的权限",
        "auth.project_access_denied": "没有该项目的访问权限",
        "auth.identity_conflict": "邮箱或用户名已被使用",
        "auth.invalid_current_password": "当前密码错误",
        "auth.rate_limited": "尝试次数过多，请稍后再试",
        "auth.rate_limit_unavailable": "登录保护服务暂时不可用",
        "auth.cross_origin_denied": "请求来源不受信任",
        "admin.last_admin": "不能停用最后一个可用管理员",
        "admin.user_not_found": "用户不存在",
        "project.not_found": "项目不存在",
        "project.code_conflict": "项目编号已存在",
        "detection.model_not_found": "检测模型不存在",
        "detection.model_unavailable": "检测模型当前不可用",
        "detection.job_not_found": "检测任务不存在",
        "detection.job_not_cancellable": "当前状态无法取消任务",
        "detection.job_not_retryable": "当前任务无法重试",
        "detection.invalid_image": "图片无法解码",
        "detection.invalid_video": "视频无法解码",
        "detection.unsupported_image": "不支持该图片格式",
        "detection.unsupported_video": "不支持该视频格式",
        "detection.image_too_large": "图片超过大小限制",
        "detection.image_batch_too_large": "本批图片总大小超过 2 GB 限制",
        "detection.video_too_large": "视频超过大小限制",
        "detection.video_too_long": "视频超过时长限制",
        "detection.storage_full": "存储空间不足，暂时无法接收媒体",
        "detection.obs_busy": "已有实时检测会话正在运行",
        "detection.processing_failed": "检测处理失败",
        "detection.rate_limited": "上传过于频繁，请稍后再试",
        "detection.rate_limit_unavailable": "上传保护服务暂时不可用",
    },
    "en": {
        "validation.failed": "The request is invalid",
        "http.not_found": "The requested resource was not found",
        "auth.invalid_credentials": "Invalid username or password",
        "auth.pending": "Your account is waiting for administrator approval",
        "auth.disabled": "Your account is disabled",
        "auth.rejected": "Your account request was rejected",
        "auth.required": "Sign in to continue",
        "auth.forbidden": "You do not have permission to perform this action",
        "auth.project_access_denied": "You do not have access to this project",
        "auth.identity_conflict": "The email or username is already in use",
        "auth.invalid_current_password": "The current password is incorrect",
        "auth.rate_limited": "Too many attempts. Try again later",
        "auth.rate_limit_unavailable": "Sign-in protection is temporarily unavailable",
        "auth.cross_origin_denied": "The request origin is not trusted",
        "admin.last_admin": "The last enabled administrator cannot be disabled",
        "admin.user_not_found": "The user was not found",
        "project.not_found": "The project was not found",
        "project.code_conflict": "The project code is already in use",
        "detection.model_not_found": "The detection model was not found",
        "detection.model_unavailable": "The detection model is unavailable",
        "detection.job_not_found": "The detection job was not found",
        "detection.job_not_cancellable": "The job cannot be cancelled in its current state",
        "detection.job_not_retryable": "The job cannot be retried",
        "detection.invalid_image": "The image could not be decoded",
        "detection.invalid_video": "The video could not be decoded",
        "detection.unsupported_image": "This image format is not supported",
        "detection.unsupported_video": "This video format is not supported",
        "detection.image_too_large": "The image exceeds the size limit",
        "detection.image_batch_too_large": "The image batch exceeds the 2 GB limit",
        "detection.video_too_large": "The video exceeds the size limit",
        "detection.video_too_long": "The video exceeds the duration limit",
        "detection.storage_full": "Storage is too low to accept media",
        "detection.obs_busy": "A live detection session is already active",
        "detection.processing_failed": "Detection processing failed",
        "detection.rate_limited": "Too many uploads. Try again later",
        "detection.rate_limit_unavailable": "Upload protection is temporarily unavailable",
    },
}

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


class InfraError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        *,
        fields: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.fields = fields


def resolve_locale(accept_language: str | None, preferred: str | None = None) -> str:
    if preferred in MESSAGES:
        return preferred
    value = (accept_language or "").lower()
    return "en" if value.startswith("en") or ",en" in value else "zh-CN"


def message_for(code: str, locale: str) -> str:
    return MESSAGES.get(locale, MESSAGES["zh-CN"]).get(code, code)


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    fields: list[dict[str, str]] | None = None,
) -> JSONResponse:
    locale = resolve_locale(request.headers.get("accept-language"))
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message_for(code, locale),
                "request_id": request_id,
                "fields": fields,
            }
        },
        headers={"X-Request-ID": request_id},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        supplied = request.headers.get("x-request-id", "")
        request.state.request_id = (
            supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid.uuid4())
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(InfraError)
    async def infra_error_handler(request: Request, exc: InfraError) -> JSONResponse:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            fields=exc.fields,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields = [
            {
                "field": ".".join(str(part) for part in item["loc"] if part != "body"),
                "message": item["type"],
            }
            for item in exc.errors()
        ]
        return error_response(request, status_code=422, code="validation.failed", fields=fields)

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        code = "http.not_found" if exc.status_code == 404 else f"http.{exc.status_code}"
        return error_response(request, status_code=exc.status_code, code=code)


def redact_secrets(value: Any) -> Any:
    blocked = ("password", "secret", "token", "cookie", "api_key", "authorization", "hash")
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]"
            if any(part in str(key).lower() for part in blocked)
            else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value
