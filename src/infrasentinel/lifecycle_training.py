from __future__ import annotations

import hashlib
import shutil
from collections.abc import Mapping
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .errors import InfraError
from .lifecycle_jobs import LifecycleCancelled
from .lifecycle_models import (
    DatasetCategory,
    DatasetSample,
    DatasetVersion,
    LifecycleArtifact,
    LifecycleJob,
    ManagedModelVersion,
    SampleAnnotation,
    VersionStatus,
)
from .lifecycle_service import DEFAULT_CATEGORIES
from .storage import safe_path
from .vision_models import sha256_file


def export_yolo_dataset(db: Session, job: LifecycleJob, storage_root: Path) -> Path:
    if job.version_id is None:
        raise InfraError(409, "lifecycle.version_not_trainable")
    version = db.get(DatasetVersion, job.version_id)
    if version is None or version.status not in {VersionStatus.FROZEN, VersionStatus.TRAINING}:
        raise InfraError(409, "lifecycle.version_not_trainable")
    export_root = safe_path(storage_root, "exports", str(job.id))
    if export_root.exists():
        shutil.rmtree(export_root)
    export_root.mkdir(parents=True)
    category_codes = [code for code, *_ in DEFAULT_CATEGORIES]
    categories = {
        item.id: item.code
        for item in db.scalars(
            select(DatasetCategory).where(DatasetCategory.code.in_(category_codes))
        )
    }
    class_indexes = {code: index for index, code in enumerate(category_codes)}
    samples = db.scalars(
        select(DatasetSample)
        .where(DatasetSample.version_id == version.id)
        .order_by(DatasetSample.id)
    ).all()
    if not samples:
        raise InfraError(409, "lifecycle.quality_blocked")
    for sample in samples:
        split = sample.split.value if hasattr(sample.split, "value") else str(sample.split)
        if split not in {"train", "val", "test"}:
            raise InfraError(409, "lifecycle.invalid_split")
        source = safe_path(storage_root, *Path(sample.storage_key).parts)
        if not source.is_file():
            raise InfraError(409, "lifecycle.sample_not_found")
        image_dir = safe_path(export_root, "images", split)
        label_dir = safe_path(export_root, "labels", split)
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        name = f"{sample.id.hex}{source.suffix.lower()}"
        shutil.copy2(source, image_dir / name)
        annotations = db.scalars(
            select(SampleAnnotation).where(SampleAnnotation.sample_id == sample.id)
        )
        lines = []
        for annotation in annotations:
            code = categories.get(annotation.category_id)
            if code not in class_indexes:
                raise InfraError(409, "lifecycle.invalid_category")
            lines.append(
                f"{class_indexes[code]} {annotation.cx:.8f} {annotation.cy:.8f} "
                f"{annotation.width:.8f} {annotation.height:.8f}"
            )
        (label_dir / f"{sample.id.hex}.txt").write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
        )
    names = "\n".join(f"  {index}: {code}" for index, code in enumerate(category_codes))
    (export_root / "data.yaml").write_text(
        f"path: {export_root.as_posix()}\n"
        "train: images/train\nval: images/val\ntest: images/test\n"
        f"names:\n{names}\n",
        encoding="utf-8",
    )
    return export_root


