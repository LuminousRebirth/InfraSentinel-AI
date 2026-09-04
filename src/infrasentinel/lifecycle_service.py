from __future__ import annotations

import hashlib
import statistics
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .database import utc_now
from .detection_service import require_project_access
from .errors import InfraError
from .lifecycle_models import (
    Dataset,
    DatasetCategory,
    DatasetChange,
    DatasetSample,
    DatasetStatus,
    DatasetVersion,
    FindingSeverity,
    QualityFinding,
    ReviewStatus,
    SampleAnnotation,
    SampleSplit,
    VersionStatus,
)
from .models import User, UserRole
from .services import record_audit

DEFAULT_CATEGORIES = (
    ("CK", "管道裂缝", "Pipeline crack", "#ef4444"),
    ("PL", "管道修补", "Pipeline repair", "#f97316"),
    ("SG", "管道沉积", "Pipeline deposit", "#eab308"),
    ("SL", "管道表面破损", "Pipeline surface damage", "#84cc16"),
    ("TL", "管道树根", "Pipeline root intrusion", "#22c55e"),
    ("ZW", "管道障碍物", "Pipeline obstruction", "#06b6d4"),
    ("helmet", "已佩戴安全帽", "Safety helmet", "#3b82f6"),
    ("no_helmet", "未佩戴安全帽", "Missing safety helmet", "#a855f7"),
)


def _value(item: Any) -> str:
    return item.value if hasattr(item, "value") else str(item)


def require_admin(user: User) -> None:
    if user.role != UserRole.ADMIN:
        raise InfraError(403, "auth.forbidden")


def seed_default_categories(db: Session) -> list[DatasetCategory]:
    categories: list[DatasetCategory] = []
    for code, name_zh, name_en, color in DEFAULT_CATEGORIES:
        category = db.scalar(select(DatasetCategory).where(DatasetCategory.code == code))
        if category is None:
            category = DatasetCategory(
                code=code,
                name_zh=name_zh,
                name_en=name_en,
                color=color,
            )
            db.add(category)
        categories.append(category)
    db.commit()
    return categories


def require_dataset_access(db: Session, user: User, dataset_id: uuid.UUID) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None or dataset.status == DatasetStatus.ARCHIVED:
        raise InfraError(404, "lifecycle.dataset_not_found")
    require_project_access(db, user, dataset.project_id)
    return dataset


def require_version_access(db: Session, user: User, version_id: uuid.UUID) -> DatasetVersion:
    version = db.get(DatasetVersion, version_id)
    if version is None:
        raise InfraError(404, "lifecycle.version_not_found")
    require_dataset_access(db, user, version.dataset_id)
    return version


def require_draft(version: DatasetVersion) -> None:
    if version.status != VersionStatus.DRAFT:
        raise InfraError(409, "lifecycle.version_immutable")


def create_dataset(
    db: Session,
    *,
    user: User,
    project_id: uuid.UUID,
    name: str,
    description: str | None = None,
) -> tuple[Dataset, DatasetVersion]:
    require_admin(user)
    require_project_access(db, user, project_id)
    dataset = Dataset(
        project_id=project_id,
        owner_id=user.id,
        name=name.strip(),
        description=(description or "").strip() or None,
    )
    db.add(dataset)
    db.flush()
    version = DatasetVersion(dataset_id=dataset.id, version_number=1, created_by=user.id)
    db.add(version)
    record_audit(
        db,
        action="lifecycle.dataset_create",
        target_type="dataset",
        target_id=dataset.id,
        actor_id=user.id,
        after_state={"project_id": str(project_id), "name": dataset.name},
    )
    db.commit()
    db.refresh(dataset)
    db.refresh(version)
    return dataset, version


def create_dataset_version(
    db: Session,
    *,
    user: User,
    dataset: Dataset,
    source: str = "upload",
    train_ratio: int = 80,
    val_ratio: int = 10,
    test_ratio: int = 10,
) -> DatasetVersion:
    require_admin(user)
    require_dataset_access(db, user, dataset.id)
    if min(train_ratio, val_ratio, test_ratio) < 0 or train_ratio + val_ratio + test_ratio != 100:
        raise InfraError(422, "lifecycle.invalid_split")
    latest = db.scalar(
        select(func.max(DatasetVersion.version_number)).where(
            DatasetVersion.dataset_id == dataset.id
        )
    )
    version = DatasetVersion(
        dataset_id=dataset.id,
        version_number=(latest or 0) + 1,
        source=source[:100],
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
        created_by=user.id,
    )
    db.add(version)
    db.flush()
    record_audit(
        db,
        action="lifecycle.version_create",
        target_type="dataset_version",
        target_id=version.id,
        actor_id=user.id,
        after_state={"dataset_id": str(dataset.id), "version_number": version.version_number},
    )
    db.commit()
    db.refresh(version)
    return version


