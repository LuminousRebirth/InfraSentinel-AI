from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from infrasentinel.config import Settings, get_settings
from infrasentinel.database import Base, get_session
from infrasentinel.dependencies import AuthContext, get_auth_context
from infrasentinel.detection_models import (
    DetectionJob,
    DetectionKind,
    DetectionObservation,
    JobStatus,
    ModelAvailability,
    VisionModel,
    VisionScene,
)
from infrasentinel.intelligence_service import refresh_job_intelligence, seed_default_rules
from infrasentinel.main import app
from infrasentinel.models import AuthSession, Project, ProjectMembership, User, UserRole, UserStatus

ORIGIN = {"Origin": "http://127.0.0.1:8090"}


def test_alert_scope_and_safe_attachment(tmp_path: Path) -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    owner = User(
        email="alert-api@example.com",
        username="alert-api",
        display_name="Owner",
        password_hash="hash",
        role=UserRole.USER,
        status=UserStatus.ENABLED,
    )
    other = User(
        email="alert-other@example.com",
        username="alert-other",
        display_name="Other",
        password_hash="hash",
        role=UserRole.USER,
        status=UserStatus.ENABLED,
    )
    admin = User(
        email="alert-admin@example.com",
        username="alert-admin",
        display_name="Admin",
        password_hash="hash",
        role=UserRole.ADMIN,
        status=UserStatus.ENABLED,
    )
    project = Project(code="ALERT-API", name="Alert API")
    model = VisionModel(
        code="alert-api-model",
        name_zh="模型",
        name_en="Model",
        scene=VisionScene.PIPELINE,
        classes_json=["CK"],
        input_size=640,
        availability=ModelAvailability.AVAILABLE,
    )
    db.add_all([owner, other, admin, project, model])
    db.flush()
    db.add_all(
        [
            ProjectMembership(user_id=owner.id, project_id=project.id),
            ProjectMembership(user_id=other.id, project_id=project.id),
        ]
    )
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
    auth_session = AuthSession(user_id=owner.id, token_hash="1" * 64, expires_at=owner.created_at)

    def override_db():
        yield db

    app.dependency_overrides[get_session] = override_db
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(owner, auth_session)
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, storage_root=tmp_path, infrasentinel_storage_critical_gb=1
    )
    try:
        client = TestClient(app)
        assert len(client.get("/api/v1/alerts").json()) == 1
        rejected = client.post(
            f"/api/v1/alerts/{alert.id}/attachments",
            files={"upload": ("bad.png", b"not-image", "image/png")},
            headers=ORIGIN,
        )
        assert rejected.status_code == 422

        image = np.zeros((10, 10, 3), dtype=np.uint8)
        ok, encoded = cv2.imencode(".png", image)
        assert ok
        uploaded = client.post(
            f"/api/v1/alerts/{alert.id}/attachments",
            files={"upload": ("evidence.png", encoded.tobytes(), "image/png")},
            headers=ORIGIN,
        )
        assert uploaded.status_code == 201
        attachment_id = uploaded.json()["id"]

        app.dependency_overrides[get_auth_context] = lambda: AuthContext(other, auth_session)
        assert client.get(f"/api/v1/alerts/attachments/{attachment_id}").status_code == 403
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(admin, auth_session)
        assert client.get(f"/api/v1/alerts/attachments/{attachment_id}").status_code == 200

        db.execute(delete(ProjectMembership).where(ProjectMembership.user_id == owner.id))
        db.commit()
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(owner, auth_session)
        assert client.get("/api/v1/alerts").json() == []
        assert client.get(f"/api/v1/alerts/{alert.id}").status_code == 403
    finally:
        app.dependency_overrides.clear()
        db.close()
