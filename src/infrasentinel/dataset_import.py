from __future__ import annotations

import hashlib
import math
import os
import shutil
import stat
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import cv2

from .storage import safe_path

IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
NESTED_ARCHIVE_TYPES = {".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar"}
MAX_ENTRIES = 20_000
MAX_ENTRY_BYTES = 100 * 1024**2
MAX_TOTAL_BYTES = 10 * 1024**3
MAX_COMPRESSION_RATIO = 100


class DatasetImportError(ValueError):
    def __init__(self, code: str, member: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.member = member


@dataclass(frozen=True)
class YoloAnnotation:
    class_index: int
    cx: float
    cy: float
    width: float
    height: float


@dataclass(frozen=True)
class ImportedSample:
    path: Path
    original_name: str
    mime_type: str
    byte_size: int
    sha256: str
    width: int
    height: int
    annotations: tuple[YoloAnnotation, ...]


def _safe_member_name(info: zipfile.ZipInfo) -> PurePosixPath:
    raw = info.filename.replace("\\", "/")
    path = PurePosixPath(raw)
    if not raw or raw.startswith("/") or path.is_absolute() or ".." in path.parts:
        raise DatasetImportError("lifecycle.archive_unsafe_path", info.filename)
    if path.parts and ":" in path.parts[0]:
        raise DatasetImportError("lifecycle.archive_unsafe_path", info.filename)
    unix_mode = info.external_attr >> 16
    if unix_mode and stat.S_ISLNK(unix_mode):
        raise DatasetImportError("lifecycle.archive_link_forbidden", info.filename)
    file_type = stat.S_IFMT(unix_mode)
    if file_type and not stat.S_ISREG(unix_mode):
        raise DatasetImportError("lifecycle.archive_device_forbidden", info.filename)
    return path


def validate_archive(archive_path: Path) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise DatasetImportError("lifecycle.invalid_archive") from exc
    with archive:
        files = [info for info in archive.infolist() if not info.is_dir()]
        if not files or len(files) > MAX_ENTRIES:
            raise DatasetImportError("lifecycle.archive_entry_limit")
        total = 0
        seen: set[str] = set()
        result: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        for info in files:
            path = _safe_member_name(info)
            normalized = path.as_posix().lower()
            if normalized in seen:
                raise DatasetImportError("lifecycle.archive_duplicate_path", info.filename)
            seen.add(normalized)
            if info.flag_bits & 0x1:
                raise DatasetImportError("lifecycle.archive_encrypted", info.filename)
            if path.suffix.lower() in NESTED_ARCHIVE_TYPES:
                raise DatasetImportError("lifecycle.archive_nested", info.filename)
            if info.file_size > MAX_ENTRY_BYTES:
                raise DatasetImportError("lifecycle.archive_entry_too_large", info.filename)
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise DatasetImportError("lifecycle.archive_too_large")
            compressed = max(info.compress_size, 1)
            if info.file_size > 1024**2 and info.file_size / compressed > MAX_COMPRESSION_RATIO:
                raise DatasetImportError("lifecycle.archive_ratio", info.filename)
            result.append((info, path))
        return result


def parse_yolo_label(text: str, class_count: int) -> tuple[YoloAnnotation, ...]:
    annotations: list[YoloAnnotation] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) != 5:
            raise DatasetImportError("lifecycle.invalid_label", str(line_number))
        try:
            class_index = int(fields[0])
            cx, cy, width, height = (float(value) for value in fields[1:])
        except ValueError as exc:
            raise DatasetImportError("lifecycle.invalid_label", str(line_number)) from exc
        values = (cx, cy, width, height)
        if (
            not 0 <= class_index < class_count
            or not all(math.isfinite(value) for value in values)
            or not _box_within_image(cx, cy, width, height)
        ):
            raise DatasetImportError("lifecycle.invalid_label", str(line_number))
        annotations.append(YoloAnnotation(class_index, cx, cy, width, height))
    return tuple(annotations)


def _box_within_image(cx: float, cy: float, width: float, height: float) -> bool:
    return (
        0 < width <= 1
        and 0 < height <= 1
        and cx - width / 2 >= 0
        and cx + width / 2 <= 1
        and cy - height / 2 >= 0
        and cy + height / 2 <= 1
    )


def extract_yolo_archive(
    archive_path: Path,
    *,
    staging_root: Path,
    class_count: int,
) -> list[ImportedSample]:
    members = validate_archive(archive_path)
    destination = safe_path(staging_root, uuid.uuid4().hex)
    destination.mkdir(parents=True, exist_ok=False)
    by_path = {path.as_posix().lower(): info for info, path in members}
    images = [(info, path) for info, path in members if path.suffix.lower() in IMAGE_TYPES]
    if not images:
        shutil.rmtree(destination)
        raise DatasetImportError("lifecycle.archive_no_images")
    imported: list[ImportedSample] = []
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for info, member_path in images:
                token = uuid.uuid4().hex
                output_path = safe_path(destination, f"{token}{member_path.suffix.lower()}")
                digest = hashlib.sha256()
                size = 0
                with archive.open(info) as source, output_path.open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        size += len(chunk)
                        if size > info.file_size or size > MAX_ENTRY_BYTES:
                            raise DatasetImportError(
                                "lifecycle.archive_entry_too_large", info.filename
                            )
                        digest.update(chunk)
                        output.write(chunk)
                image = cv2.imread(os.fspath(output_path))
                if image is None:
                    raise DatasetImportError("lifecycle.invalid_image", info.filename)
                height, width = image.shape[:2]
                label_info = _matching_label(member_path, by_path)
                annotations: tuple[YoloAnnotation, ...] = ()
                if label_info is not None:
                    raw = archive.read(label_info)
                    try:
                        annotations = parse_yolo_label(raw.decode("utf-8-sig"), class_count)
                    except UnicodeDecodeError as exc:
                        raise DatasetImportError(
                            "lifecycle.invalid_label", label_info.filename
                        ) from exc
                imported.append(
                    ImportedSample(
                        path=output_path,
                        original_name=member_path.name[:255],
                        mime_type=IMAGE_TYPES[member_path.suffix.lower()],
                        byte_size=size,
                        sha256=digest.hexdigest(),
                        width=width,
                        height=height,
                        annotations=annotations,
                    )
                )
        return imported
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def _matching_label(
    image_path: PurePosixPath, by_path: dict[str, zipfile.ZipInfo]
) -> zipfile.ZipInfo | None:
    direct = image_path.with_suffix(".txt").as_posix().lower()
    if direct in by_path:
        return by_path[direct]
    parts = list(image_path.parts)
    if "images" in [part.lower() for part in parts]:
        index = [part.lower() for part in parts].index("images")
        parts[index] = "labels"
        paired = PurePosixPath(*parts).with_suffix(".txt").as_posix().lower()
        return by_path.get(paired)
    return None
