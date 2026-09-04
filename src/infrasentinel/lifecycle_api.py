from __future__ import annotations

import os
import shutil
import uuid
from collections import Counter
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import func, select

from .database import utc_now
from .dataset_import import DatasetImportError, extract_yolo_archive
from .dependencies import AdminDep, AuthDep, DbDep, SettingsDep, require_same_origin
from .detection_media import (
    IMAGE_TYPES,
    VIDEO_TYPES,
    MediaValidationError,
    SavedUpload,
    resolve_storage_key,
    save_upload,
)
from .errors import InfraError
from .lifecycle_jobs import (
    create_lifecycle_job,
    deploy_model,
    publish_model,
    request_lifecycle_cancel,
    retry_lifecycle_job,
    rollback_deployment,
)
from .lifecycle_models import (
    Dataset,
    DatasetCategory,
    DatasetSample,
    DatasetVersion,
    LifecycleArtifact,
    LifecycleJob,
    LifecycleJobKind,
    LifecycleJobStatus,
    ManagedModelStatus,
    ManagedModelVersion,
    ModelDeployment,
    QualityFinding,
    SampleAnnotation,
    TrainingMetric,
    VersionStatus,
)
from .lifecycle_schemas import (
    AnnotationReplace,
    CategoryOut,
    CategoryUpdate,
    CategoryWrite,
    DatasetCreate,
    DatasetOut,
    DeploymentOut,
    DeploymentWrite,
    ImportResult,
    LifecycleJobCreate,
    LifecycleJobOut,
    ManagedModelOut,
    QualityFindingOut,
    ReviewWrite,
    RevisionRequest,
    SampleOut,
    TrainingMetricOut,
    TrustedModelImport,
    VersionCreate,
    VersionOut,
)
from .lifecycle_service import (
    DEFAULT_CATEGORIES,
    assign_version_splits,
    create_dataset,
    create_dataset_version,
    freeze_version,
    replace_annotations,
    require_dataset_access,
    require_draft,
    require_version_access,
    restore_annotations,
    review_sample,
    run_quality_checks,
    seed_default_categories,
)
from .models import ProjectMembership, UserRole
from .services import record_audit
from .storage import safe_path
from .vision_models import sha256_file

router = APIRouter(tags=["dataset-model-lifecycle"])
ARCHIVE_MAX_BYTES = 2 * 1024**3


def _dataset_out(
    db: DbDep, dataset: Dataset, versions: list[DatasetVersion] | None = None
) -> DatasetOut:
    result = DatasetOut.model_validate(dataset)
    result.versions = [
        VersionOut.model_validate(item)
        for item in (
            versions
            if versions is not None
            else db.scalars(
                select(DatasetVersion)
                .where(DatasetVersion.dataset_id == dataset.id)
                .order_by(DatasetVersion.version_number.desc())
            )
        )
    ]
    return result


def _sample_out(
    db: DbDep, sample: DatasetSample, annotations: list[SampleAnnotation] | None = None
) -> SampleOut:
    result = SampleOut.model_validate(sample)
    result.annotations = [
        annotation
        for annotation in (
            annotations
            if annotations is not None
            else db.scalars(
                select(SampleAnnotation)
                .where(SampleAnnotation.sample_id == sample.id)
                .order_by(SampleAnnotation.created_at, SampleAnnotation.id)
            )
        )
    ]
    return result


@router.get("/dataset-categories", response_model=list[CategoryOut])
def list_categories(db: DbDep, context: AuthDep) -> list[DatasetCategory]:
    del context
    return list(db.scalars(select(DatasetCategory).order_by(DatasetCategory.code).limit(500)))


@router.post(
    "/admin/dataset-categories",
    response_model=CategoryOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_same_origin)],
)
def create_category(payload: CategoryWrite, db: DbDep, context: AdminDep) -> DatasetCategory:
    existing = db.scalar(select(DatasetCategory).where(DatasetCategory.code == payload.code))
    if existing:
        raise InfraError(409, "lifecycle.category_conflict")
    category = DatasetCategory(**payload.model_dump(), created_by=context.user.id)
    db.add(category)
    db.flush()
    record_audit(
        db,
        action="lifecycle.category_create",
        target_type="dataset_category",
        target_id=category.id,
        actor_id=context.user.id,
        after_state={"code": category.code},
    )
    db.commit()
    db.refresh(category)
    return category


