from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .auth import digest_session_token, enforce_rate_limit, rate_limit_key
from .config import Settings, get_settings
from .database import SessionLocal, get_engine
from .dependencies import AuthContext, AuthDep, DbDep, SettingsDep, client_ip, require_same_origin
from .detection_media import MediaValidationError, SavedUpload, resolve_storage_key, save_upload
from .detection_models import (
    DetectionJob,
    DetectionKind,
    DetectionMedia,
    DetectionMetric,
    DetectionObservation,
    JobStatus,
    MediaRole,
    MediaType,
    VisionModel,
)
from .detection_schemas import (
    DetectionJobOut,
    DetectionMediaOut,
    DetectionMetricOut,
    DetectionObservationOut,
    DetectionParameters,
    ObsStartRequest,
    ObsUpdateRequest,
    VisionModelOut,
)
from .detection_service import (
    create_detection_job,
    request_job_cancel,
    require_job_access,
    require_model,
    require_project_access,
    retry_detection_job,
)
from .errors import InfraError
from .models import AuthSession, User, UserRole, UserStatus
from .services import record_audit

router = APIRouter(tags=["vision-detection"])
BATCH_IMAGE_MAX_BYTES = 2 * 1024**3


def _model_out(model: VisionModel) -> VisionModelOut:
    result = VisionModelOut.model_validate(model)
    result.engine_configured = bool(model.engine_path)
    return result


def _job_out(
    db: Session,
    job: DetectionJob,
    observation_limit: int = 200,
    *,
    include_details: bool = True,
) -> DetectionJobOut:
    result = DetectionJobOut.model_validate(job)
    if not include_details:
        return result
    result.media = [
        DetectionMediaOut.model_validate(item)
        for item in db.scalars(
            select(DetectionMedia)
            .where(DetectionMedia.job_id == job.id)
            .order_by(DetectionMedia.created_at)
        )
    ]
    result.observations = [
        DetectionObservationOut.model_validate(item)
        for item in db.scalars(
            select(DetectionObservation)
            .where(DetectionObservation.job_id == job.id)
            .order_by(DetectionObservation.timestamp_ms, DetectionObservation.frame_index)
            .limit(observation_limit)
        )
    ]
    result.metrics = [
        DetectionMetricOut.model_validate(item)
        for item in db.scalars(
            select(DetectionMetric)
            .where(DetectionMetric.job_id == job.id)
            .order_by(DetectionMetric.sample_at.desc())
            .limit(100)
        )
    ]
    return result


def _remove_saved_upload(root: Path, saved: SavedUpload | None) -> None:
    if saved is not None:
        resolve_storage_key(root, saved.storage_key).unlink(missing_ok=True)


def _limit_upload(request: Request, context: AuthContext, settings: Settings) -> None:
    redis_url = settings.redis_url.get_secret_value()
    source_ip = client_ip(request)
    for key, limit in (
        (rate_limit_key("detection-upload-ip", source_ip), 60),
        (rate_limit_key("detection-upload-user", source_ip, str(context.user.id)), 30),
    ):
        enforce_rate_limit(
            redis_url,
            key,
            limit=limit,
            window_seconds=600,
            error_prefix="detection",
        )


def _parameters(value: str) -> DetectionParameters:
    try:
        return DetectionParameters.model_validate_json(value)
    except (ValueError, json.JSONDecodeError) as exc:
        raise InfraError(422, "validation.failed") from exc


def _media_from_upload(
    job_id: uuid.UUID,
    media_type: MediaType,
    saved,
) -> DetectionMedia:
    return DetectionMedia(
        job_id=job_id,
        role=MediaRole.ORIGINAL,
        media_type=media_type,
        storage_key=saved.storage_key,
        original_name=saved.original_name,
        mime_type=saved.mime_type,
        byte_size=saved.byte_size,
        sha256=saved.sha256,
        width=saved.width,
        height=saved.height,
        duration_seconds=saved.duration_seconds,
        fps=saved.fps,
        frame_count=saved.frame_count,
    )


@router.get("/vision/models", response_model=list[VisionModelOut])
def list_vision_models(context: AuthDep, db: DbDep) -> list[VisionModelOut]:
    del context
    return [
        _model_out(model) for model in db.scalars(select(VisionModel).order_by(VisionModel.code))
    ]


