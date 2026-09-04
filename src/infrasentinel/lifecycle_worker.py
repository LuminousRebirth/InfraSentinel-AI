from __future__ import annotations

import logging
import socket
import time

from sqlalchemy.orm import Session

from .config import get_settings
from .database import SessionLocal, get_engine, utc_now
from .lifecycle_jobs import (
    LifecycleCancelled,
    claim_next_lifecycle_job,
    complete_lifecycle_job,
    create_fake_training_result,
    fail_lifecycle_job,
    heartbeat_lifecycle_job,
)
from .lifecycle_media import extract_video_frames
from .lifecycle_models import (
    DatasetVersion,
    LifecycleJobKind,
    LifecycleJobStatus,
    ManagedModelVersion,
)
from .lifecycle_training import (
    evaluate_with_ultralytics,
    package_yolo_export,
    train_with_ultralytics,
)

LOGGER = logging.getLogger("infrasentinel.lifecycle-worker")


def process_next(db: Session, *, worker_id: str, fake_runner: bool) -> bool:
    settings = get_settings()
    job = claim_next_lifecycle_job(
        db, worker_id, lease_seconds=settings.infrasentinel_task_lease_seconds
    )
    if job is None:
        return False
    try:
        if job.cancel_requested:
            raise LifecycleCancelled("lifecycle.cancelled")
        heartbeat_lifecycle_job(db, job, worker_id, progress=5, detail="preparing")
        if job.kind == LifecycleJobKind.EXPORT:
            artifact = package_yolo_export(db, job, settings.storage_root)
            complete_lifecycle_job(
                db, job, {"artifact_id": str(artifact.id), "storage_key": artifact.storage_key}
            )
        elif job.kind == LifecycleJobKind.EXTRACT:
            version = db.get(DatasetVersion, job.version_id)
            if version is None:
                raise ValueError("dataset version not found")
            frames = extract_video_frames(
                db,
                version=version,
                storage_root=settings.storage_root,
                interval_seconds=float(job.config_json.get("interval_seconds", 1)),
                max_frames=int(job.config_json.get("max_frames", 1000)),
                actor_id=job.owner_id,
            )
            complete_lifecycle_job(db, job, {"frames": len(frames)})
        elif job.kind == LifecycleJobKind.TRAIN:
            model = (
                create_fake_training_result(db, job=job, storage_root=settings.storage_root)
                if fake_runner
                else train_with_ultralytics(db, job=job, storage_root=settings.storage_root)
            )
            complete_lifecycle_job(db, job, {"model_version_id": str(model.id)})
        elif job.kind == LifecycleJobKind.EVALUATE:
            model = db.get(ManagedModelVersion, job.model_version_id)
            if model is None:
                raise ValueError("managed model not found")
            if fake_runner:
                metrics = dict(model.metrics_json or {})
                metrics.update(job.config_json.get("metrics", {}))
                model.metrics_json = metrics
                db.commit()
            else:
                metrics = evaluate_with_ultralytics(db, job=job, storage_root=settings.storage_root)
            complete_lifecycle_job(db, job, metrics)
        else:
            fail_lifecycle_job(db, job, "lifecycle.unsupported_job_kind")
    except LifecycleCancelled:
        job.status = LifecycleJobStatus.CANCELLED
        job.progress_detail = "cancelled"
        job.finished_at = utc_now()
        db.commit()
    except Exception as exc:
        LOGGER.exception("Lifecycle job %s failed", job.id)
        fail_lifecycle_job(db, job, "lifecycle.processing_failed", str(exc))
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    fake_runner = settings.infrasentinel_lifecycle_fake_runner
    worker_id = f"{socket.gethostname()}-lifecycle"
    while True:
        with SessionLocal(bind=get_engine()) as db:
            worked = process_next(db, worker_id=worker_id, fake_runner=fake_runner)
        if not worked:
            time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