@router.patch(
    "/admin/dataset-categories/{category_id}",
    response_model=CategoryOut,
    dependencies=[Depends(require_same_origin)],
)
def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    db: DbDep,
    context: AdminDep,
) -> DatasetCategory:
    category = db.get(DatasetCategory, category_id)
    if category is None:
        raise InfraError(404, "lifecycle.invalid_category")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(category, key, value)
    record_audit(
        db,
        action="lifecycle.category_update",
        target_type="dataset_category",
        target_id=category.id,
        actor_id=context.user.id,
        after_state=payload.model_dump(exclude_none=True),
    )
    db.commit()
    db.refresh(category)
    return category


@router.get("/datasets", response_model=list[DatasetOut])
def list_datasets(db: DbDep, context: AuthDep) -> list[DatasetOut]:
    query = select(Dataset).order_by(Dataset.updated_at.desc())
    if context.user.role != UserRole.ADMIN:
        query = query.join(
            ProjectMembership,
            ProjectMembership.project_id == Dataset.project_id,
        ).where(ProjectMembership.user_id == context.user.id)
    datasets = list(db.scalars(query.limit(200)))
    versions = (
        list(
            db.scalars(
                select(DatasetVersion)
                .where(DatasetVersion.dataset_id.in_([item.id for item in datasets]))
                .order_by(DatasetVersion.version_number.desc())
            )
        )
        if datasets
        else []
    )
    by_dataset: dict[uuid.UUID, list[DatasetVersion]] = {}
    for version in versions:
        by_dataset.setdefault(version.dataset_id, []).append(version)
    return [_dataset_out(db, item, by_dataset.get(item.id, [])) for item in datasets]


@router.get("/datasets/{dataset_id}", response_model=DatasetOut)
def get_dataset(dataset_id: uuid.UUID, db: DbDep, context: AuthDep) -> DatasetOut:
    return _dataset_out(db, require_dataset_access(db, context.user, dataset_id))


@router.post(
    "/admin/datasets/{dataset_id}/archive",
    response_model=DatasetOut,
    dependencies=[Depends(require_same_origin)],
)
def archive_dataset(dataset_id: uuid.UUID, db: DbDep, context: AdminDep) -> DatasetOut:
    dataset = require_dataset_access(db, context.user, dataset_id)
    dataset.status = "archived"
    record_audit(
        db,
        action="lifecycle.dataset_archive",
        target_type="dataset",
        target_id=dataset.id,
        actor_id=context.user.id,
    )
    db.commit()
    return _dataset_out(db, dataset)


@router.post(
    "/admin/datasets",
    response_model=DatasetOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_same_origin)],
)
def create_dataset_endpoint(payload: DatasetCreate, db: DbDep, context: AdminDep) -> DatasetOut:
    dataset, _ = create_dataset(
        db,
        user=context.user,
        project_id=payload.project_id,
        name=payload.name,
        description=payload.description,
    )
    return _dataset_out(db, dataset)


@router.post(
    "/admin/datasets/{dataset_id}/versions",
    response_model=VersionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_same_origin)],
)
def create_version_endpoint(
    dataset_id: uuid.UUID,
    payload: VersionCreate,
    db: DbDep,
    context: AdminDep,
) -> DatasetVersion:
    dataset = require_dataset_access(db, context.user, dataset_id)
    return create_dataset_version(db, user=context.user, dataset=dataset, **payload.model_dump())


