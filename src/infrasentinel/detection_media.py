from __future__ import annotations

import hashlib
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import cv2

from .storage import safe_path

IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
VIDEO_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
}
CHUNK_SIZE = 1024 * 1024


class MediaValidationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SavedUpload:
    storage_key: str
    original_name: str
    mime_type: str
    byte_size: int
    sha256: str
    width: int
    height: int
    duration_seconds: float | None = None
    fps: float | None = None
    frame_count: int | None = None


def safe_display_name(name: str | None) -> str:
    normalized = (name or "upload").replace("\\", "/").split("/")[-1]
    normalized = re.sub(r"[\x00-\x1f\x7f]", "", normalized).strip()
    return (normalized or "upload")[:255]


def resolve_storage_key(root: Path, storage_key: str) -> Path:
    return safe_path(root, *Path(storage_key).parts)


def _probe_image(path: Path) -> tuple[int, int]:
    image = cv2.imread(str(path))
    if image is None:
        raise MediaValidationError("detection.invalid_image")
    height, width = image.shape[:2]
    return width, height


def _probe_video(path: Path, max_seconds: int) -> tuple[int, int, float, float, int]:
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise MediaValidationError("detection.invalid_video")
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if width <= 0 or height <= 0 or fps <= 0 or frame_count <= 0:
            raise MediaValidationError("detection.invalid_video")
        duration = frame_count / fps
        if duration > max_seconds:
            raise MediaValidationError("detection.video_too_long")
        return width, height, round(duration, 3), round(fps, 3), frame_count
    finally:
        capture.release()


async def save_upload(
    upload,
    *,
    root: Path,
    job_id: uuid.UUID,
    media_type: str,
    max_bytes: int,
    max_video_seconds: int = 7200,
    critical_free_gb: int = 2,
) -> SavedUpload:
    root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < critical_free_gb * 1024**3:
        raise MediaValidationError("detection.storage_full")

    original_name = safe_display_name(getattr(upload, "filename", None))
    suffix = Path(original_name).suffix.lower()
    allowed = IMAGE_TYPES if media_type == "image" else VIDEO_TYPES
    if suffix not in allowed:
        raise MediaValidationError(f"detection.unsupported_{media_type}")

    token = uuid.uuid4().hex
    staging_key = f"staging/{job_id}/{token}{suffix}"
    staging_path = resolve_storage_key(root, staging_key)
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    try:
        with staging_path.open("xb") as output:
            while chunk := await upload.read(CHUNK_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    raise MediaValidationError(f"detection.{media_type}_too_large")
                digest.update(chunk)
                output.write(chunk)
        if size == 0:
            raise MediaValidationError(f"detection.invalid_{media_type}")

        if media_type == "image":
            width, height = _probe_image(staging_path)
            duration = fps = None
            frame_count = None
        else:
            width, height, duration, fps, frame_count = _probe_video(
                staging_path, max_video_seconds
            )

        now = datetime.now(UTC)
        storage_key = f"originals/{now:%Y/%m}/{job_id}/{token}{suffix}"
        final_path = resolve_storage_key(root, storage_key)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging_path, final_path)
        return SavedUpload(
            storage_key=storage_key,
            original_name=original_name,
            mime_type=allowed[suffix],
            byte_size=size,
            sha256=digest.hexdigest(),
            width=width,
            height=height,
            duration_seconds=duration,
            fps=fps,
            frame_count=frame_count,
        )
    except Exception:
        staging_path.unlink(missing_ok=True)
        raise