def deterministic_split(sha256: str, *, train_ratio: int = 80, val_ratio: int = 10) -> SampleSplit:
    bucket = int(hashlib.sha256(sha256.lower().encode("ascii")).hexdigest()[:16], 16) % 100
    if bucket < train_ratio:
        return SampleSplit.TRAIN
    if bucket < train_ratio + val_ratio:
        return SampleSplit.VAL
    return SampleSplit.TEST


def assign_version_splits(db: Session, version: DatasetVersion) -> dict[str, int]:
    require_draft(version)
    counts = {item.value: 0 for item in (SampleSplit.TRAIN, SampleSplit.VAL, SampleSplit.TEST)}
    samples = db.scalars(
        select(DatasetSample)
        .where(
            DatasetSample.version_id == version.id,
            DatasetSample.media_type == "image",
        )
        .order_by(DatasetSample.sha256, DatasetSample.id)
    ).all()
    groups: dict[str, SampleSplit] = {}
    hash_counts = Counter(sample.sha256 for sample in samples)
    for sample in samples:
        split = groups.setdefault(
            sample.sha256,
            deterministic_split(
                sample.sha256,
                train_ratio=version.train_ratio,
                val_ratio=version.val_ratio,
            ),
        )
        sample.split = split
        sample.duplicate_group = sample.sha256 if hash_counts[sample.sha256] > 1 else None
        counts[split.value] += 1
    db.flush()
    return counts


def replace_annotations(
    db: Session,
    *,
    user: User,
    sample_id: uuid.UUID,
    expected_revision: int,
    annotations: Iterable[Mapping[str, Any]],
) -> DatasetSample:
    sample = db.get(DatasetSample, sample_id)
    if sample is None:
        raise InfraError(404, "lifecycle.sample_not_found")
    version = require_version_access(db, user, sample.version_id)
    require_draft(version)
    if sample.revision != expected_revision:
        raise InfraError(409, "lifecycle.revision_conflict")
    incoming = list(annotations)
    category_ids = {uuid.UUID(str(item["category_id"])) for item in incoming}
    categories = {
        category.id: category
        for category in db.scalars(
            select(DatasetCategory).where(DatasetCategory.id.in_(category_ids))
        )
    }
    if len(categories) != len(category_ids) or any(
        not item.enabled for item in categories.values()
    ):
        raise InfraError(422, "lifecycle.invalid_category")
    before = [
        {
            "category_id": str(item.category_id),
            "cx": item.cx,
            "cy": item.cy,
            "width": item.width,
            "height": item.height,
        }
        for item in db.scalars(
            select(SampleAnnotation).where(SampleAnnotation.sample_id == sample.id)
        )
    ]
    db.execute(delete(SampleAnnotation).where(SampleAnnotation.sample_id == sample.id))
    after: list[dict[str, Any]] = []
    for item in incoming:
        values = {key: float(item[key]) for key in ("cx", "cy", "width", "height")}
        if not _valid_box(**values):
            raise InfraError(422, "lifecycle.invalid_annotation")
        category_id = uuid.UUID(str(item["category_id"]))
        db.add(
            SampleAnnotation(
                sample_id=sample.id,
                category_id=category_id,
                created_by=user.id,
                **values,
            )
        )
        after.append({"category_id": str(category_id), **values})
    sample.revision += 1
    sample.review_status = ReviewStatus.UNREVIEWED
    version.revision += 1
    version.annotation_count = int(
        db.scalar(
            select(func.count(SampleAnnotation.id)).where(
                SampleAnnotation.sample_id != sample.id,
                SampleAnnotation.sample_id.in_(
                    select(DatasetSample.id).where(DatasetSample.version_id == version.id)
                ),
            )
        )
        or 0
    ) + len(after)
    db.add(
        DatasetChange(
            version_id=version.id,
            sample_id=sample.id,
            actor_id=user.id,
            action="annotations.replace",
            before_state={"annotations": before, "revision": expected_revision},
            after_state={"annotations": after, "revision": sample.revision},
        )
    )
    record_audit(
        db,
        action="lifecycle.annotations_replace",
        target_type="dataset_sample",
        target_id=sample.id,
        actor_id=user.id,
        before_state={"revision": expected_revision, "count": len(before)},
        after_state={"revision": sample.revision, "count": len(after)},
    )
    db.commit()
    db.refresh(sample)
    return sample