@router.post(
    "/admin/dataset-versions/{version_id}/archive",
    response_model=VersionOut,
    dependencies=[Depends(require_same_origin)],
)
def archive_dataset_version(version_id: uuid.UUID, db: DbDep, context: AdminDep) -> DatasetVersion:
    version = require_version_access(db, context.user, version_id)
    active_job = db.scalar(
        select(LifecycleJob.id).where(
            LifecycleJob.version_id == version.id,
            LifecycleJob.status.in_(
                [
                    LifecycleJobStatus.QUEUED,
                    LifecycleJobStatus.RUNNING,
                    LifecycleJobStatus.CANCELLING,
                ]
            ),
        )
    )
    if active_job is not None:
        raise InfraError(409, "lifecycle.version_immutable")
    before = {"status": getattr(version.status, "value", version.status)}
    version.status = VersionStatus.ARCHIVED
    record_audit(
        db,
        action="lifecycle.version_archive",
        target_type="dataset_version",
        target_id=version.id,
        actor_id=context.user.id,
        before_state=before,
        after_state={"status": VersionStatus.ARCHIVED.value},
    )
    db.commit()
    db.refresh(version)
    return version


@router.get("/dataset-versions/{version_id}/samples", response_model=list[SampleOut])
def list_samples(
    version_id: uuid.UUID,
    db: DbDep,
    context: AuthDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SampleOut]:
    require_version_access(db, context.user, version_id)
    samples = list(
        db.scalars(
            select(DatasetSample)
            .where(DatasetSample.version_id == version_id)
            .order_by(DatasetSample.created_at, DatasetSample.id)
            .offset(offset)
            .limit(limit)
        )
    )
    annotations = (
        list(
            db.scalars(
                select(SampleAnnotation)
                .where(SampleAnnotation.sample_id.in_([item.id for item in samples]))
                .order_by(SampleAnnotation.created_at, SampleAnnotation.id)
            )
        )
        if samples
        else []
    )
    by_sample: dict[uuid.UUID, list[SampleAnnotation]] = {}
    for annotation in annotations:
        by_sample.setdefault(annotation.sample_id, []).append(annotation)
    return [_sample_out(db, item, by_sample.get(item.id, [])) for item in samples]


@router.get("/dataset-samples/{sample_id}/content", response_class=FileResponse)
def sample_content(
    sample_id: uuid.UUID, db: DbDep, context: AuthDep, settings: SettingsDep
) -> FileResponse:
    sample = db.get(DatasetSample, sample_id)
    if sample is None:
        raise InfraError(404, "lifecycle.sample_not_found")
    require_version_access(db, context.user, sample.version_id)
    path = safe_path(settings.storage_root, *Path(sample.storage_key).parts)
    if not path.is_file():
        raise InfraError(404, "lifecycle.sample_not_found")
    return FileResponse(path, media_type=sample.mime_type, filename=sample.original_name)


@router.put(
    "/dataset-samples/{sample_id}/annotations",
    response_model=SampleOut,
    dependencies=[Depends(require_same_origin)],
)
def update_annotations(
    sample_id: uuid.UUID,
    payload: AnnotationReplace,
    db: DbDep,
    context: AuthDep,
) -> SampleOut:
    sample = replace_annotations(
        db,
        user=context.user,
        sample_id=sample_id,
        expected_revision=payload.expected_revision,
        annotations=[item.model_dump() for item in payload.annotations],
    )
    return _sample_out(db, sample)


@router.post(
    "/dataset-samples/{sample_id}/review",
    response_model=SampleOut,
    dependencies=[Depends(require_same_origin)],
)
def review_dataset_sample(
    sample_id: uuid.UUID,
    payload: ReviewWrite,
    db: DbDep,
    context: AuthDep,
) -> SampleOut:
    from .lifecycle_models import ReviewStatus

    sample = review_sample(
        db,
        user=context.user,
        sample_id=sample_id,
        expected_revision=payload.expected_revision,
        status=ReviewStatus(payload.status),
    )
    return _sample_out(db, sample)