@router.post(
    "/detections/images",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_same_origin)],
)
async def upload_images(
    request: Request,
    context: AuthDep,
    db: DbDep,
    settings: SettingsDep,
    project_id: Annotated[uuid.UUID, Form()],
    model_id: Annotated[uuid.UUID, Form()],
    parameters: Annotated[str, Form()] = "{}",
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> list[dict]:
    _limit_upload(request, context, settings)
    files = files or []
    if not 1 <= len(files) <= 100:
        raise InfraError(422, "validation.failed")
    model = require_model(db, model_id)
    require_project_access(db, context.user, project_id)
    payload = _parameters(parameters)
    results: list[dict] = []
    accepted_bytes = 0
    for upload in files:
        job_id = uuid.uuid4()
        saved = None
        try:
            remaining_bytes = BATCH_IMAGE_MAX_BYTES - accepted_bytes
            if remaining_bytes <= 0:
                raise MediaValidationError("detection.image_batch_too_large")
            saved = await save_upload(
                upload,
                root=settings.storage_root,
                job_id=job_id,
                media_type="image",
                max_bytes=min(settings.infrasentinel_image_max_mb * 1024**2, remaining_bytes),
                critical_free_gb=settings.infrasentinel_storage_critical_gb,
            )
            job = create_detection_job(
                db,
                user=context.user,
                project_id=project_id,
                model=model,
                kind=DetectionKind.IMAGE,
                parameters=payload.model_dump(exclude_none=True),
                job_id=job_id,
                commit=False,
            )
            db.add(_media_from_upload(job.id, MediaType.IMAGE, saved))
            db.commit()
            accepted_bytes += saved.byte_size
            results.append({"filename": saved.original_name, "job_id": str(job.id), "error": None})
        except MediaValidationError as exc:
            db.rollback()
            results.append(
                {
                    "filename": getattr(upload, "filename", "upload"),
                    "job_id": None,
                    "error": exc.code,
                }
            )
        except Exception:
            db.rollback()
            _remove_saved_upload(settings.storage_root, saved)
            raise
    return results


@router.post(
    "/detections/videos",
    response_model=DetectionJobOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_same_origin)],
)
async def upload_video(
    request: Request,
    context: AuthDep,
    db: DbDep,
    settings: SettingsDep,
    project_id: Annotated[uuid.UUID, Form()],
    model_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File()],
    parameters: Annotated[str, Form()] = "{}",
) -> DetectionJobOut:
    _limit_upload(request, context, settings)
    model = require_model(db, model_id)
    require_project_access(db, context.user, project_id)
    payload = _parameters(parameters)
    job_id = uuid.uuid4()
    saved = None
    try:
        saved = await save_upload(
            file,
            root=settings.storage_root,
            job_id=job_id,
            media_type="video",
            max_bytes=settings.infrasentinel_video_max_gb * 1024**3,
            max_video_seconds=settings.infrasentinel_video_max_seconds,
            critical_free_gb=settings.infrasentinel_storage_critical_gb,
        )
        job = create_detection_job(
            db,
            user=context.user,
            project_id=project_id,
            model=model,
            kind=DetectionKind.VIDEO,
            parameters=payload.model_dump(exclude_none=True),
            job_id=job_id,
            commit=False,
        )
        db.add(_media_from_upload(job.id, MediaType.VIDEO, saved))
        db.commit()
        db.refresh(job)
        return _job_out(db, job)
    except MediaValidationError as exc:
        raise InfraError(422, exc.code) from exc
    except Exception:
        db.rollback()
        _remove_saved_upload(settings.storage_root, saved)
        raise


@router.get("/detections/jobs", response_model=list[DetectionJobOut])
def list_detection_jobs(
    context: AuthDep,
    db: DbDep,
    project_id: uuid.UUID | None = None,
    kind: Literal["image", "video", "obs"] | None = None,
    job_status: Literal["queued", "running", "cancelling", "cancelled", "succeeded", "failed"]
    | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[DetectionJobOut]:
    query = select(DetectionJob).order_by(DetectionJob.created_at.desc()).limit(limit)
    if context.user.role != UserRole.ADMIN:
        query = query.where(DetectionJob.owner_id == context.user.id)
    if project_id:
        require_project_access(db, context.user, project_id)
        query = query.where(DetectionJob.project_id == project_id)
    if kind:
        query = query.where(DetectionJob.kind == kind)
    if job_status:
        query = query.where(DetectionJob.status == job_status)
    return [_job_out(db, job, include_details=False) for job in db.scalars(query)]


@router.get("/detections/jobs/{job_id}", response_model=DetectionJobOut)
def get_detection_job(job_id: uuid.UUID, context: AuthDep, db: DbDep) -> DetectionJobOut:
    return _job_out(db, require_job_access(db, context.user, job_id))


@router.post(
    "/detections/jobs/{job_id}/cancel",
    response_model=DetectionJobOut,
    dependencies=[Depends(require_same_origin)],
)
def cancel_detection_job(job_id: uuid.UUID, context: AuthDep, db: DbDep) -> DetectionJobOut:
    job = require_job_access(db, context.user, job_id)
    return _job_out(db, request_job_cancel(db, user=context.user, job=job))


@router.post(
    "/detections/jobs/{job_id}/retry",
    response_model=DetectionJobOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_same_origin)],
)
def retry_job(job_id: uuid.UUID, context: AuthDep, db: DbDep) -> DetectionJobOut:
    job = require_job_access(db, context.user, job_id)
    return _job_out(db, retry_detection_job(db, user=context.user, job=job))


