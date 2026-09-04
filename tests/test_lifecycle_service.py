from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from infrasentinel.database import Base
from infrasentinel.errors import InfraError
from infrasentinel.lifecycle_models import (
    DatasetCategory,
    DatasetSample,
    ReviewStatus,
    SampleAnnotation,
    VersionStatus,
)
from infrasentinel.lifecycle_service import (
    assign_version_splits,
    create_dataset,
    deterministic_split,
    freeze_version,
    replace_annotations,
    restore_annotations,
    review_sample,
    seed_default_categories,
)
from infrasentinel.models import Project, User, UserRole, UserStatus


def make_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def seed_identity(db: Session) -> tuple[User, Project]:
    user = User(
        email="admin@example.com",
        username="admin2",
        display_name="Admin",
        password_hash="hash",
        role=UserRole.ADMIN,
        status=UserStatus.ENABLED,
    )
    project = Project(code="DATA", name="Dataset Project")
    db.add_all([user, project])
    db.commit()
    return user, project


def test_deterministic_split_keeps_duplicate_hashes_together() -> None:
    digest = "a" * 64
    assert deterministic_split(digest) == deterministic_split(digest.upper())


def test_annotation_revision_quality_and_freeze_workflow() -> None:
    with make_db() as db:
        user, project = seed_identity(db)
        categories = seed_default_categories(db)
        dataset, version = create_dataset(
            db, user=user, project_id=project.id, name="Site inspection"
        )
        first = DatasetSample(
            version_id=version.id,
            storage_key="datasets/first.jpg",
            original_name="first.jpg",
            mime_type="image/jpeg",
            byte_size=12,
            sha256="1" * 64,
            width=100,
            height=100,
            created_by=user.id,
        )
        duplicate = DatasetSample(
            version_id=version.id,
            storage_key="datasets/duplicate.jpg",
            original_name="duplicate.jpg",
            mime_type="image/jpeg",
            byte_size=12,
            sha256="1" * 64,
            width=100,
            height=100,
            created_by=user.id,
        )
        db.add_all([first, duplicate])
        version.sample_count = 2
        version.byte_size = 24
        db.commit()

        counts = assign_version_splits(db, version)
        assert first.split == duplicate.split
        assert sum(counts.values()) == 2
        assert first.duplicate_group == first.sha256

        replace_annotations(
            db,
            user=user,
            sample_id=first.id,
            expected_revision=1,
            annotations=[
                {
                    "category_id": categories[0].id,
                    "cx": 0.5,
                    "cy": 0.5,
                    "width": 0.4,
                    "height": 0.4,
                }
            ],
        )
        assert first.revision == 2
        assert first.review_status == ReviewStatus.UNREVIEWED
        assert db.scalar(select(SampleAnnotation).where(SampleAnnotation.sample_id == first.id))

        with pytest.raises(InfraError) as conflict:
            replace_annotations(
                db,
                user=user,
                sample_id=first.id,
                expected_revision=1,
                annotations=[],
            )
        assert conflict.value.code == "lifecycle.revision_conflict"

        reviewed = review_sample(
            db,
            user=user,
            sample_id=first.id,
            expected_revision=2,
            status=ReviewStatus.APPROVED,
        )
        assert reviewed.review_status == ReviewStatus.APPROVED
        restored = restore_annotations(
            db,
            user=user,
            sample_id=first.id,
            expected_revision=3,
        )
        assert restored.revision == 4
        assert restored.review_status == ReviewStatus.UNREVIEWED
        assert (
            db.scalar(select(SampleAnnotation).where(SampleAnnotation.sample_id == first.id))
            is None
        )
        redone = restore_annotations(
            db,
            user=user,
            sample_id=first.id,
            expected_revision=4,
            redo=True,
        )
        assert (
            db.scalar(select(SampleAnnotation).where(SampleAnnotation.sample_id == redone.id))
            is not None
        )
        replaced_again = replace_annotations(
            db,
            user=user,
            sample_id=first.id,
            expected_revision=redone.revision,
            annotations=[],
        )
        first_undo = restore_annotations(
            db,
            user=user,
            sample_id=first.id,
            expected_revision=replaced_again.revision,
        )
        assert db.scalar(
            select(SampleAnnotation).where(SampleAnnotation.sample_id == first_undo.id)
        )
        second_undo = restore_annotations(
            db,
            user=user,
            sample_id=first.id,
            expected_revision=first_undo.revision,
        )
        assert (
            db.scalar(select(SampleAnnotation).where(SampleAnnotation.sample_id == second_undo.id))
            is None
        )
        first_redo = restore_annotations(
            db,
            user=user,
            sample_id=first.id,
            expected_revision=second_undo.revision,
            redo=True,
        )
        assert db.scalar(
            select(SampleAnnotation).where(SampleAnnotation.sample_id == first_redo.id)
        )
        second_redo = restore_annotations(
            db,
            user=user,
            sample_id=first.id,
            expected_revision=first_redo.revision,
            redo=True,
        )
        assert (
            db.scalar(select(SampleAnnotation).where(SampleAnnotation.sample_id == second_redo.id))
            is None
        )

        with pytest.raises(InfraError) as blocked:
            freeze_version(db, user=user, version=version)
        assert blocked.value.code == "lifecycle.quality_blocked"
        assert version.status == VersionStatus.DRAFT


def test_annotation_rejects_box_outside_image() -> None:
    with make_db() as db:
        user, project = seed_identity(db)
        seed_default_categories(db)
        _, version = create_dataset(db, user=user, project_id=project.id, name="Boxes")
        sample = DatasetSample(
            version_id=version.id,
            storage_key="datasets/bad.jpg",
            original_name="bad.jpg",
            mime_type="image/jpeg",
            byte_size=5,
            sha256="2" * 64,
            created_by=user.id,
        )
        db.add(sample)
        db.commit()
        category = db.scalar(select(DatasetCategory))
        with pytest.raises(InfraError) as invalid:
            replace_annotations(
                db,
                user=user,
                sample_id=sample.id,
                expected_revision=1,
                annotations=[
                    {
                        "category_id": uuid.UUID(str(category.id)),
                        "cx": 0.1,
                        "cy": 0.5,
                        "width": 0.4,
                        "height": 0.4,
                    }
                ],
            )
        assert invalid.value.code == "lifecycle.invalid_annotation"