@router.post(
    "/dataset-samples/{sample_id}/annotations/{operation}",
    response_model=SampleOut,
    dependencies=[Depends(require_same_origin)],
)
def restore_sample_annotations(
    sample_id: uuid.UUID,
    operation: str,
    payload: RevisionRequest,
    db: DbDep,
    context: AuthDep,
) -> SampleOut:
    if operation not in {"undo", "redo"}:
        raise InfraError(404, "http.not_found")
    sample = restore_annotations(
        db,
        user=context.user,
        sample_id=sample_id,
        expected_revision=payload.expected_revision,
        redo=operation == "redo",
    )
    return _sample_out(db, sample)


@router.post(
    "/admin/dataset-versions/{version_id}/import",
    response_model=ImportResult,
    dependencies=[Depends(require_same_origin)],
)
async def import_dataset_archive(
    version_id: uuid.UUID,
    archive: Annotated[UploadFile, File()],
    db: DbDep,
    context: AdminDep,
    settings: SettingsDep,
) -> ImportResult:
    version = require_version_access(db, context.user, version_id)
    require_draft(version)
    if Path(archive.filename or "").suffix.lower() != ".zip":
        raise InfraError(422, "lifecycle.invalid_archive")
    categories = seed_default_categories(db)
    category_by_index = [
        next(category for category in categories if category.code == code)
        for code, *_ in DEFAULT_CATEGORIES
    ]
    token = uuid.uuid4().hex
    archive_path = safe_path(settings.storage_root, "datasets", "staging", f"{token}.zip")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with archive_path.open("xb") as output:
            while chunk := await archive.read(1024 * 1024):
                size += len(chunk)
                if size > ARCHIVE_MAX_BYTES:
                    raise InfraError(413, "lifecycle.archive_too_large")
                output.write(chunk)
        extracted = extract_yolo_archive(
            archive_path,
            staging_root=safe_path(settings.storage_root, "datasets", "staging", "extracted"),
            class_count=len(category_by_index),
        )
        moved: list[Path] = []
        annotation_count = 0
        for item in extracted:
            storage_key = (
                f"datasets/{version.dataset_id}/v{version.version_number}/"
                f"{uuid.uuid4().hex}{item.path.suffix}"
            )
            final_path = safe_path(settings.storage_root, *Path(storage_key).parts)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(item.path, final_path)
            moved.append(final_path)
            sample = DatasetSample(
                version_id=version.id,
                storage_key=storage_key,
                original_name=item.original_name,
                mime_type=item.mime_type,
                byte_size=item.byte_size,
                sha256=item.sha256,
                width=item.width,
                height=item.height,
                created_by=context.user.id,
            )
            db.add(sample)
            db.flush()
            for annotation in item.annotations:
                db.add(
                    SampleAnnotation(
                        sample_id=sample.id,
                        category_id=category_by_index[annotation.class_index].id,
                        cx=annotation.cx,
                        cy=annotation.cy,
                        width=annotation.width,
                        height=annotation.height,
                        created_by=context.user.id,
                    )
                )
            annotation_count += len(item.annotations)
        version.sample_count += len(extracted)
        version.annotation_count += annotation_count
        version.byte_size += sum(item.byte_size for item in extracted)
        version.revision += 1
        split_counts = assign_version_splits(db, version)
        record_audit(
            db,
            action="lifecycle.dataset_import",
            target_type="dataset_version",
            target_id=version.id,
            actor_id=context.user.id,
            after_state={
                "samples": len(extracted),
                "annotations": annotation_count,
                "splits": split_counts,
            },
        )
        db.commit()
        db.refresh(version)
        hash_counts = Counter(item.sha256 for item in extracted)
        return ImportResult(
            imported_samples=len(extracted),
            imported_annotations=annotation_count,
            duplicate_samples=sum(1 for item in extracted if hash_counts[item.sha256] > 1),
            version=VersionOut.model_validate(version),
        )
    except DatasetImportError as exc:
        db.rollback()
        raise InfraError(422, exc.code) from exc
    except Exception:
        db.rollback()
        for path in locals().get("moved", []):
            path.unlink(missing_ok=True)
        raise
    finally:
        archive_path.unlink(missing_ok=True)
        if "extracted" in locals() and extracted:
            shutil.rmtree(extracted[0].path.parent, ignore_errors=True)


