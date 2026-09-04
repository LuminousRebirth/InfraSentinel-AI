from __future__ import annotations

import hashlib
import io
import zipfile
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
from infrasentinel.main import app
from infrasentinel.models import AuthSession, Project, User, UserRole, UserStatus

ORIGIN = {"Origin": "http://127.0.0.1:8090"}


def yolo_archive() -> bytes:
    ok, image = cv2.imencode(".jpg", np.zeros((20, 30, 3), dtype=np.uint8))
    assert ok
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("images/train/sample.jpg", image.tobytes())
        archive.writestr("labels/train/sample.txt", "0 0.5 0.5 0.4 0.4\n")
    return output.getvalue()


def test_dataset_create_import_annotate_and_quality(tmp_path: Path) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db = Session(engine)
    Base.metadata.create_all(engine)
    admin = User(
        email="lifecycle-admin@example.com",
        username="lifecycle-admin",
        display_name="Lifecycle Admin",
        password_hash="hash",
        role=UserRole.ADMIN,
        status=UserStatus.ENABLED,
    )
    project = Project(code="LIFECYCLE", name="Lifecycle")
    db.add_all([admin, project])
    db.commit()
    auth_session = AuthSession(
        user_id=admin.id,
        token_hash="f" * 64,
        expires_at=admin.created_at,
    )

    def override_db():
        yield db

    app.dependency_overrides[get_session] = override_db
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(admin, auth_session)
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        storage_root=tmp_path,
    )
    try:
        client = TestClient(app)
        created = client.post(
            "/api/v1/admin/datasets",
            json={"project_id": str(project.id), "name": "Inspection set"},
            headers=ORIGIN,
        )
        assert created.status_code == 201, created.text
        dataset = created.json()
        version_id = dataset["versions"][0]["id"]

        imported = client.post(
            f"/api/v1/admin/dataset-versions/{version_id}/import",
            files={"archive": ("dataset.zip", yolo_archive(), "application/zip")},
            headers=ORIGIN,
        )
        assert imported.status_code == 200, imported.text
        assert imported.json()["imported_samples"] == 1
        assert imported.json()["imported_annotations"] == 1

        samples = client.get(f"/api/v1/dataset-versions/{version_id}/samples")
        assert samples.status_code == 200
        sample = samples.json()[0]
        assert len(sample["annotations"]) == 1
        assert client.get(f"/api/v1/dataset-samples/{sample['id']}/content").status_code == 200

        categories = client.get("/api/v1/dataset-categories").json()
        updated = client.put(
            f"/api/v1/dataset-samples/{sample['id']}/annotations",
            json={
                "expected_revision": sample["revision"],
                "annotations": [
                    {
                        "category_id": categories[1]["id"],
                        "cx": 0.5,
                        "cy": 0.5,
                        "width": 0.2,
                        "height": 0.2,
                    }
                ],
            },
            headers=ORIGIN,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["revision"] == sample["revision"] + 1

        quality = client.post(
            f"/api/v1/admin/dataset-versions/{version_id}/quality", headers=ORIGIN
        )
        assert quality.status_code == 200
        assert quality.json() == []
        frozen = client.post(f"/api/v1/admin/dataset-versions/{version_id}/freeze", headers=ORIGIN)
        assert frozen.status_code == 200, frozen.text
        assert frozen.json()["status"] == "frozen"
        trusted = tmp_path / "models" / "trusted.pt"
        trusted.parent.mkdir(parents=True)
        trusted.write_bytes(b"trusted-local-weight")
        imported_model = client.post(
            "/api/v1/admin/managed-models/import",
            json={
                "version_id": version_id,
                "code": "trusted-api-model",
                "scene": "pipeline",
                "size_variant": "n",
                "storage_key": "models/trusted.pt",
                "sha256": hashlib.sha256(trusted.read_bytes()).hexdigest(),
                "model_card": "Trusted local acceptance asset",
                "class_map": ["CK", "PL", "SG", "SL", "TL", "ZW"],
            },
            headers=ORIGIN,
        )
        assert imported_model.status_code == 201, imported_model.text
        assert imported_model.json()["status"] == "draft"
        escaped_model = client.post(
            "/api/v1/admin/managed-models/import",
            json={
                "version_id": version_id,
                "code": "escaped-model",
                "scene": "pipeline",
                "storage_key": "../outside.pt",
                "sha256": "0" * 64,
                "model_card": "Must be rejected",
                "class_map": ["CK"],
            },
            headers=ORIGIN,
        )
        assert escaped_model.status_code == 422
        queued = client.post(
            "/api/v1/admin/lifecycle-jobs",
            json={
                "version_id": version_id,
                "kind": "train",
                "config": {"code": "api-model", "epochs": 2},
            },
            headers=ORIGIN,
        )
        assert queued.status_code == 201, queued.text
        assert queued.json()["status"] == "queued"
        assert client.get("/api/v1/lifecycle-jobs").json()[0]["id"] == queued.json()["id"]

        second = client.post(
            f"/api/v1/admin/datasets/{dataset['id']}/versions",
            json={"source": "direct", "train_ratio": 80, "val_ratio": 10, "test_ratio": 10},
            headers=ORIGIN,
        )
        assert second.status_code == 201
        ok, image = cv2.imencode(".png", np.zeros((12, 18, 3), dtype=np.uint8))
        assert ok
        direct = client.post(
            f"/api/v1/admin/dataset-versions/{second.json()['id']}/media",
            files={"files": ("direct.png", image.tobytes(), "image/png")},
            headers=ORIGIN,
        )
        assert direct.status_code == 200, direct.text
        assert direct.json()["imported_samples"] == 1
        direct_quality = client.post(
            f"/api/v1/admin/dataset-versions/{second.json()['id']}/quality",
            headers=ORIGIN,
        )
        assert direct_quality.status_code == 200
        finding_id = direct_quality.json()[0]["id"]
        resolved = client.post(
            f"/api/v1/admin/quality-findings/{finding_id}/resolve",
            headers=ORIGIN,
        )
        assert resolved.status_code == 200
        assert resolved.json()["resolved"] is True
        archived = client.post(
            f"/api/v1/admin/dataset-versions/{second.json()['id']}/archive",
            headers=ORIGIN,
        )
        assert archived.status_code == 200
        assert archived.json()["status"] == "archived"
    finally:
        app.dependency_overrides.clear()
        db.close()
