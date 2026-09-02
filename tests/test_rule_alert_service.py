from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from infrasentinel.database import Base
from infrasentinel.detection_models import (
    DetectionJob,
    DetectionKind,
    DetectionObservation,
    JobStatus,
    ModelAvailability,
    VisionModel,
    VisionScene,
)
from infrasentinel.intelligence_models import Alert, AlertAction, DetectionEvent, RiskLevel
from infrasentinel.intelligence_service import refresh_job_intelligence, seed_default_rules
from infrasentinel.models import Project, ProjectMembership, User, UserRole, UserStatus


def test_default_rules_and_refresh_are_idempotent() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first = seed_default_rules(db)
        second = seed_default_rules(db)
        assert len(first) == len(second) == 7

        user = User(
            email="alerts@example.com",
            username="alerts",
            display_name="Alerts",
            password_hash="hash",
            role=UserRole.USER,
            status=UserStatus.ENABLED,
        )
        project = Project(code="ALERT", name="Alert Plant")
        model = VisionModel(
            code="alerts-model",
            name_zh="模型",
            name_en="Model",
            scene=VisionScene.PIPELINE,
            classes_json=["CK"],
            input_size=640,
            availability=ModelAvailability.AVAILABLE,
        )
        db.add_all([user, project, model])
        db.flush()
        db.add(ProjectMembership(user_id=user.id, project_id=project.id))
        job = DetectionJob(
            kind=DetectionKind.VIDEO,
            status=JobStatus.SUCCEEDED,
            project_id=project.id,
            point_id=project.id,
            owner_id=user.id,
            model_id=model.id,
            scene=model.scene,
            parameters_json={},
        )
        db.add(job)
        db.flush()
        for timestamp, x in ((0, 0), (1000, 1), (5000, 1)):
            db.add(
                DetectionObservation(
                    job_id=job.id,
                    frame_index=timestamp // 100,
                    timestamp_ms=timestamp,
                    class_name="CK",
                    confidence=0.8,
                    x1=x,
                    y1=0,
                    x2=x + 10,
                    y2=10,
                    inference_ms=5,
                )
            )
        db.commit()

        alerts = refresh_job_intelligence(db, job)
        assert len(alerts) == 2
        assert all(alert.final_level == RiskLevel.MEDIUM for alert in alerts)
        assert db.scalar(select(func.count()).select_from(DetectionEvent)) == 2
        assert db.scalar(select(func.count()).select_from(AlertAction)) == 2

        refresh_job_intelligence(db, job)
        assert db.scalar(select(func.count()).select_from(Alert)) == 2
        assert db.scalar(select(func.count()).select_from(AlertAction)) == 2