def review_sample(
    db: Session,
    *,
    user: User,
    sample_id: uuid.UUID,
    expected_revision: int,
    status: ReviewStatus,
) -> DatasetSample:
    sample = db.get(DatasetSample, sample_id)
    if sample is None:
        raise InfraError(404, "lifecycle.sample_not_found")
    version = require_version_access(db, user, sample.version_id)
    require_draft(version)
    if sample.revision != expected_revision:
        raise InfraError(409, "lifecycle.revision_conflict")
    before = _sample_state(db, sample)
    sample.review_status = status
    sample.reviewed_by = user.id
    sample.reviewed_at = utc_now()
    sample.revision += 1
    version.revision += 1
    db.add(
        DatasetChange(
            version_id=version.id,
            sample_id=sample.id,
            actor_id=user.id,
            action="sample.review",
            before_state=before,
            after_state=_sample_state(db, sample),
        )
    )
    record_audit(
        db,
        action="lifecycle.sample_review",
        target_type="dataset_sample",
        target_id=sample.id,
        actor_id=user.id,
        after_state={"status": status.value, "revision": sample.revision},
    )
    db.commit()
    db.refresh(sample)
    return sample


def restore_annotations(
    db: Session,
    *,
    user: User,
    sample_id: uuid.UUID,
    expected_revision: int,
    redo: bool = False,
) -> DatasetSample:
    sample = db.get(DatasetSample, sample_id)
    if sample is None:
        raise InfraError(404, "lifecycle.sample_not_found")
    version = require_version_access(db, user, sample.version_id)
    require_draft(version)
    if sample.revision != expected_revision:
        raise InfraError(409, "lifecycle.revision_conflict")
    actions = ["annotations.undo"] if redo else ["annotations.replace", "annotations.redo"]
    current = _sample_state(db, sample)
    # ponytail: bound interactive history to 1000 edits; add a persisted cursor if needed.
    changes = db.scalars(
        select(DatasetChange)
        .where(
            DatasetChange.sample_id == sample.id,
            DatasetChange.action.in_(actions),
        )
        .order_by(DatasetChange.created_at.desc(), DatasetChange.id.desc())
        .limit(1000)
    ).all()
    change = next(
        (
            item
            for item in changes
            if (item.after_state or {}).get("annotations") == current["annotations"]
        ),
        None,
    )
    if change is None:
        raise InfraError(409, "lifecycle.no_annotation_history")
    desired = list((change.before_state or {}).get("annotations", []))
    before = current
    db.execute(delete(SampleAnnotation).where(SampleAnnotation.sample_id == sample.id))
    for item in desired:
        db.add(
            SampleAnnotation(
                sample_id=sample.id,
                category_id=uuid.UUID(str(item["category_id"])),
                cx=float(item["cx"]),
                cy=float(item["cy"]),
                width=float(item["width"]),
                height=float(item["height"]),
                created_by=user.id,
            )
        )
    sample.revision += 1
    sample.review_status = ReviewStatus.UNREVIEWED
    version.revision += 1
    after = {"annotations": desired, "revision": sample.revision}
    db.add(
        DatasetChange(
            version_id=version.id,
            sample_id=sample.id,
            actor_id=user.id,
            action="annotations.redo" if redo else "annotations.undo",
            before_state=before,
            after_state=after,
        )
    )
    record_audit(
        db,
        action="lifecycle.annotations_redo" if redo else "lifecycle.annotations_undo",
        target_type="dataset_sample",
        target_id=sample.id,
        actor_id=user.id,
        after_state={"revision": sample.revision, "count": len(desired)},
    )
    version.annotation_count = int(
        db.scalar(
            select(func.count(SampleAnnotation.id)).where(
                SampleAnnotation.sample_id != sample.id,
                SampleAnnotation.sample_id.in_(
                    select(DatasetSample.id).where(DatasetSample.version_id == version.id)
                ),
            )
        )
        or 0
    ) + len(desired)
    db.commit()
    db.refresh(sample)
    return sample


