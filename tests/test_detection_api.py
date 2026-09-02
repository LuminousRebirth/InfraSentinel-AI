from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from infrasentinel.config import Settings, get_settings
from infrasentinel.database import Base, get_session
from infrasentinel.dependencies import AuthContext, get_auth_context
from infrasentinel.detection_models import ModelAvailability, VisionModel, VisionScene
from infrasentinel.main import app
from infrasentinel.models import AuthSession, Project, ProjectMembership, User, UserRole, UserStatus

ORIGIN = {"Origin": "http://127.0.0.1:8090"}


def test_detection_upload_list_and_single_obs(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    user = User(
        email="api@example.com",
        username="api-user",
        display_name="API User",
        password_hash="hash",
        role=UserRole.USER,
        status=UserStatus.ENABLED,
    )
    other = User(
        email="other@example.com",
        username="other-user",
        display_name="Other User",
        password_hash="hash",
        role=UserRole.USER,
        status=UserStatus.ENABLED,
    )
    admin = User(
        email="vision-admin@example.com",
        username="vision-admin",
        display_name="Vision Admin",
        password_hash="hash",
        role=UserRole.ADMIN,
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
    db.add_all([user, other, admin, project, model])
    db.flush()
    db.add_all(
        [
            ProjectMembership(user_id=user.id, project_id=project.id),
            ProjectMembership(user_id=other.id, project_id=project.id),
        ]
    )
    db.commit()
    auth_session = AuthSession(
        user_id=user.id,
        token_hash="0" * 64,
        expires_at=user.created_at,
    )

    def override_db():
        yield db

    app.dependency_overrides[get_session] = override_db
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(user, auth_session)
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        storage_root=tmp_path,
        infrasentinel_storage_critical_gb=1,
    )
    monkeypatch.setattr(
        "infrasentinel.detection_api.enforce_rate_limit", lambda *_args, **_kwargs: None
    )
    try:
        client = TestClient(app)
        listed = client.get("/api/v1/vision/models")
        assert listed.status_code == 200
        assert "pt_path" not in listed.text

        image = np.zeros((20, 30, 3), dtype=np.uint8)
        ok, encoded = cv2.imencode(".png", image)
        assert ok
        uploaded = client.post(
            "/api/v1/detections/images",
            data={
                "project_id": str(project.id),
                "model_id": str(model.id),
                "parameters": json.dumps({"confidence": 0.4}),
            },
            files={"files": ("sample.png", encoded.tobytes(), "image/png")},
            headers=ORIGIN,
        )
        assert uploaded.status_code == 201
        job_id = uploaded.json()[0]["job_id"]
        assert job_id
        assert client.get("/api/v1/detections/jobs").status_code == 200
        detail = client.get(f"/api/v1/detections/jobs/{job_id}")
        assert detail.status_code == 200
        media_id = detail.json()["media"][0]["id"]

        app.dependency_overrides[get_auth_context] = lambda: AuthContext(other, auth_session)
        assert client.get(f"/api/v1/detections/jobs/{job_id}").status_code == 403
        assert client.get(f"/api/v1/detections/media/{media_id}").status_code == 403

        app.dependency_overrides[get_auth_context] = lambda: AuthContext(admin, auth_session)
        assert client.get(f"/api/v1/detections/jobs/{job_id}").status_code == 200
        assert client.get(f"/api/v1/detections/media/{media_id}").status_code == 200

        app.dependency_overrides[get_auth_context] = lambda: AuthContext(user, auth_session)

        obs = client.post(
            "/api/v1/detections/obs",
            json={"project_id": str(project.id), "model_id": str(model.id)},
            headers=ORIGIN,
        )
        assert obs.status_code == 201
        duplicate = client.post(
            "/api/v1/detections/obs",
            json={"project_id": str(project.id), "model_id": str(model.id)},
            headers=ORIGIN,
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "detection.obs_busy"
    finally:
        app.dependency_overrides.clear()
        db.close()
