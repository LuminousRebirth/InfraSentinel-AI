from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from infrasentinel.database import Base
from infrasentinel.lifecycle_models import (
    DatasetSample,
    LifecycleJob,
    LifecycleJobKind,
    SampleAnnotation,
    SampleSplit,
    VersionStatus,
)
from infrasentinel.lifecycle_service import create_dataset, seed_default_categories
from infrasentinel.lifecycle_training import (
    _canonical_metrics,
    export_yolo_dataset,
    package_yolo_export,
)
from infrasentinel.models import Project, User, UserRole, UserStatus


def test_yolo_export_stays_contained_and_is_repeatable(tmp_path) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        admin = User(
            email="export@example.com",
            username="export-admin",
            display_name="Export",
            password_hash="hash",
            role=UserRole.ADMIN,
            status=UserStatus.ENABLED,
        )
        project = Project(code="EXPORT", name="Export")
        db.add_all([admin, project])
        db.commit()
        categories = seed_default_categories(db)
        _, version = create_dataset(db, user=admin, project_id=project.id, name="Export")
        source = tmp_path / "datasets" / "source.jpg"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"fixture")
        sample = DatasetSample(
            version_id=version.id,
            storage_key="datasets/source.jpg",
            original_name="source.jpg",
            mime_type="image/jpeg",
            byte_size=7,
            sha256="a" * 64,
            width=10,
            height=10,
            split=SampleSplit.TRAIN,
            created_by=admin.id,
        )
        db.add(sample)
        db.flush()
        db.add(
            SampleAnnotation(
                sample_id=sample.id,
                category_id=categories[0].id,
                cx=0.5,
                cy=0.5,
                width=0.2,
                height=0.2,
                created_by=admin.id,
            )
        )
        version.status = VersionStatus.FROZEN
        job = LifecycleJob(
            kind=LifecycleJobKind.EXPORT,
            project_id=project.id,
            owner_id=admin.id,
            version_id=version.id,
        )
        db.add(job)
        db.commit()
        first = export_yolo_dataset(db, job, tmp_path)
        label = first / "labels" / "train" / f"{sample.id.hex}.txt"
        assert label.read_text(encoding="utf-8").startswith("0 0.50000000")
        assert (first / "data.yaml").is_file()
        second = export_yolo_dataset(db, job, tmp_path)
        assert second == first
        assert second.is_relative_to(tmp_path)
        artifact = package_yolo_export(db, job, tmp_path)
        archive = tmp_path / artifact.storage_key
        assert archive.is_file()
        assert archive.suffix == ".zip"
        assert artifact.byte_size == archive.stat().st_size
        assert len(artifact.sha256) == 64


def test_ultralytics_metrics_are_normalized_for_publication() -> None:
    metrics = _canonical_metrics(
        {
            "metrics/mAP50(B)": 0.8,
            "metrics/mAP50-95(B)": 0.6,
            "metrics/precision(B)": 0.75,
            "metrics/recall(B)": 0.5,
        }
    )
    assert metrics["map50"] == 0.8
    assert metrics["precision"] == 0.75
    assert metrics["f1"] == 0.6
