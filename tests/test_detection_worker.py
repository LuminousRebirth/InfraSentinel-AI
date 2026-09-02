from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from infrasentinel.config import Settings
from infrasentinel.database import Base
from infrasentinel.detection_models import (
    DetectionKind,
    DetectionMedia,
    JobStatus,
    MediaRole,
    MediaType,
    ModelAvailability,
    VisionModel,
    VisionScene,
)
from infrasentinel.detection_service import claim_next_job, create_detection_job
from infrasentinel.models import Project, ProjectMembership, User, UserRole, UserStatus
from infrasentinel.worker import VisionWorker, class_counts, ffmpeg_executable
from vision_inspection.infer import RuntimePrediction


class FakeRuntime:
    backend = "fake"

    def predict(self, image, **kwargs) -> RuntimePrediction:
        del kwargs
        return RuntimePrediction(
            scene="pipeline",
            detections=[{"cls": "CK", "conf": 0.9, "box": [1, 2, 12, 14]}],
            annotated_image=image.copy(),
            inference_ms=5.0,
            backend="fake",
        )


class FakeCapture:
    def __init__(self) -> None:
        self.released = False
        self.settings: list[tuple[int, int]] = []

    def isOpened(self) -> bool:
        return True

    def read(self):
        return True, np.zeros((20, 20, 3), dtype=np.uint8)

    def release(self) -> None:
        self.released = True

    def set(self, prop: int, value: int) -> bool:
        self.settings.append((prop, value))
        return True


class FakeRedis:
    def __init__(self) -> None:
        self.frames: list[bytes] = []
        self.deleted: list[str] = []
        self.closed = False

    def setex(self, _key: str, _ttl: int, value: bytes) -> None:
        self.frames.append(value)

    def delete(self, key: str) -> None:
        self.deleted.append(key)

    def close(self) -> None:
        self.closed = True


def test_worker_helpers_are_deterministic() -> None:
    assert class_counts([{"cls": "CK"}, {"cls": "CK"}, {"cls": "SG"}]) == {
        "CK": 2,
        "SG": 1,
    }
    assert ffmpeg_executable().lower().endswith("ffmpeg.exe")


def test_image_worker_persists_output_and_observation(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
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
            parameters={},
        )
        original_path = tmp_path / "originals" / "image.jpg"
        original_path.parent.mkdir(parents=True)
        assert cv2.imwrite(str(original_path), np.zeros((20, 20, 3), dtype=np.uint8))
        db.add(
            DetectionMedia(
                job_id=job.id,
                role=MediaRole.ORIGINAL,
                media_type=MediaType.IMAGE,
                storage_key="originals/image.jpg",
                original_name="image.jpg",
                mime_type="image/jpeg",
                byte_size=original_path.stat().st_size,
                sha256="0" * 64,
                width=20,
                height=20,
            )
        )
        db.commit()
        claimed = claim_next_job(db, "test-worker", 120)
        assert claimed is not None
        worker = VisionWorker(Settings(_env_file=None, storage_root=tmp_path), "test-worker")
        worker.process_job(db, claimed, FakeRuntime())
        db.refresh(claimed)
        assert claimed.status == JobStatus.SUCCEEDED
        assert claimed.result_json["class_counts"] == {"CK": 1}
        assert db.scalar(
            select(DetectionMedia).where(
                DetectionMedia.job_id == job.id,
                DetectionMedia.role == MediaRole.ANNOTATED,
            )
        )

        failed = create_detection_job(
            db,
            user=user,
            project_id=project.id,
            model=model,
            kind=DetectionKind.IMAGE,
            parameters={},
        )
        claimed_failed = claim_next_job(db, "test-worker", 120)
        assert claimed_failed is not None

        def fail_runtime(_model):
            raise RuntimeError("model load failed")

        monkeypatch.setattr(worker, "runtime_for", fail_runtime)
        worker.process_job(db, claimed_failed)
        db.refresh(failed)
        assert failed.status == JobStatus.FAILED
        assert failed.error_code == "detection.processing_failed"


def test_obs_worker_publishes_preview_and_releases_resources(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(
            email="obs@example.com",
            username="obs",
            display_name="OBS",
            password_hash="hash",
            role=UserRole.USER,
            status=UserStatus.ENABLED,
        )
        project = Project(code="OBS", name="OBS Project")
        model = VisionModel(
            code="pipeline-obs",
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
            kind=DetectionKind.OBS,
            parameters={"detection_fps": 1_000_000_000},
        )
        claimed = claim_next_job(db, "obs-worker", 120)
        assert claimed is not None

        checks = iter([False] * 15 + [True])
        monkeypatch.setattr(
            "infrasentinel.worker.cancellation_requested", lambda *_args: next(checks)
        )
        capture = FakeCapture()
        redis = FakeRedis()
        worker = VisionWorker(Settings(_env_file=None, storage_root=tmp_path), "obs-worker")
        worker.process_obs(db, claimed, FakeRuntime(), capture=capture, redis=redis)

        db.refresh(claimed)
        assert claimed.status == JobStatus.CANCELLED
        assert len(redis.frames) == 15
        assert capture.released
        assert capture.settings == [
            (cv2.CAP_PROP_FRAME_WIDTH, 1280),
            (cv2.CAP_PROP_FRAME_HEIGHT, 720),
        ]
        assert redis.closed
        assert redis.deleted == [f"infrasentinel:obs:{job.id}:preview"]
        assert db.scalar(
            select(DetectionMedia).where(
                DetectionMedia.job_id == job.id,
                DetectionMedia.role == MediaRole.KEYFRAME,
            )
        )