@router.post(
    "/admin/dataset-versions/{version_id}/media",
    response_model=ImportResult,
    dependencies=[Depends(require_same_origin)],
)
async def import_dataset_media(
    version_id: uuid.UUID,
    files: Annotated[list[UploadFile], File()],
    db: DbDep,
    context: AdminDep,
    settings: SettingsDep,
) -> ImportResult:
    version = require_version_access(db, context.user, version_id)
    require_draft(version)
    if not files or len(files) > 500:
        raise InfraError(422, "lifecycle.media_batch_limit")
    saved_items: list[tuple[str, SavedUpload]] = []
    committed = False
    try:
        for upload in files:
            suffix = Path(upload.filename or "").suffix.lower()
            media_type = (
                "image" if suffix in IMAGE_TYPES else "video" if suffix in VIDEO_TYPES else ""
            )
            if not media_type:
                raise InfraError(422, "lifecycle.unsupported_media")
            saved = await save_upload(
                upload,
                root=settings.storage_root,
                job_id=uuid.uuid4(),
                media_type=media_type,
                max_bytes=(
                    settings.infrasentinel_image_max_mb * 1024**2
                    if media_type == "image"
                    else settings.infrasentinel_video_max_gb * 1024**3
                ),
                max_video_seconds=settings.infrasentinel_video_max_seconds,
                critical_free_gb=settings.infrasentinel_storage_critical_gb,
            )
            saved_items.append((media_type, saved))
        for media_type, saved in saved_items:
            db.add(
                DatasetSample(
                    version_id=version.id,
                    storage_key=saved.storage_key,
                    original_name=saved.original_name,
                    media_type=media_type,
                    mime_type=saved.mime_type,
                    byte_size=saved.byte_size,
                    sha256=saved.sha256,
                    width=saved.width,
                    height=saved.height,
                    created_by=context.user.id,
                )
            )
        version.sample_count += len(saved_items)
        version.byte_size += sum(item.byte_size for _, item in saved_items)
        version.revision += 1
        db.flush()
        assign_version_splits(db, version)
        record_audit(
            db,
            action="lifecycle.media_import",
            target_type="dataset_version",
            target_id=version.id,
            actor_id=context.user.id,
            after_state={"files": len(saved_items)},
        )
        db.commit()
        committed = True
        db.refresh(version)
        return ImportResult(
            imported_samples=len(saved_items),
            imported_annotations=0,
            duplicate_samples=0,
            version=VersionOut.model_validate(version),
        )
    except MediaValidationError as exc:
        db.rollback()
        raise InfraError(422, exc.code) from exc
    except Exception:
        db.rollback()
        raise
    finally:
        if db.in_transaction():
            db.rollback()
        if not committed:
            for _, saved in saved_items:
                resolve_storage_key(settings.storage_root, saved.storage_key).unlink(
                    missing_ok=True
                )


@router.post(
    "/admin/dataset-versions/{version_id}/quality",
    response_model=list[QualityFindingOut],
    dependencies=[Depends(require_same_origin)],
)
def quality_check(version_id: uuid.UUID, db: DbDep, context: AdminDep) -> list[QualityFinding]:
    version = require_version_access(db, context.user, version_id)
    return run_quality_checks(db, version)


@router.get("/dataset-versions/{version_id}/quality", response_model=list[QualityFindingOut])
def list_quality_findings(
    version_id: uuid.UUID, db: DbDep, context: AuthDep
) -> list[QualityFinding]:
    require_version_access(db, context.user, version_id)
    return list(
        db.scalars(
            select(QualityFinding)
            .where(QualityFinding.version_id == version_id)
            .order_by(QualityFinding.created_at.desc())
            .limit(1000)
        )
    )


