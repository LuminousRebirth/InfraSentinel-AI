from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import cv2
from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import InfraError
from .lifecycle_models import DatasetSample, DatasetVersion
from .lifecycle_service import assign_version_splits, require_draft
from .storage import safe_path


def extract_video_frames(
    db: Session,
    *,
    version: DatasetVersion,
    storage_root: Path,
    interval_seconds: float = 1.0,
    max_frames: int = 1000,
    actor_id: uuid.UUID,
) -> list[DatasetSample]:
    require_draft(version)
    interval_seconds = max(0.1, min(interval_seconds, 60.0))
    max_frames = max(1, min(max_frames, 10_000))
    videos = db.scalars(
        select(DatasetSample).where(
            DatasetSample.version_id == version.id,
            DatasetSample.media_type == "video",
        )
    ).all()
    created: list[DatasetSample] = []
    written: list[Path] = []
    try:
        for video in videos:
            source = safe_path(storage_root, *Path(video.storage_key).parts)
            capture = cv2.VideoCapture(str(source))
            try:
                if not capture.isOpened():
                    raise InfraError(422, "lifecycle.invalid_video")
                fps = float(capture.get(cv2.CAP_PROP_FPS))
                if fps <= 0:
                    raise InfraError(422, "lifecycle.invalid_video")
                stride = max(1, round(fps * interval_seconds))
                frame_index = 0
                while len(created) < max_frames:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    if frame_index % stride == 0:
                        encoded, body = cv2.imencode(".jpg", frame)
                        if not encoded:
                            raise InfraError(422, "lifecycle.invalid_video")
                        raw = body.tobytes()
                        digest = hashlib.sha256(raw).hexdigest()
                        storage_key = (
                            f"datasets/{version.dataset_id}/v{version.version_number}/frames/"
                            f"{video.id.hex}-{frame_index:010d}.jpg"
                        )
                        output = safe_path(storage_root, *Path(storage_key).parts)
                        output.parent.mkdir(parents=True, exist_ok=True)
                        output.write_bytes(raw)
                        written.append(output)
                        height, width = frame.shape[:2]
                        sample = DatasetSample(
                            version_id=version.id,
                            storage_key=storage_key,
                            original_name=f"{Path(video.original_name).stem}-{frame_index:010d}.jpg",
                            media_type="image",
                            mime_type="image/jpeg",
                            byte_size=len(raw),
                            sha256=digest,
                            width=width,
                            height=height,
                            source_video_id=video.id,
                            frame_index=frame_index,
                            timestamp_ms=round(frame_index / fps * 1000),
                            created_by=actor_id,
                        )
                        db.add(sample)
                        created.append(sample)
                    frame_index += 1
            finally:
                capture.release()
        version.sample_count += len(created)
        version.byte_size += sum(item.byte_size for item in created)
        version.revision += 1
        db.flush()
        assign_version_splits(db, version)
        db.commit()
        return created
    except Exception:
        db.rollback()
        for path in written:
            path.unlink(missing_ok=True)
        raise
