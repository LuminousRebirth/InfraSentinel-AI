from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from .database import utc_now
from .errors import InfraError
from .lifecycle_models import (
    DatasetVersion,
    LifecycleArtifact,
    LifecycleJob,
    LifecycleJobKind,
    LifecycleJobStatus,
    ManagedModelStatus,
    ManagedModelVersion,
    ModelDeployment,
    TrainingMetric,
    VersionStatus,
)
from .lifecycle_service import require_admin, require_version_access
from .models import User
from .services import record_audit
from .storage import safe_path
from .vision_models import sha256_file

TERMINAL_JOB_STATUSES = {
    LifecycleJobStatus.CANCELLED,
    LifecycleJobStatus.SUCCEEDED,
    LifecycleJobStatus.FAILED,
}


class LifecycleCancelled(RuntimeError):
    pass


def create_lifecycle_job(
    db: Session,
    *,
    user: User,
    version: DatasetVersion,
    kind: LifecycleJobKind,
    config: dict[str, Any] | None = None,
) -> LifecycleJob:
    require_admin(user)
    require_version_access(db, user, version.id)
    _validate_job_config(kind, config or {})
    if kind == LifecycleJobKind.TRAIN and version.status != VersionStatus.FROZEN:
        raise InfraError(409, "lifecycle.version_not_trainable")
    job = LifecycleJob(
        kind=kind,
        project_id=_project_id(db, version),
        owner_id=user.id,
        version_id=version.id,
        config_json=config or {},
    )
    db.add(job)
    if kind == LifecycleJobKind.EVALUATE:
        model_id = (config or {}).get("model_version_id")
        model = db.get(ManagedModelVersion, uuid.UUID(str(model_id))) if model_id else None
        if model is None or model.dataset_version_id != version.id:
            raise InfraError(422, "lifecycle.model_not_found")
        job.model_version_id = model.id
        model.status = ManagedModelStatus.EVALUATING
    if kind == LifecycleJobKind.TRAIN:
        version.status = VersionStatus.TRAINING
    record_audit(
        db,
        action=f"lifecycle.job_{kind.value}_create",
        target_type="lifecycle_job",
        target_id=job.id,
        actor_id=user.id,
        after_state={"version_id": str(version.id), "config": config or {}},
    )
    db.commit()
    db.refresh(job)
    return job


def _validate_job_config(kind: LifecycleJobKind, config: dict[str, Any]) -> None:
    if kind == LifecycleJobKind.TRAIN:
        epochs = int(config.get("epochs", 50))
        batch = config.get("batch", 8)
        imgsz = int(config.get("imgsz", 640))
        learning_rate = float(config.get("learning_rate", 0.01))
        if not 1 <= epochs <= 1000 or not 320 <= imgsz <= 1536 or not 0 < learning_rate <= 1:
            raise InfraError(422, "lifecycle.invalid_training_config")
        if batch != "auto" and not 1 <= int(batch) <= 256:
            raise InfraError(422, "lifecycle.invalid_training_config")
    if kind == LifecycleJobKind.EXTRACT:
        interval = float(config.get("interval_seconds", 1))
        max_frames = int(config.get("max_frames", 1000))
        if not 0.1 <= interval <= 60 or not 1 <= max_frames <= 10_000:
            raise InfraError(422, "lifecycle.invalid_extraction_config")


def _project_id(db: Session, version: DatasetVersion) -> uuid.UUID:
    from .lifecycle_models import Dataset

    dataset = db.get(Dataset, version.dataset_id)
    if dataset is None:
        raise InfraError(404, "lifecycle.dataset_not_found")
    return dataset.project_id