@router.post(
    "/admin/quality-findings/{finding_id}/resolve",
    response_model=QualityFindingOut,
    dependencies=[Depends(require_same_origin)],
)
def resolve_quality_finding(finding_id: uuid.UUID, db: DbDep, context: AdminDep) -> QualityFinding:
    finding = db.get(QualityFinding, finding_id)
    if finding is None:
        raise InfraError(404, "http.not_found")
    require_version_access(db, context.user, finding.version_id)
    if not finding.resolved:
        finding.resolved = True
        finding.resolved_by = context.user.id
        finding.resolved_at = utc_now()
        record_audit(
            db,
            action="lifecycle.quality_finding_resolve",
            target_type="quality_finding",
            target_id=finding.id,
            actor_id=context.user.id,
            after_state={"resolved": True},
        )
        db.commit()
        db.refresh(finding)
    return finding


@router.post(
    "/admin/dataset-versions/{version_id}/freeze",
    response_model=VersionOut,
    dependencies=[Depends(require_same_origin)],
)
def freeze_dataset_version(version_id: uuid.UUID, db: DbDep, context: AdminDep) -> DatasetVersion:
    version = require_version_access(db, context.user, version_id)
    return freeze_version(db, user=context.user, version=version)


@router.get("/lifecycle-jobs", response_model=list[LifecycleJobOut])
def list_lifecycle_jobs(db: DbDep, context: AuthDep) -> list[LifecycleJob]:
    query = select(LifecycleJob).order_by(LifecycleJob.queued_at.desc())
    if context.user.role != UserRole.ADMIN:
        query = query.join(
            ProjectMembership,
            ProjectMembership.project_id == LifecycleJob.project_id,
        ).where(ProjectMembership.user_id == context.user.id)
    return list(db.scalars(query.limit(200)))


@router.get("/lifecycle-jobs/{job_id}", response_model=LifecycleJobOut)
def get_lifecycle_job(job_id: uuid.UUID, db: DbDep, context: AuthDep) -> LifecycleJob:
    job = db.get(LifecycleJob, job_id)
    if job is None:
        raise InfraError(404, "lifecycle.job_not_found")
    from .detection_service import require_project_access

    require_project_access(db, context.user, job.project_id)
    return job


@router.get("/lifecycle-jobs/{job_id}/metrics", response_model=list[TrainingMetricOut])
def lifecycle_job_metrics(job_id: uuid.UUID, db: DbDep, context: AuthDep) -> list[TrainingMetric]:
    get_lifecycle_job(job_id, db, context)
    return list(
        db.scalars(
            select(TrainingMetric)
            .where(TrainingMetric.job_id == job_id)
            .order_by(TrainingMetric.epoch)
            .limit(1000)
        )
    )


@router.get("/lifecycle-jobs/{job_id}/log", response_class=PlainTextResponse)
def lifecycle_job_log(job_id: uuid.UUID, db: DbDep, context: AuthDep) -> str:
    job = get_lifecycle_job(job_id, db, context)
    lines = [f"status={job.status}", f"progress={job.progress}"]
    if job.progress_detail:
        lines.append(f"detail={job.progress_detail}")
    if job.error_code:
        lines.append(f"error={job.error_code}: {job.error_detail or ''}")
    return "\n".join(lines)[:100_000]


@router.get("/lifecycle-artifacts/{artifact_id}", response_class=FileResponse)
def download_lifecycle_artifact(
    artifact_id: uuid.UUID,
    db: DbDep,
    context: AuthDep,
    settings: SettingsDep,
) -> FileResponse:
    artifact = db.get(LifecycleArtifact, artifact_id)
    if artifact is None:
        raise InfraError(404, "http.not_found")
    if artifact.job_id is not None:
        get_lifecycle_job(artifact.job_id, db, context)
    else:
        model = db.scalar(
            select(ManagedModelVersion).where(ManagedModelVersion.weight_artifact_id == artifact.id)
        )
        if model is None or (
            context.user.role != UserRole.ADMIN and model.status != ManagedModelStatus.PUBLISHED
        ):
            raise InfraError(404, "http.not_found")
    path = safe_path(settings.storage_root, *Path(artifact.storage_key).parts)
    if not path.is_file():
        raise InfraError(404, "http.not_found")
    return FileResponse(path, media_type=artifact.mime_type, filename=path.name)


