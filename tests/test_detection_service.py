from __future__ import annotations

from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from infrasentinel.database import Base, utc_now
from infrasentinel.detection_models import (
    DetectionKind,
    JobStatus,
    ModelAvailability,
    VisionModel,
    VisionScene,
)
from infrasentinel.detection_service import (
    claim_next_job,
    create_detection_job,
    request_job_cancel,
    retry_detection_job,
)
from infrasentinel.models import Project, ProjectMembership, User, UserRole, UserStatus


def make_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def test_job_lifecycle_claim_cancel_and_retry() -> None:
    with make_db() as db:
        user = User(
            email="worker@example.com",
            username="worker",
            display_name="Worker",
            password_hash="hash",
            role=UserRole.USER,
            status=UserStatus.ENABLED,
        )
        project = Project(code="P1", name="Plant")
        model = VisionModel(
            code="pipeline-local",
            name_zh="管道",
            name_en="Pipeline",
            scene=VisionScene.PIPELINE,
            classes_json=["CK"],
            input_size=640,
            availability=ModelAvailability.AVAILABLE,
        )
        db.add_all([user, project, model])
        db.flush()
        db.add(ProjectMembership(user_id=user.id, project_id=project.id))
        db.commit()

        job = create_detection_job(
            db,
            user=user,
            project_id=project.id,
            model=model,
            kind=DetectionKind.IMAGE,
            parameters={"confidence": 0.35},
        )
        claimed = claim_next_job(db, "worker-1", 120)
        assert claimed is not None
        assert claimed.id == job.id
        assert claimed.status == JobStatus.RUNNING

        request_job_cancel(db, user=user, job=claimed)
        assert claimed.status == JobStatus.CANCELLING
        claimed.status = JobStatus.CANCELLED
        db.commit()
        retry = retry_detection_job(db, user=user, job=claimed)
        assert retry.retry_of_id == claimed.id
        assert retry.attempt == 2
        assert retry.status == JobStatus.QUEUED

        retry.status = JobStatus.RUNNING
        retry.attempt = retry.max_attempts
        retry.lease_expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
        assert claim_next_job(db, "worker-2", 120) is None
        db.refresh(retry)
        assert retry.status == JobStatus.FAILED
        assert retry.error_code == "detection.max_attempts_exceeded"
