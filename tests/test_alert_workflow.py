from sqlalchemy import create_engine, delete, func, select
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
from infrasentinel.errors import InfraError
from infrasentinel.intelligence_models import AlertAction, AlertStatus
from infrasentinel.intelligence_service import (
    refresh_job_intelligence,
    require_alert_access,
    seed_default_rules,
    update_alert_workflow,
)
from infrasentinel.models import Project, ProjectMembership, User, UserRole, UserStatus


def test_alert_workflow_is_versioned_audited_and_project_scoped() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        admin = User(
            email="admin-workflow@example.com",
            username="admin-workflow",
            display_name="Admin",
            password_hash="hash",
            role=UserRole.ADMIN,
            status=UserStatus.ENABLED,
        )
        owner = User(
            email="owner-workflow@example.com",
            username="owner-workflow",
            display_name="Owner",
            password_hash="hash",
            role=UserRole.USER,
            status=UserStatus.ENABLED,
        )
        project = Project(code="FLOW", name="Workflow")
        model = VisionModel(
            code="flow-model",
            name_zh="模型",
            name_en="Model",
            scene=VisionScene.PIPELINE,
            classes_json=["CK"],
            input_size=640,
            availability=ModelAvailability.AVAILABLE,
        )
        db.add_all([admin, owner, project, model])
        db.flush()
        db.add(ProjectMembership(user_id=owner.id, project_id=project.id))
        job = DetectionJob(
            kind=DetectionKind.IMAGE,
            status=JobStatus.SUCCEEDED,
            project_id=project.id,
            point_id=project.id,
            owner_id=owner.id,
            model_id=model.id,
            scene=model.scene,
            parameters_json={},
        )
        db.add(job)
        db.flush()
        db.add(
            DetectionObservation(
                job_id=job.id,
                frame_index=0,
                timestamp_ms=0,
                class_name="CK",
                confidence=0.8,
                x1=0,
                y1=0,
                x2=10,
                y2=10,
                inference_ms=5,
            )
        )
        db.commit()
        seed_default_rules(db)
        alert = refresh_job_intelligence(db, job)[0]

        update_alert_workflow(
            db,
            actor=admin,
            alert=alert,
            expected_version=1,
            status=AlertStatus.ASSIGNED,
            assignee_id=owner.id,
        )
        update_alert_workflow(
            db,
            actor=owner,
            alert=alert,
            expected_version=2,
            status=AlertStatus.PROCESSING,
        )
        update_alert_workflow(
            db,
            actor=owner,
            alert=alert,
            expected_version=3,
            status=AlertStatus.RESOLVED,
            note="Field repair confirmed",
        )
        assert alert.status == AlertStatus.RESOLVED
        assert alert.version == 4
        assert db.scalar(select(func.count()).select_from(AlertAction)) == 4

        try:
            update_alert_workflow(
                db,
                actor=admin,
                alert=alert,
                expected_version=3,
                status=AlertStatus.FALSE_POSITIVE,
                note="stale",
            )
        except InfraError as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("stale workflow update was accepted")

        db.execute(
            delete(ProjectMembership).where(
                ProjectMembership.user_id == owner.id,
                ProjectMembership.project_id == project.id,
            )
        )
        db.commit()
        try:
            require_alert_access(db, owner, alert.id)
        except InfraError as exc:
            assert exc.status_code == 403
        else:
            raise AssertionError("removed project member retained alert access")