@router.post(
    "/admin/lifecycle-jobs",
    response_model=LifecycleJobOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_same_origin)],
)
def create_lifecycle_job_endpoint(
    payload: LifecycleJobCreate, db: DbDep, context: AdminDep
) -> LifecycleJob:
    version = require_version_access(db, context.user, payload.version_id)
    return create_lifecycle_job(
        db,
        user=context.user,
        version=version,
        kind=LifecycleJobKind(payload.kind),
        config=payload.config,
    )


@router.post(
    "/admin/lifecycle-jobs/{job_id}/cancel",
    response_model=LifecycleJobOut,
    dependencies=[Depends(require_same_origin)],
)
def cancel_lifecycle_job(job_id: uuid.UUID, db: DbDep, context: AdminDep) -> LifecycleJob:
    job = db.get(LifecycleJob, job_id)
    if job is None:
        raise InfraError(404, "lifecycle.job_not_found")
    return request_lifecycle_cancel(db, user=context.user, job=job)


@router.post(
    "/admin/lifecycle-jobs/{job_id}/retry",
    response_model=LifecycleJobOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_same_origin)],
)
def retry_lifecycle_job_endpoint(job_id: uuid.UUID, db: DbDep, context: AdminDep) -> LifecycleJob:
    job = db.get(LifecycleJob, job_id)
    if job is None:
        raise InfraError(404, "lifecycle.job_not_found")
    return retry_lifecycle_job(db, user=context.user, job=job)


@router.get("/managed-models", response_model=list[ManagedModelOut])
def list_managed_models(db: DbDep, context: AuthDep) -> list[ManagedModelVersion]:
    query = select(ManagedModelVersion).order_by(
        ManagedModelVersion.code, ManagedModelVersion.version_number.desc()
    )
    if context.user.role != UserRole.ADMIN:
        query = query.where(ManagedModelVersion.status == ManagedModelStatus.PUBLISHED)
    return list(db.scalars(query.limit(500)))


@router.get("/managed-models/{model_id}", response_model=ManagedModelOut)
def get_managed_model(model_id: uuid.UUID, db: DbDep, context: AuthDep) -> ManagedModelVersion:
    model = db.get(ManagedModelVersion, model_id)
    if model is None:
        raise InfraError(404, "lifecycle.model_not_found")
    if context.user.role != UserRole.ADMIN and model.status != ManagedModelStatus.PUBLISHED:
        raise InfraError(404, "lifecycle.model_not_found")
    return model


@router.post(
    "/admin/managed-models/import",
    response_model=ManagedModelOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_same_origin)],
)
def import_trusted_model(
    payload: TrustedModelImport,
    db: DbDep,
    context: AdminDep,
    settings: SettingsDep,
) -> ManagedModelVersion:
    version = require_version_access(db, context.user, payload.version_id)
    if version.status != VersionStatus.FROZEN:
        raise InfraError(409, "lifecycle.version_not_trainable")
    try:
        path = safe_path(settings.storage_root, *Path(payload.storage_key).parts)
    except ValueError as exc:
        raise InfraError(422, "lifecycle.artifact_integrity_failed") from exc
    if path.suffix.lower() != ".pt" or not path.is_file():
        raise InfraError(409, "lifecycle.artifact_integrity_failed")
    digest = sha256_file(path)
    if digest != payload.sha256.lower():
        raise InfraError(409, "lifecycle.artifact_integrity_failed")
    artifact = db.scalar(
        select(LifecycleArtifact).where(LifecycleArtifact.storage_key == payload.storage_key)
    )
    if artifact is None:
        artifact = LifecycleArtifact(
            job_id=None,
            kind="weights",
            storage_key=payload.storage_key,
            mime_type="application/octet-stream",
            byte_size=path.stat().st_size,
            sha256=digest,
        )
        db.add(artifact)
        db.flush()
    elif artifact.sha256 != digest:
        raise InfraError(409, "lifecycle.artifact_integrity_failed")
    next_version = (
        db.scalar(
            select(func.max(ManagedModelVersion.version_number)).where(
                ManagedModelVersion.code == payload.code
            )
        )
        or 0
    ) + 1
    model = ManagedModelVersion(
        code=payload.code,
        version_number=next_version,
        scene=payload.scene,
        size_variant=payload.size_variant,
        dataset_version_id=version.id,
        weight_artifact_id=artifact.id,
        model_card=payload.model_card,
        class_map_json=payload.class_map,
        metrics_json=payload.metrics,
        created_by=context.user.id,
    )
    db.add(model)
    db.flush()
    record_audit(
        db,
        action="lifecycle.model_import",
        target_type="managed_model_version",
        target_id=model.id,
        actor_id=context.user.id,
        after_state={"storage_key": artifact.storage_key, "sha256": digest},
    )
    db.commit()
    db.refresh(model)
    return model