def _sample_state(db: Session, sample: DatasetSample) -> dict[str, Any]:
    annotations = [
        {
            "category_id": str(item.category_id),
            "cx": item.cx,
            "cy": item.cy,
            "width": item.width,
            "height": item.height,
        }
        for item in db.scalars(
            select(SampleAnnotation).where(SampleAnnotation.sample_id == sample.id)
        )
    ]
    return {
        "annotations": annotations,
        "revision": sample.revision,
        "review_status": _value(sample.review_status),
    }


def _valid_box(*, cx: float, cy: float, width: float, height: float) -> bool:
    return (
        0 < width <= 1
        and 0 < height <= 1
        and cx - width / 2 >= 0
        and cx + width / 2 <= 1
        and cy - height / 2 >= 0
        and cy + height / 2 <= 1
    )


def run_quality_checks(db: Session, version: DatasetVersion) -> list[QualityFinding]:
    db.execute(
        delete(QualityFinding).where(
            QualityFinding.version_id == version.id,
            QualityFinding.resolved.is_(False),
        )
    )
    samples = db.scalars(select(DatasetSample).where(DatasetSample.version_id == version.id)).all()
    annotation_counts = (
        dict(
            db.execute(
                select(SampleAnnotation.sample_id, func.count(SampleAnnotation.id))
                .where(SampleAnnotation.sample_id.in_([item.id for item in samples]))
                .group_by(SampleAnnotation.sample_id)
            ).all()
        )
        if samples
        else {}
    )
    findings: list[QualityFinding] = []
    image_samples = [sample for sample in samples if sample.media_type == "image"]
    splits_by_hash: dict[str, set[str]] = {}
    for sample in samples:
        if sample.media_type == "video":
            continue
        splits_by_hash.setdefault(sample.sha256, set()).add(_value(sample.split))
        if not annotation_counts.get(sample.id):
            findings.append(
                QualityFinding(
                    version_id=version.id,
                    sample_id=sample.id,
                    code="missing_annotation",
                    severity=FindingSeverity.ERROR,
                    message=f"{sample.original_name} has no annotations",
                    suggestion="Annotate or remove this sample before freezing",
                )
            )
        if sample.duplicate_group:
            findings.append(
                QualityFinding(
                    version_id=version.id,
                    sample_id=sample.id,
                    code="duplicate_content",
                    severity=FindingSeverity.WARNING,
                    message=f"{sample.original_name} duplicates another sample",
                    suggestion="Review duplicate content",
                )
            )
    for digest, splits in splits_by_hash.items():
        if len(splits) > 1:
            findings.append(
                QualityFinding(
                    version_id=version.id,
                    code="cross_split_duplicate",
                    severity=FindingSeverity.ERROR,
                    message=f"Duplicate content {digest[:12]} appears in multiple splits",
                    suggestion="Re-run deterministic splitting before freezing",
                )
            )
    category_counts = [
        count
        for (count,) in db.execute(
            select(func.count(SampleAnnotation.id))
            .join(DatasetSample, DatasetSample.id == SampleAnnotation.sample_id)
            .where(DatasetSample.version_id == version.id)
            .group_by(SampleAnnotation.category_id)
        )
    ]
    if len(category_counts) > 1 and min(category_counts) < statistics.median(category_counts) * 0.2:
        findings.append(
            QualityFinding(
                version_id=version.id,
                code="class_imbalance",
                severity=FindingSeverity.WARNING,
                message="One or more classes have substantially fewer annotations",
                suggestion="Collect or annotate more examples for underrepresented classes",
            )
        )
    if not image_samples:
        findings.append(
            QualityFinding(
                version_id=version.id,
                code="empty_dataset",
                severity=FindingSeverity.ERROR,
                message="Dataset version has no samples",
                suggestion="Import labeled images before freezing",
            )
        )
    db.add_all(findings)
    db.commit()
    return findings


def freeze_version(db: Session, *, user: User, version: DatasetVersion) -> DatasetVersion:
    require_admin(user)
    require_draft(version)
    assign_version_splits(db, version)
    findings = run_quality_checks(db, version)
    if any(_value(item.severity) == FindingSeverity.ERROR.value for item in findings):
        raise InfraError(409, "lifecycle.quality_blocked")
    version.status = VersionStatus.FROZEN
    version.frozen_at = utc_now()
    version.revision += 1
    record_audit(
        db,
        action="lifecycle.version_freeze",
        target_type="dataset_version",
        target_id=version.id,
        actor_id=user.id,
        after_state={"version_number": version.version_number},
    )
    db.commit()
    db.refresh(version)
    return version
