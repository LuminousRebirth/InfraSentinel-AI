from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import cv2
import numpy as np
import pytest

from infrasentinel.detection_media import (
    MediaValidationError,
    resolve_storage_key,
    safe_display_name,
    save_upload,
)


class FakeUpload:
    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self.content = content
        self.position = 0

    async def read(self, size: int) -> bytes:
        chunk = self.content[self.position : self.position + size]
        self.position += len(chunk)
        return chunk


def test_image_upload_is_hashed_probed_and_finalized(tmp_path: Path) -> None:
    image = np.zeros((24, 32, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    saved = asyncio.run(
        save_upload(
            FakeUpload("../sample.png", encoded.tobytes()),
            root=tmp_path,
            job_id=uuid.uuid4(),
            media_type="image",
            max_bytes=1024 * 1024,
            critical_free_gb=0,
        )
    )
    assert saved.original_name == "sample.png"
    assert (saved.width, saved.height) == (32, 24)
    assert saved.storage_key.startswith("originals/")
    assert resolve_storage_key(tmp_path, saved.storage_key).is_file()


def test_invalid_and_oversized_uploads_leave_no_staging_file(tmp_path: Path) -> None:
    job_id = uuid.uuid4()
    with pytest.raises(MediaValidationError, match="invalid_image"):
        asyncio.run(
            save_upload(
                FakeUpload("broken.jpg", b"not-an-image"),
                root=tmp_path,
                job_id=job_id,
                media_type="image",
                max_bytes=100,
                critical_free_gb=0,
            )
        )
    with pytest.raises(MediaValidationError, match="image_too_large"):
        asyncio.run(
            save_upload(
                FakeUpload("large.jpg", b"x" * 101),
                root=tmp_path,
                job_id=job_id,
                media_type="image",
                max_bytes=100,
                critical_free_gb=0,
            )
        )
    assert not list((tmp_path / "staging").rglob("*.*"))


def test_display_name_and_storage_resolution_are_safe(tmp_path: Path) -> None:
    assert safe_display_name("..\\secret\x00.jpg") == "secret.jpg"
    with pytest.raises(ValueError, match="escapes"):
        resolve_storage_key(tmp_path, "../outside.jpg")
