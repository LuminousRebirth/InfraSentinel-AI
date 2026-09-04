from __future__ import annotations

import hashlib

import cv2
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from infrasentinel.database import Base
from infrasentinel.lifecycle_media import extract_video_frames
from infrasentinel.lifecycle_models import DatasetSample
from infrasentinel.lifecycle_service import create_dataset
from infrasentinel.models import Project, User, UserRole, UserStatus


def test_video_frame_extraction_is_bounded_and_persisted(tmp_path) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        admin = User(
            email="frames@example.com",
            username="frames-admin",
            display_name="Frames",
            password_hash="hash",
            role=UserRole.ADMIN,
            status=UserStatus.ENABLED,
        )
        project = Project(code="FRAMES", name="Frames")
        db.add_all([admin, project])
        db.commit()
        _, version = create_dataset(db, user=admin, project_id=project.id, name="Video")
        source = tmp_path / "originals" / "sample.avi"
        source.parent.mkdir(parents=True)
        writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 5, (24, 16))
        assert writer.isOpened()
        for index in range(10):
            writer.write(np.full((16, 24, 3), index * 10, dtype=np.uint8))
        writer.release()
        raw = source.read_bytes()
        video = DatasetSample(
            version_id=version.id,
            storage_key="originals/sample.avi",
            original_name="sample.avi",
            media_type="video",
            mime_type="video/x-msvideo",
            byte_size=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            width=24,
            height=16,
            created_by=admin.id,
        )
        db.add(video)
        version.sample_count = 1
        version.byte_size = len(raw)
        db.commit()

        frames = extract_video_frames(
            db,
            version=version,
            storage_root=tmp_path,
            interval_seconds=1,
            max_frames=2,
            actor_id=admin.id,
        )
        assert len(frames) == 2
        assert all(frame.source_video_id == video.id for frame in frames)
        assert all((tmp_path / frame.storage_key).is_file() for frame in frames)
        assert version.sample_count == 3
