from __future__ import annotations

import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from infrasentinel.dataset_import import (
    DatasetImportError,
    extract_yolo_archive,
    parse_yolo_label,
    validate_archive,
)


def write_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in files.items():
            archive.writestr(name, body)


def jpeg_bytes() -> bytes:
    success, encoded = cv2.imencode(".jpg", np.zeros((16, 24, 3), dtype=np.uint8))
    assert success
    return encoded.tobytes()


def test_yolo_archive_extracts_image_and_paired_label(tmp_path: Path) -> None:
    archive = tmp_path / "dataset.zip"
    write_zip(
        archive,
        {
            "images/train/sample.jpg": jpeg_bytes(),
            "labels/train/sample.txt": b"0 0.5 0.5 0.25 0.5\n",
        },
    )
    samples = extract_yolo_archive(archive, staging_root=tmp_path / "staging", class_count=2)
    assert len(samples) == 1
    assert samples[0].width == 24
    assert samples[0].height == 16
    assert samples[0].annotations[0].class_index == 0
    assert samples[0].path.is_file()


@pytest.mark.parametrize("name", ["../escape.jpg", "/absolute.jpg", "C:/drive.jpg"])
def test_archive_rejects_path_escape(tmp_path: Path, name: str) -> None:
    archive = tmp_path / "unsafe.zip"
    write_zip(archive, {name: jpeg_bytes()})
    with pytest.raises(DatasetImportError) as error:
        validate_archive(archive)
    assert error.value.code == "lifecycle.archive_unsafe_path"


def test_archive_rejects_nested_archive(tmp_path: Path) -> None:
    archive = tmp_path / "nested.zip"
    write_zip(archive, {"nested.zip": b"not really a zip"})
    with pytest.raises(DatasetImportError) as error:
        validate_archive(archive)
    assert error.value.code == "lifecycle.archive_nested"


@pytest.mark.parametrize(
    "label",
    [
        "2 0.5 0.5 0.2 0.2",
        "0 nan 0.5 0.2 0.2",
        "0 0.1 0.5 0.4 0.2",
        "0 0.5 0.5 -0.2 0.2",
        "0 0.5 0.5 0.2",
    ],
)
def test_invalid_yolo_labels_are_rejected(label: str) -> None:
    with pytest.raises(DatasetImportError) as error:
        parse_yolo_label(label, class_count=2)
    assert error.value.code == "lifecycle.invalid_label"
