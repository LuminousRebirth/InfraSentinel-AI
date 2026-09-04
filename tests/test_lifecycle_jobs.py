from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from infrasentinel.database import Base
from infrasentinel.lifecycle_jobs import (
    claim_next_lifecycle_job,
    complete_lifecycle_job,
    create_fake_training_result,
    create_lifecycle_job,
    deploy_model,
    publish_model,
    rollback_deployment,
)
from infrasentinel.lifecycle_models import (
    LifecycleJobKind,
    LifecycleJobStatus,
    VersionStatus,
)
from infrasentinel.lifecycle_service import create_dataset
from infrasentinel.models import Project, User, UserRole, UserStatus


def test_fake_training_publish_deploy_and_rollback(tmp_path) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        admin = User(
            email="trainer@example.com",
            username="trainer-admin",
            display_name="Trainer",
            password_hash="hash",
            role=UserRole.ADMIN,
            status=UserStatus.ENABLED,
        )
        project = Project(code="TRAIN", name="Training")
        db.add_all([admin, project])
        db.commit()
        _, version = create_dataset(db, user=admin, project_id=project.id, name="Train")
        version.status = VersionStatus.FROZEN
        db.commit()

        job = create_lifecycle_job(
            db,
            user=admin,
            version=version,
            kind=LifecycleJobKind.TRAIN,
            config={"code": "pipeline-custom", "epochs": 3},
        )
        claimed = claim_next_lifecycle_job(db, "trainer-1")
        assert claimed and claimed.id == job.id
        assert claimed.status == LifecycleJobStatus.RUNNING
        model_v1 = create_fake_training_result(db, job=claimed, storage_root=tmp_path)
        complete_lifecycle_job(db, claimed, {"model_version_id": str(model_v1.id)})
        evaluation = create_lifecycle_job(
            db,
            user=admin,
            version=version,
            kind=LifecycleJobKind.EVALUATE,
            config={"model_version_id": str(model_v1.id)},
        )
        evaluation = claim_next_lifecycle_job(db, "trainer-1")
        complete_lifecycle_job(db, evaluation, model_v1.metrics_json)
        assert (
            publish_model(db, user=admin, model=model_v1, storage_root=tmp_path).published_at
            is not None
        )

        deployment = deploy_model(
            db, user=admin, project_id=project.id, model=model_v1, rollout_percent=50
        )
        assert deployment.model_version_id == model_v1.id

        version.status = VersionStatus.FROZEN
        db.commit()
        second_job = create_lifecycle_job(
            db,
            user=admin,
            version=version,
            kind=LifecycleJobKind.TRAIN,
            config={"code": "pipeline-custom", "epochs": 1},
        )
        claimed = claim_next_lifecycle_job(db, "trainer-1")
        model_v2 = create_fake_training_result(db, job=claimed, storage_root=tmp_path)
        complete_lifecycle_job(db, second_job)
        evaluation = create_lifecycle_job(
            db,
            user=admin,
            version=version,
            kind=LifecycleJobKind.EVALUATE,
            config={"model_version_id": str(model_v2.id)},
        )
        evaluation = claim_next_lifecycle_job(db, "trainer-1")
        complete_lifecycle_job(db, evaluation, model_v2.metrics_json)
        publish_model(db, user=admin, model=model_v2, storage_root=tmp_path)
        deploy_model(db, user=admin, project_id=project.id, model=model_v2)
        assert deployment.model_version_id == model_v2.id
        rollback_deployment(db, user=admin, deployment=deployment)
        assert deployment.model_version_id == model_v1.id
