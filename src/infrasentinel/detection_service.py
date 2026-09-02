from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from .database import utc_now
from .detection_models import (
    DetectionJob,
    DetectionKind,
    DetectionMedia,
    JobStatus,
    ModelAvailability,
    VisionModel,
)
from .errors import InfraError
from .models import AuditResult, Project, ProjectMembership, ProjectStatus, User, UserRole
from .services import record_audit

TERMINAL_STATUSES = {JobStatus.CANCELLED, JobStatus.SUCCEEDED, JobStatus.FAILED}


def require_project_access(db: Session, user: User, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.status != ProjectStatus.ACTIVE:
        raise InfraError(404, "project.not_found")
    if user.role != UserRole.ADMIN and db.get(ProjectMembership, (user.id, project_id)) is None:
        raise InfraError(403, "auth.project_access_denied")
    return project


def require_model(db: Session, model_id: uuid.UUID) -> VisionModel:
    model = db.get(VisionModel, model_id)
    if model is None:
        raise InfraError(404, "detection.model_not_found")
    if model.availability != ModelAvailability.AVAILABLE:
        raise InfraError(409, "detection.model_unavailable")
    return model


def require_job_access(db: Session, user: User, job_id: uuid.UUID) -> DetectionJob:
    job = db.get(DetectionJob, job_id)
    if job is None:
        raise InfraError(404, "detection.job_not_found")
    require_project_access(db, user, job.project_id)
    if user.role != UserRole.ADMIN and job.owner_id != user.id:
        raise InfraError(403, "auth.forbidden")
    return job


def create_detection_job(
    db: Session,
    *,
    user: User,
    project_id: uuid.UUID,
    model: VisionModel,
    kind: DetectionKind,
    parameters: dict[str, Any],
    job_id: uuid.UUID | None = None,
    commit: bool = True,
) -> DetectionJob:
    require_project_access(db, user, project_id)
    if model.availability != ModelAvailability.AVAILABLE:
        raise InfraError(409, "detection.model_unavailable")
    job = DetectionJob(
        id=job_id or uuid.uuid4(),
        kind=kind,
        status=JobStatus.QUEUED,
        project_id=project_id,
        point_id=project_id,
        owner_id=user.id,
        model_id=model.id,
        scene=model.scene,
        parameters_json=parameters,
    )
    db.add(job)
    db.flush()
    record_audit(
        db,
        action="detection.job_create",
        target_type="detection_job",
        target_id=job.id,
        actor_id=user.id,
        after_state={
            "kind": kind.value,
            "project_id": str(project_id),
            "model_id": str(model.id),
            "parameters": parameters,
        },
    )
    if commit:
        db.commit()
        db.refresh(job)
    return job


def claim_next_job(db: Session, worker_id: str, lease_seconds: int) -> DetectionJob | None:
    now = utc_now()
    exhausted = db.scalar(
        select(DetectionJob)
        .where(
            DetectionJob.status == JobStatus.RUNNING,
            DetectionJob.lease_expires_at < now,
            DetectionJob.attempt >= DetectionJob.max_attempts,
        )
        .order_by(DetectionJob.queued_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if exhausted is not None:
        fail_job(db, exhausted, "detection.max_attempts_exceeded")
        now = utc_now()
    # ponytail: single-host PostgreSQL queue; add a broker only for multi-host load.
    candidate = db.scalar(
        select(DetectionJob)
        .where(
            or_(
                DetectionJob.status == JobStatus.QUEUED,
                (
                    (DetectionJob.status == JobStatus.RUNNING)
                    & (DetectionJob.lease_expires_at < now)
                    & (DetectionJob.attempt < DetectionJob.max_attempts)
                ),
            )
        )
        .order_by(DetectionJob.queued_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if candidate is None:
        return None
    if candidate.status == JobStatus.RUNNING:
        candidate.attempt += 1
    candidate.status = JobStatus.RUNNING
    candidate.claimed_by = worker_id[:100]
    candidate.started_at = candidate.started_at or now
    candidate.heartbeat_at = now
    candidate.lease_expires_at = now + timedelta(seconds=lease_seconds)
    candidate.progress_detail = "running"
    record_audit(
        db,
        action="detection.job_start",
        target_type="detection_job",
        target_id=candidate.id,
        actor_id=candidate.owner_id,
        after_state={"attempt": candidate.attempt, "worker": candidate.claimed_by},
    )
    db.commit()
    db.refresh(candidate)
    return candidate


def heartbeat_job(
    db: Session,
    job_id: uuid.UUID,
    worker_id: str,
    lease_seconds: int,
    *,
    progress: int | None = None,
    detail: str | None = None,
) -> bool:
    now = utc_now()
    values: dict[str, Any] = {
        "heartbeat_at": now,
        "lease_expires_at": now + timedelta(seconds=lease_seconds),
        "updated_at": now,
    }
    if progress is not None:
        values["progress_percent"] = max(0, min(99, progress))
    if detail is not None:
        values["progress_detail"] = detail[:500]
    result = db.execute(
        update(DetectionJob)
        .where(
            DetectionJob.id == job_id,
            DetectionJob.status == JobStatus.RUNNING,
            DetectionJob.claimed_by == worker_id,
        )
        .values(**values)
    )
    db.commit()
    return result.rowcount == 1


def cancellation_requested(db: Session, job_id: uuid.UUID) -> bool:
    status = db.scalar(select(DetectionJob.status).where(DetectionJob.id == job_id))
    return status in {JobStatus.CANCELLING, JobStatus.CANCELLED}


def request_job_cancel(db: Session, *, user: User, job: DetectionJob) -> DetectionJob:
    if job.status == JobStatus.QUEUED:
        job.status = JobStatus.CANCELLED
        job.progress_detail = "cancelled"
        job.cancel_requested_at = job.cancelled_at = job.finished_at = utc_now()
    elif job.status == JobStatus.RUNNING:
        job.status = JobStatus.CANCELLING
        job.cancel_requested_at = utc_now()
        job.progress_detail = "cancelling"
    elif job.status == JobStatus.CANCELLING:
        return job
    else:
        raise InfraError(409, "detection.job_not_cancellable")
    record_audit(
        db,
        action="detection.job_cancel",
        target_type="detection_job",
        target_id=job.id,
        actor_id=user.id,
        after_state={"status": job.status.value},
    )
    db.commit()
    db.refresh(job)
    return job


def retry_detection_job(db: Session, *, user: User, job: DetectionJob) -> DetectionJob:
    if job.status not in {JobStatus.FAILED, JobStatus.CANCELLED} or job.attempt >= job.max_attempts:
        raise InfraError(409, "detection.job_not_retryable")
    retry = DetectionJob(
        kind=job.kind,
        status=JobStatus.QUEUED,
        project_id=job.project_id,
        point_id=job.point_id,
        owner_id=job.owner_id,
        model_id=job.model_id,
        scene=job.scene,
        parameters_json=dict(job.parameters_json),
        attempt=job.attempt + 1,
        max_attempts=job.max_attempts,
        retry_of_id=job.id,
    )
    db.add(retry)
    db.flush()
    record_audit(
        db,
        action="detection.job_retry",
        target_type="detection_job",
        target_id=retry.id,
        actor_id=user.id,
        after_state={"retry_of_id": str(job.id), "attempt": retry.attempt},
    )
    db.commit()
    db.refresh(retry)
    return retry


def input_media_for_job(db: Session, job: DetectionJob) -> DetectionMedia | None:
    source_id = job.id
    current = job
    while current.retry_of_id:
        source_id = current.retry_of_id
        current = db.get(DetectionJob, source_id) or current
        if current.id != source_id:
            break
    return db.scalar(
        select(DetectionMedia).where(
            DetectionMedia.job_id == source_id,
            DetectionMedia.role == "original",
        )
    )


def complete_job(db: Session, job: DetectionJob, result: dict[str, Any]) -> None:
    job.status = JobStatus.SUCCEEDED
    job.result_json = result
    job.progress_percent = 100
    job.progress_detail = "completed"
    job.finished_at = utc_now()
    job.lease_expires_at = None
    record_audit(
        db,
        action="detection.job_succeed",
        target_type="detection_job",
        target_id=job.id,
        actor_id=job.owner_id,
        after_state={"status": job.status.value, "result": result},
    )
    db.commit()


def cancel_running_job(db: Session, job: DetectionJob) -> None:
    job.status = JobStatus.CANCELLED
    job.progress_detail = "cancelled"
    job.cancelled_at = job.finished_at = utc_now()
    job.lease_expires_at = None
    record_audit(
        db,
        action="detection.job_cancelled",
        target_type="detection_job",
        target_id=job.id,
        actor_id=job.owner_id,
        after_state={"status": job.status.value},
    )
    db.commit()


def fail_job(db: Session, job: DetectionJob, code: str, detail: str = "") -> None:
    job.status = JobStatus.FAILED
    job.error_code = code[:100]
    job.error_detail = detail[:1000] or None
    job.progress_detail = "failed"
    job.finished_at = utc_now()
    job.lease_expires_at = None
    record_audit(
        db,
        action="detection.job_fail",
        target_type="detection_job",
        target_id=job.id,
        actor_id=job.owner_id,
        result=AuditResult.FAILURE,
        detail=code,
    )
    db.commit()