def package_yolo_export(db: Session, job: LifecycleJob, storage_root: Path) -> LifecycleArtifact:
    export_root = export_yolo_dataset(db, job, storage_root)
    storage_key = f"artifacts/datasets/{job.version_id}/{job.id}.zip"
    archive_path = safe_path(storage_root, *Path(storage_key).parts)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.make_archive(str(archive_path.with_suffix("")), "zip", export_root)
    digest = hashlib.sha256()
    with archive_path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    artifact = LifecycleArtifact(
        job_id=job.id,
        kind="dataset_export",
        storage_key=storage_key,
        mime_type="application/zip",
        byte_size=archive_path.stat().st_size,
        sha256=digest.hexdigest(),
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def train_with_ultralytics(
    db: Session, *, job: LifecycleJob, storage_root: Path
) -> ManagedModelVersion:
    config = job.config_json or {}
    base_model = Path(str(config.get("base_model_path", ""))).resolve()
    if not base_model.is_file() or base_model.suffix.lower() != ".pt":
        raise InfraError(409, "lifecycle.base_model_required")
    export_root = export_yolo_dataset(db, job, storage_root)
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise InfraError(503, "lifecycle.runner_unavailable") from exc
    runner = YOLO(str(base_model))

    def check_cancel(trainer) -> None:
        db.refresh(job)
        if job.cancel_requested:
            raise LifecycleCancelled("lifecycle.cancelled")
        job.progress = min(95, round((trainer.epoch + 1) / max(trainer.epochs, 1) * 90) + 5)
        job.progress_detail = f"epoch {trainer.epoch + 1}/{trainer.epochs}"
        db.commit()

    runner.add_callback("on_train_epoch_end", check_cancel)
    results = runner.train(
        data=str(export_root / "data.yaml"),
        epochs=max(1, min(int(config.get("epochs", 50)), 500)),
        imgsz=max(320, min(int(config.get("imgsz", 640)), 1280)),
        batch=max(1, min(int(config.get("batch", 8)), 128)),
        device=str(config.get("device", "auto")),
        project=str(safe_path(storage_root, "training-runs")),
        name=str(job.id),
        exist_ok=True,
        pretrained=True,
    )
    run_root = safe_path(storage_root, "training-runs")
    run_dir = Path(results.save_dir).resolve()
    if not run_dir.is_relative_to(run_root.resolve()):
        raise InfraError(500, "lifecycle.training_output_missing")
    best = run_dir / "weights" / "best.pt"
    if not best.is_file():
        raise InfraError(500, "lifecycle.training_output_missing")
    code = str(config.get("code", "infrasentinel-custom"))[:100]
    next_version = (
        db.scalar(
            select(func.max(ManagedModelVersion.version_number)).where(
                ManagedModelVersion.code == code
            )
        )
        or 0
    ) + 1
    digest = sha256_file(best)
    storage_key = f"models/{code}/v{next_version}/{digest[:16]}.pt"
    target = safe_path(storage_root, *Path(storage_key).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, target)
    artifact = LifecycleArtifact(
        job_id=job.id,
        kind="weights",
        storage_key=storage_key,
        mime_type="application/octet-stream",
        byte_size=target.stat().st_size,
        sha256=digest,
    )
    db.add(artifact)
    db.flush()
    raw_metrics = getattr(results, "results_dict", {}) or {}
    if not isinstance(raw_metrics, Mapping):
        raw_metrics = {}
    metrics = _canonical_metrics(raw_metrics)
    metrics["runner"] = "ultralytics"
    _register_run_artifacts(db, job, storage_root, run_dir)
    model = ManagedModelVersion(
        code=code,
        version_number=next_version,
        scene=str(config.get("scene", "pipeline"))[:30],
        size_variant=str(config.get("size_variant", "n"))[:1],
        training_job_id=job.id,
        dataset_version_id=job.version_id,
        weight_artifact_id=artifact.id,
        model_card=str(config.get("model_card", "Locally trained Ultralytics model")),
        class_map_json=[code for code, *_ in DEFAULT_CATEGORIES],
        metrics_json=metrics,
        created_by=job.owner_id,
    )
    db.add(model)
    job.model_version_id = model.id
    version = db.get(DatasetVersion, job.version_id)
    if version:
        version.status = VersionStatus.FROZEN
    db.commit()
    db.refresh(model)
    return model


def evaluate_with_ultralytics(
    db: Session, *, job: LifecycleJob, storage_root: Path
) -> dict[str, float | str]:
    model = db.get(ManagedModelVersion, job.model_version_id)
    if model is None:
        raise InfraError(404, "lifecycle.model_not_found")
    artifact = db.get(LifecycleArtifact, model.weight_artifact_id)
    if artifact is None:
        raise InfraError(409, "lifecycle.training_output_missing")
    weight_path = safe_path(storage_root, *Path(artifact.storage_key).parts)
    if not weight_path.is_file() or sha256_file(weight_path) != artifact.sha256:
        raise InfraError(409, "lifecycle.artifact_integrity_failed")
    export_root = export_yolo_dataset(db, job, storage_root)
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise InfraError(503, "lifecycle.runner_unavailable") from exc
    run_root = safe_path(storage_root, "evaluation-runs")
    results = YOLO(str(weight_path)).val(
        data=str(export_root / "data.yaml"),
        split="test",
        imgsz=max(320, min(int((job.config_json or {}).get("imgsz", 640)), 1536)),
        device=str((job.config_json or {}).get("device", "auto")),
        project=str(run_root),
        name=str(job.id),
        exist_ok=True,
        plots=True,
    )
    run_dir = Path(results.save_dir).resolve()
    if not run_dir.is_relative_to(run_root.resolve()):
        raise InfraError(500, "lifecycle.training_output_missing")
    raw_metrics = getattr(results, "results_dict", {}) or {}
    metrics = _canonical_metrics(raw_metrics if isinstance(raw_metrics, Mapping) else {})
    metrics["runner"] = "ultralytics-evaluate"
    model.metrics_json = metrics
    _register_run_artifacts(db, job, storage_root, run_dir)
    db.commit()
    return metrics


def _canonical_metrics(raw: Mapping[str, object]) -> dict[str, float]:
    aliases = {
        "map50": ("map50", "metrics/mAP50(B)"),
        "map50_95": ("map50_95", "metrics/mAP50-95(B)"),
        "precision": ("precision", "metrics/precision(B)"),
        "recall": ("recall", "metrics/recall(B)"),
    }
    metrics = {
        name: float(raw[key])
        for name, keys in aliases.items()
        for key in keys
        if key in raw and _numeric(raw[key])
    }
    precision = metrics.get("precision")
    recall = metrics.get("recall")
    if precision is not None and recall is not None and precision + recall:
        metrics["f1"] = 2 * precision * recall / (precision + recall)
    return metrics


def _register_run_artifacts(
    db: Session, job: LifecycleJob, storage_root: Path, run_dir: Path
) -> None:
    for relative, kind, mime in (
        ("weights/last.pt", "last_weights", "application/octet-stream"),
        ("results.csv", "training_metrics", "text/csv"),
        ("results.png", "training_plot", "image/png"),
        ("confusion_matrix.png", "confusion_matrix", "image/png"),
        ("PR_curve.png", "pr_curve", "image/png"),
    ):
        path = (run_dir / relative).resolve()
        if not path.is_relative_to(run_dir) or not path.is_file():
            continue
        storage_key = path.relative_to(storage_root.resolve()).as_posix()
        if db.scalar(
            select(LifecycleArtifact.id).where(LifecycleArtifact.storage_key == storage_key)
        ):
            continue
        db.add(
            LifecycleArtifact(
                job_id=job.id,
                kind=kind,
                storage_key=storage_key,
                mime_type=mime,
                byte_size=path.stat().st_size,
                sha256=sha256_file(path),
            )
        )


def _numeric(value: object) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False