def claim_next_lifecycle_job(
    db: Session, worker_id: str, lease_seconds: int = 120
) -> LifecycleJob | None:
    now = utc_now()
    exhausted = db.scalar(
        select(LifecycleJob)
        .where(
            LifecycleJob.status == LifecycleJobStatus.RUNNING,
            LifecycleJob.lease_expires_at < now,
            LifecycleJob.attempt >= LifecycleJob.max_attempts,
        )
        .order_by(LifecycleJob.queued_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if exhausted is not None:
        fail_lifecycle_job(db, exhausted, "lifecycle.max_attempts_exceeded")
    candidate = db.scalar(
        select(LifecycleJob)
        .where(
            or_(
                LifecycleJob.status == LifecycleJobStatus.QUEUED,
                (
                    (LifecycleJob.status == LifecycleJobStatus.RUNNING)
                    & (LifecycleJob.lease_expires_at < now)
                    & (LifecycleJob.attempt < LifecycleJob.max_attempts)
                ),
            )
        )
        .order_by(LifecycleJob.queued_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if candidate is None:
        return None
    if candidate.status == LifecycleJobStatus.RUNNING:
        candidate.attempt += 1
    candidate.status = LifecycleJobStatus.RUNNING
    candidate.claimed_by = worker_id[:100]
    candidate.started_at = candidate.started_at or now
    candidate.lease_expires_at = now + timedelta(seconds=lease_seconds)
    candidate.progress_detail = "running"
    db.commit()
    db.refresh(candidate)
    return candidate


def heartbeat_lifecycle_job(
    db: Session,
    job: LifecycleJob,
    worker_id: str,
    *,
    progress: int,
    detail: str,
    lease_seconds: int = 120,
) -> bool:
    now = utc_now()
    result = db.execute(
        update(LifecycleJob)
        .where(
            LifecycleJob.id == job.id,
            LifecycleJob.status == LifecycleJobStatus.RUNNING,
            LifecycleJob.claimed_by == worker_id,
        )
        .values(
            progress=max(0, min(99, progress)),
            progress_detail=detail[:500],
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            updated_at=now,
        )
    )
    db.commit()
    return bool(result.rowcount)


def complete_lifecycle_job(
    db: Session, job: LifecycleJob, result: dict[str, Any] | None = None
) -> None:
    job.status = LifecycleJobStatus.SUCCEEDED
    job.progress = 100
    job.progress_detail = "completed"
    job.result_json = result or {}
    job.finished_at = utc_now()
    job.lease_expires_at = None
    db.commit()


def fail_lifecycle_job(
    db: Session, job: LifecycleJob, code: str, detail: str | None = None
) -> None:
    job.status = LifecycleJobStatus.FAILED
    job.error_code = code[:100]
    job.error_detail = (detail or "")[:1000] or None
    job.finished_at = utc_now()
    job.lease_expires_at = None
    if job.kind == LifecycleJobKind.TRAIN and job.version_id:
        version = db.get(DatasetVersion, job.version_id)
        if version and version.status == VersionStatus.TRAINING:
            version.status = VersionStatus.FROZEN
    db.commit()


def request_lifecycle_cancel(db: Session, *, user: User, job: LifecycleJob) -> LifecycleJob:
    require_admin(user)
    if job.status in TERMINAL_JOB_STATUSES:
        raise InfraError(409, "lifecycle.job_not_cancellable")
    job.cancel_requested = True
    if job.status == LifecycleJobStatus.QUEUED:
        job.status = LifecycleJobStatus.CANCELLED
        job.finished_at = utc_now()
    else:
        job.status = LifecycleJobStatus.CANCELLING
    record_audit(
        db,
        action="lifecycle.job_cancel",
        target_type="lifecycle_job",
        target_id=job.id,
        actor_id=user.id,
    )
    db.commit()
    db.refresh(job)
    return job


def retry_lifecycle_job(db: Session, *, user: User, job: LifecycleJob) -> LifecycleJob:
    require_admin(user)
    if job.status not in {LifecycleJobStatus.CANCELLED, LifecycleJobStatus.FAILED}:
        raise InfraError(409, "lifecycle.job_not_retryable")
    version = db.get(DatasetVersion, job.version_id) if job.version_id else None
    if version is None:
        raise InfraError(404, "lifecycle.version_not_found")
    retry = LifecycleJob(
        kind=job.kind,
        project_id=job.project_id,
        owner_id=user.id,
        version_id=job.version_id,
        model_version_id=job.model_version_id,
        config_json=job.config_json,
        attempt=job.attempt + 1,
        max_attempts=max(job.max_attempts, job.attempt + 1),
    )
    if job.kind == LifecycleJobKind.TRAIN:
        version.status = VersionStatus.TRAINING
    db.add(retry)
    db.flush()
    record_audit(
        db,
        action="lifecycle.job_retry",
        target_type="lifecycle_job",
        target_id=retry.id,
        actor_id=user.id,
        after_state={"retry_of": str(job.id), "attempt": retry.attempt},
    )
    db.commit()
    db.refresh(retry)
    return retry


def create_fake_training_result(
    db: Session,
    *,
    job: LifecycleJob,
    storage_root: Path,
) -> ManagedModelVersion:
    if job.version_id is None:
        raise InfraError(409, "lifecycle.version_not_trainable")
    config = job.config_json or {}
    epochs = max(1, min(int(config.get("epochs", 5)), 20))
    for epoch in range(1, epochs + 1):
        db.refresh(job)
        if job.cancel_requested:
            raise LifecycleCancelled("lifecycle.cancelled")
        progress = epoch / epochs
        db.add(
            TrainingMetric(
                job_id=job.id,
                epoch=epoch,
                train_loss=round(1.0 - 0.6 * progress, 4),
                val_loss=round(1.1 - 0.55 * progress, 4),
                map50=round(0.45 + 0.4 * progress, 4),
                map50_95=round(0.25 + 0.35 * progress, 4),
                precision=round(0.5 + 0.35 * progress, 4),
                recall=round(0.45 + 0.35 * progress, 4),
                f1=round(0.47 + 0.35 * progress, 4),
            )
        )
    code = str(config.get("code", "infrasentinel-custom"))[:100]
    next_version = (
        db.scalar(
            select(func.max(ManagedModelVersion.version_number)).where(
                ManagedModelVersion.code == code
            )
        )
        or 0
    ) + 1
    body = f"fake-ultralytics-weight:{job.id}:{job.version_id}".encode()
    digest = hashlib.sha256(body).hexdigest()
    storage_key = f"models/{code}/v{next_version}/{digest[:16]}.pt"
    path = storage_root.joinpath(*Path(storage_key).parts).resolve()
    if not path.is_relative_to(storage_root.resolve()):
        raise ValueError("artifact path escaped storage root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    artifact = LifecycleArtifact(
        job_id=job.id,
        kind="weights",
        storage_key=storage_key,
        mime_type="application/octet-stream",
        byte_size=len(body),
        sha256=digest,
    )
    db.add(artifact)
    db.flush()
    metrics = {
        "map50": 0.85,
        "map50_95": 0.60,
        "precision": 0.85,
        "recall": 0.80,
        "f1": 0.82,
        "runner": "fake",
    }
    model = ManagedModelVersion(
        code=code,
        version_number=next_version,
        scene=str(config.get("scene", "pipeline"))[:30],
        size_variant=str(config.get("size_variant", "n"))[:1],
        training_job_id=job.id,
        dataset_version_id=job.version_id,
        weight_artifact_id=artifact.id,
        model_card=str(config.get("model_card", "Acceptance model generated by fake runner")),
        class_map_json=list(config.get("classes", ["CK", "PL", "SG", "SL", "TL", "ZW"])),
        metrics_json=metrics,
        created_by=job.owner_id,
    )
    db.add(model)
    job.model_version_id = model.id
    version = db.get(DatasetVersion, job.version_id)
    if version:
        version.status = VersionStatus.FROZEN
    db.commit()
    db.refresh(model)
    return model


def publish_model(
    db: Session,
    *,
    user: User,
    model: ManagedModelVersion,
    storage_root: Path,
) -> ManagedModelVersion:
    from .detection_models import (
        ModelAvailability,
        ModelBackend,
        VisionModel,
        VisionScene,
    )

    require_admin(user)
    metrics = model.metrics_json or {}
    if model.status not in {ManagedModelStatus.DRAFT, ManagedModelStatus.EVALUATING}:
        raise InfraError(409, "lifecycle.model_not_publishable")
    evaluation = db.scalar(
        select(LifecycleJob.id).where(
            LifecycleJob.kind == LifecycleJobKind.EVALUATE,
            LifecycleJob.status == LifecycleJobStatus.SUCCEEDED,
            LifecycleJob.model_version_id == model.id,
        )
    )
    if evaluation is None:
        raise InfraError(409, "lifecycle.evaluation_required")
    if not model.model_card.strip():
        raise InfraError(409, "lifecycle.model_card_required")
    if float(metrics.get("map50", 0)) < 0.5 or float(metrics.get("precision", 0)) < 0.5:
        raise InfraError(409, "lifecycle.model_quality_blocked")
    artifact = db.get(LifecycleArtifact, model.weight_artifact_id)
    if artifact is None:
        raise InfraError(409, "lifecycle.training_output_missing")
    weight_path = safe_path(storage_root, *Path(artifact.storage_key).parts)
    if not weight_path.is_file() or sha256_file(weight_path) != artifact.sha256:
        raise InfraError(409, "lifecycle.artifact_integrity_failed")
    model.status = ManagedModelStatus.PUBLISHED
    model.approved_by = user.id
    model.published_at = utc_now()
    runtime_code = f"{model.code[:38]}-v{model.version_number}"
    runtime = db.scalar(select(VisionModel).where(VisionModel.code == runtime_code))
    values = {
        "name_zh": f"自训练模型 {model.code} V{model.version_number}",
        "name_en": f"Custom model {model.code} V{model.version_number}",
        "scene": VisionScene(model.scene),
        "pt_path": str(weight_path),
        "asset_sha256": artifact.sha256,
        "classes_json": model.class_map_json,
        "input_size": 640,
        "preferred_backend": ModelBackend.PT,
        "availability": ModelAvailability.AVAILABLE,
        "unavailable_reason": None,
        "version_label": f"managed-v{model.version_number}",
        "synced_at": utc_now(),
    }
    if runtime is None:
        runtime = VisionModel(code=runtime_code, engine_path=None, **values)
        db.add(runtime)
    else:
        for key, value in values.items():
            setattr(runtime, key, value)
    record_audit(
        db,
        action="lifecycle.model_publish",
        target_type="managed_model_version",
        target_id=model.id,
        actor_id=user.id,
        after_state={"runtime_code": runtime_code, "sha256": artifact.sha256},
    )
    db.commit()
    db.refresh(model)
    return model


def deploy_model(
    db: Session,
    *,
    user: User,
    project_id: uuid.UUID,
    model: ManagedModelVersion,
    rollout_percent: int = 100,
) -> ModelDeployment:
    from .detection_service import require_project_access

    require_admin(user)
    require_project_access(db, user, project_id)
    if model.status != ManagedModelStatus.PUBLISHED:
        raise InfraError(409, "lifecycle.model_not_published")
    deployment = db.scalar(
        select(ModelDeployment).where(
            ModelDeployment.project_id == project_id,
            ModelDeployment.scene == model.scene,
        )
    )
    if deployment is None:
        deployment = ModelDeployment(
            project_id=project_id,
            scene=model.scene,
            model_version_id=model.id,
            rollout_percent=rollout_percent,
            deployed_by=user.id,
        )
        db.add(deployment)
    else:
        deployment.previous_model_version_id = deployment.model_version_id
        deployment.model_version_id = model.id
        deployment.rollout_percent = rollout_percent
        deployment.deployed_by = user.id
    db.flush()
    record_audit(
        db,
        action="lifecycle.model_deploy",
        target_type="model_deployment",
        target_id=deployment.id,
        actor_id=user.id,
        after_state={
            "project_id": str(project_id),
            "model_version_id": str(model.id),
            "rollout_percent": rollout_percent,
        },
    )
    db.commit()
    db.refresh(deployment)
    return deployment


def rollback_deployment(db: Session, *, user: User, deployment: ModelDeployment) -> ModelDeployment:
    require_admin(user)
    if deployment.previous_model_version_id is None:
        raise InfraError(409, "lifecycle.deployment_no_rollback")
    current = deployment.model_version_id
    deployment.model_version_id = deployment.previous_model_version_id
    deployment.previous_model_version_id = current
    deployment.deployed_by = user.id
    record_audit(
        db,
        action="lifecycle.deployment_rollback",
        target_type="model_deployment",
        target_id=deployment.id,
        actor_id=user.id,
        before_state={"model_version_id": str(current)},
        after_state={"model_version_id": str(deployment.model_version_id)},
    )
    db.commit()
    db.refresh(deployment)
    return deployment