@router.get("/detections/media/{media_id}")
def get_detection_media(
    media_id: uuid.UUID, context: AuthDep, db: DbDep, settings: SettingsDep
) -> FileResponse:
    media = db.get(DetectionMedia, media_id)
    if media is None:
        raise InfraError(404, "http.not_found")
    require_job_access(db, context.user, media.job_id)
    path = resolve_storage_key(settings.storage_root, media.storage_key)
    if not path.is_file():
        raise InfraError(404, "http.not_found")
    return FileResponse(
        path,
        media_type=media.mime_type,
        filename=media.original_name,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post(
    "/detections/obs",
    response_model=DetectionJobOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_same_origin)],
)
def start_obs(payload: ObsStartRequest, context: AuthDep, db: DbDep) -> DetectionJobOut:
    if db.bind and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(20260902)"))
    active = db.scalar(
        select(DetectionJob.id).where(
            DetectionJob.kind == DetectionKind.OBS,
            DetectionJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCELLING]),
        )
    )
    if active:
        raise InfraError(409, "detection.obs_busy")
    model = require_model(db, payload.model_id)
    job = create_detection_job(
        db,
        user=context.user,
        project_id=payload.project_id,
        model=model,
        kind=DetectionKind.OBS,
        parameters=payload.parameters.model_dump(exclude_none=True),
    )
    return _job_out(db, job)


@router.patch(
    "/detections/obs/{job_id}",
    response_model=DetectionJobOut,
    dependencies=[Depends(require_same_origin)],
)
def update_obs(
    job_id: uuid.UUID,
    payload: ObsUpdateRequest,
    context: AuthDep,
    db: DbDep,
) -> DetectionJobOut:
    job = require_job_access(db, context.user, job_id)
    if job.kind != DetectionKind.OBS or job.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
        raise InfraError(409, "detection.job_not_cancellable")
    before = dict(job.parameters_json)
    job.parameters_json = {**before, **payload.model_dump(exclude_none=True)}
    record_audit(
        db,
        action="detection.obs_update",
        target_type="detection_job",
        target_id=job.id,
        actor_id=context.user.id,
        before_state=before,
        after_state=job.parameters_json,
    )
    db.commit()
    db.refresh(job)
    return _job_out(db, job)


@router.post(
    "/detections/obs/{job_id}/stop",
    response_model=DetectionJobOut,
    dependencies=[Depends(require_same_origin)],
)
def stop_obs(job_id: uuid.UUID, context: AuthDep, db: DbDep) -> DetectionJobOut:
    job = require_job_access(db, context.user, job_id)
    if job.kind != DetectionKind.OBS:
        raise InfraError(404, "detection.job_not_found")
    return _job_out(db, request_job_cancel(db, user=context.user, job=job))


def _websocket_user(websocket: WebSocket, db: Session) -> User | None:
    settings = get_settings()
    token = websocket.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    auth_session = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == digest_session_token(token))
    )
    if auth_session is None or auth_session.revoked_at is not None:
        return None
    user = db.get(User, auth_session.user_id)
    return user if user and user.status == UserStatus.ENABLED else None


@router.websocket("/detections/obs/{job_id}/preview")
async def obs_preview(websocket: WebSocket, job_id: uuid.UUID) -> None:
    with SessionLocal(bind=get_engine()) as db:
        user = _websocket_user(websocket, db)
        if user is None:
            await websocket.close(code=4401)
            return
        try:
            require_job_access(db, user, job_id)
        except InfraError:
            await websocket.close(code=4403)
            return
    await websocket.accept()
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url.get_secret_value())
    key = f"infrasentinel:obs:{job_id}:preview"
    try:
        previous = b""
        while True:
            frame = await redis.get(key)
            if frame and frame != previous:
                await websocket.send_bytes(frame)
                previous = frame
            else:
                await websocket.send_json({"state": "stale"})
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    finally:
        await redis.aclose()