@router.post(
    "/admin/managed-models/{model_id}/archive",
    response_model=ManagedModelOut,
    dependencies=[Depends(require_same_origin)],
)
def archive_managed_model(model_id: uuid.UUID, db: DbDep, context: AdminDep) -> ManagedModelVersion:
    model = db.get(ManagedModelVersion, model_id)
    if model is None:
        raise InfraError(404, "lifecycle.model_not_found")
    active = db.scalar(
        select(ModelDeployment.id).where(ModelDeployment.model_version_id == model.id)
    )
    if active:
        raise InfraError(409, "lifecycle.model_deployed")
    model.status = ManagedModelStatus.ARCHIVED
    record_audit(
        db,
        action="lifecycle.model_archive",
        target_type="managed_model_version",
        target_id=model.id,
        actor_id=context.user.id,
    )
    db.commit()
    db.refresh(model)
    return model


@router.post(
    "/admin/managed-models/{model_id}/publish",
    response_model=ManagedModelOut,
    dependencies=[Depends(require_same_origin)],
)
def publish_managed_model(
    model_id: uuid.UUID, db: DbDep, context: AdminDep, settings: SettingsDep
) -> ManagedModelVersion:
    model = db.get(ManagedModelVersion, model_id)
    if model is None:
        raise InfraError(404, "lifecycle.model_not_found")
    return publish_model(db, user=context.user, model=model, storage_root=settings.storage_root)


@router.post(
    "/admin/managed-models/{model_id}/deploy",
    response_model=DeploymentOut,
    dependencies=[Depends(require_same_origin)],
)
def deploy_managed_model(
    model_id: uuid.UUID,
    payload: DeploymentWrite,
    db: DbDep,
    context: AdminDep,
) -> ModelDeployment:
    model = db.get(ManagedModelVersion, model_id)
    if model is None:
        raise InfraError(404, "lifecycle.model_not_found")
    return deploy_model(
        db,
        user=context.user,
        project_id=payload.project_id,
        model=model,
        rollout_percent=payload.rollout_percent,
    )


@router.get("/model-deployments", response_model=list[DeploymentOut])
def list_model_deployments(db: DbDep, context: AuthDep) -> list[ModelDeployment]:
    query = select(ModelDeployment).order_by(ModelDeployment.updated_at.desc())
    if context.user.role != UserRole.ADMIN:
        query = query.join(
            ProjectMembership,
            ProjectMembership.project_id == ModelDeployment.project_id,
        ).where(ProjectMembership.user_id == context.user.id)
    return list(db.scalars(query.limit(500)))


@router.post(
    "/admin/model-deployments/{deployment_id}/rollback",
    response_model=DeploymentOut,
    dependencies=[Depends(require_same_origin)],
)
def rollback_model_deployment(
    deployment_id: uuid.UUID, db: DbDep, context: AdminDep
) -> ModelDeployment:
    deployment = db.get(ModelDeployment, deployment_id)
    if deployment is None:
        raise InfraError(404, "lifecycle.deployment_not_found")
    return rollback_deployment(db, user=context.user, deployment=deployment)
