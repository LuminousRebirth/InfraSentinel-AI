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
        "lifecycle.dataset_not_found": "数据集不存在",
        "lifecycle.version_not_found": "数据集版本不存在",
        "lifecycle.sample_not_found": "数据样本不存在",
        "lifecycle.version_immutable": "该数据集版本已冻结，不能再修改",
        "lifecycle.invalid_split": "训练、验证和测试拆分比例无效",
        "lifecycle.revision_conflict": "样本已被其他人修改，请刷新后重试",
        "lifecycle.invalid_category": "标注类别不存在或已停用",
        "lifecycle.invalid_annotation": "标注框坐标无效",
        "lifecycle.quality_blocked": "数据质量检查未通过，暂时不能冻结",
        "lifecycle.invalid_archive": "上传文件不是有效的 ZIP 数据集",
        "lifecycle.archive_unsafe_path": "压缩包包含不安全路径",
        "lifecycle.archive_link_forbidden": "压缩包不能包含符号链接",
        "lifecycle.archive_device_forbidden": "压缩包不能包含设备或特殊文件",
        "lifecycle.archive_duplicate_path": "压缩包包含重复文件路径",
        "lifecycle.archive_encrypted": "暂不支持加密压缩包",
        "lifecycle.archive_nested": "压缩包不能嵌套其他压缩文件",
        "lifecycle.archive_entry_limit": "压缩包文件数量超出限制",
        "lifecycle.archive_entry_too_large": "压缩包内单个文件过大",
        "lifecycle.archive_too_large": "压缩包解压后大小超出限制",
        "lifecycle.archive_ratio": "压缩包压缩率异常，已拒绝导入",
        "lifecycle.archive_no_images": "压缩包中没有支持的图片",
        "lifecycle.invalid_label": "YOLO 标注文件格式无效",
        "lifecycle.invalid_image": "数据集图片无法解码",
        "lifecycle.version_not_trainable": "仅已冻结的数据集版本可以训练",
        "lifecycle.job_not_found": "生命周期任务不存在",
        "lifecycle.job_not_cancellable": "当前任务状态无法取消",
        "lifecycle.job_not_retryable": "当前任务状态无法重试",
        "lifecycle.max_attempts_exceeded": "任务重试次数已耗尽",
        "lifecycle.model_not_found": "模型版本不存在",
        "lifecycle.model_not_publishable": "当前模型状态无法发布",
        "lifecycle.model_quality_blocked": "模型评估指标未达到发布门槛",
        "lifecycle.model_card_required": "发布前必须填写模型卡",
        "lifecycle.artifact_integrity_failed": "模型权重完整性校验失败",
        "lifecycle.evaluation_required": "模型完成评估后才能发布",
        "lifecycle.model_not_published": "仅已发布模型可以部署",
        "lifecycle.deployment_not_found": "模型部署不存在",
        "lifecycle.deployment_no_rollback": "该部署没有可回滚的历史版本",
        "lifecycle.base_model_required": "请配置可信的本地 YOLO 基础权重",
        "lifecycle.runner_unavailable": "本地 Ultralytics 训练器不可用",
        "lifecycle.training_output_missing": "训练未生成最佳权重文件",
        "lifecycle.invalid_video": "数据集视频无法解码",
        "lifecycle.media_batch_limit": "单次媒体文件数量超出限制",
        "lifecycle.unsupported_media": "不支持该媒体格式",
        "lifecycle.category_conflict": "数据类别代号已存在",
        "lifecycle.invalid_training_config": "训练参数超出允许范围",
        "lifecycle.invalid_extraction_config": "视频抽帧参数超出允许范围",
        "lifecycle.no_annotation_history": "没有可撤销或重做的标注记录",
        "lifecycle.model_deployed": "模型仍在项目中使用，不能归档",
        "lifecycle.cancelled": "任务已取消",
        "lifecycle.processing_failed": "生命周期任务执行失败",
        "lifecycle.unsupported_job_kind": "不支持该生命周期任务类型",
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
        "lifecycle.dataset_not_found": "The dataset was not found",
        "lifecycle.version_not_found": "The dataset version was not found",
        "lifecycle.sample_not_found": "The dataset sample was not found",
        "lifecycle.version_immutable": "The dataset version is immutable",
        "lifecycle.invalid_split": "The train, validation, and test split is invalid",
        "lifecycle.revision_conflict": "The sample changed; refresh and try again",
        "lifecycle.invalid_category": "The category is missing or disabled",
        "lifecycle.invalid_annotation": "The annotation coordinates are invalid",
        "lifecycle.quality_blocked": "Quality checks must pass before freezing",
        "lifecycle.invalid_archive": "The upload is not a valid ZIP dataset",
        "lifecycle.archive_unsafe_path": "The archive contains an unsafe path",
        "lifecycle.archive_link_forbidden": "Archive links are not allowed",
        "lifecycle.archive_device_forbidden": "Archive device and special files are not allowed",
        "lifecycle.archive_duplicate_path": "The archive contains duplicate file paths",
        "lifecycle.archive_encrypted": "Encrypted archives are not supported",
        "lifecycle.archive_nested": "Nested archives are not allowed",
        "lifecycle.archive_entry_limit": "The archive has too many entries",
        "lifecycle.archive_entry_too_large": "An archive entry is too large",
        "lifecycle.archive_too_large": "The expanded archive is too large",
        "lifecycle.archive_ratio": "The archive compression ratio is unsafe",
        "lifecycle.archive_no_images": "The archive has no supported images",
        "lifecycle.invalid_label": "A YOLO label file is invalid",
        "lifecycle.invalid_image": "A dataset image could not be decoded",
        "lifecycle.version_not_trainable": "Only frozen dataset versions can be trained",
        "lifecycle.job_not_found": "The lifecycle job was not found",
        "lifecycle.job_not_cancellable": "The job cannot be cancelled in its current state",
        "lifecycle.job_not_retryable": "The job cannot be retried in its current state",
        "lifecycle.max_attempts_exceeded": "The job exhausted all attempts",
        "lifecycle.model_not_found": "The model version was not found",
        "lifecycle.model_not_publishable": "The model cannot be published in its current state",
        "lifecycle.model_quality_blocked": "Model metrics are below the publication threshold",
        "lifecycle.model_card_required": "A model card is required before publication",
        "lifecycle.artifact_integrity_failed": "The model weight failed integrity verification",
        "lifecycle.evaluation_required": "Complete model evaluation before publication",
        "lifecycle.model_not_published": "Only published models can be deployed",
        "lifecycle.deployment_not_found": "The model deployment was not found",
        "lifecycle.deployment_no_rollback": "The deployment has no previous version",
        "lifecycle.base_model_required": "Configure a trusted local YOLO base weight",
        "lifecycle.runner_unavailable": "The local Ultralytics runner is unavailable",
        "lifecycle.training_output_missing": "Training did not produce a best weight",
        "lifecycle.invalid_video": "A dataset video could not be decoded",
        "lifecycle.media_batch_limit": "The media batch exceeds the file-count limit",
        "lifecycle.unsupported_media": "The media format is unsupported",
        "lifecycle.category_conflict": "The category code already exists",
        "lifecycle.invalid_training_config": "Training parameters are out of bounds",
        "lifecycle.invalid_extraction_config": "Frame extraction parameters are out of bounds",
        "lifecycle.no_annotation_history": "There is no annotation change to restore",
        "lifecycle.model_deployed": "The model is still deployed and cannot be archived",
        "lifecycle.cancelled": "The job was cancelled",
        "lifecycle.processing_failed": "The lifecycle job failed",
        "lifecycle.unsupported_job_kind": "The lifecycle job type is unsupported",
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
