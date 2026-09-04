# Spec: dataset-model-lifecycle (v1.4)

## Status and Approved Defaults

- Module id: `dataset-model-lifecycle`; depends on `platform-foundation` and `vision-detection`.
- Existing project defaults remain authoritative; implementation continues without new questions.
- Dataset, video, label, weight and training artifacts stay under configured local storage and are Git-ignored.
- Administrators manage categories, datasets, training, evaluation and publication. Enabled project members may view project datasets and annotate assigned-project draft samples; publication remains admin-only.
- Dataset versions are mutable only while `draft`; `frozen`, `training`, `published` and `archived` versions are immutable. Training always references a frozen version.
- Default deterministic split is 80/10/10 by content hash, with identical hashes forced into one split to prevent leakage.
- Existing categories seed as `CK`, `PL`, `SG`, `SL`, `TL`, `ZW`, `helmet`, `no_helmet`. Category deletion is not implemented; administrators enable/disable instead.
- Training uses the existing Ultralytics/YOLO runtime and one PostgreSQL-leased GPU worker. No Celery, new SDK, annotation library or experiment tracker is added.
- Real long-running GPU training is optional during local acceptance because no approved training dataset is currently available and storage has about 11.86 GB free. A fake runner verifies the complete lifecycle; real training remains user-triggered.
- YOLO26 base weights must already exist locally or be a trusted platform-produced artifact. The worker never downloads weights implicitly and never loads an untrusted uploaded pickle in the API process.

## Objective

Provide an auditable Web lifecycle from raw media to a published model:

1. create project-scoped datasets and immutable versions;
2. safely import images, videos and YOLO ZIP archives;
3. extract selected video frames and annotate normalized boxes in the browser;
4. detect corrupt media, invalid/empty boxes, duplicates, class imbalance and split leakage;
5. freeze a validated version and export a YOLO layout;
6. queue, monitor, cancel and retry training/evaluation jobs;
7. retain metrics and artifacts, approve publication, deploy by project and roll back.

## Minimal Architecture

- PostgreSQL stores category metadata, dataset/version/sample/annotation revisions, quality findings, jobs, metrics, artifacts, governed models and deployments.
- Local storage stores originals, extracted frames, YOLO exports, training runs, plots and weights through generated safe keys.
- API requests validate metadata and stream bounded files; archive inspection rejects traversal, links, entry bombs and excessive expansion before extraction.
- One `model_lifecycle_worker` claims training/evaluation/frame-extraction jobs with leases. Ultralytics is imported only inside the worker runner.
- Dataset validation and YOLO export are deterministic services; they do not require GPU or cloud APIs.

## Data Model

- `dataset_categories`: stable code, bilingual names, enabled flag, color and audit timestamps.
- `datasets`: project, name, description, owner, status and timestamps.
- `dataset_versions`: dataset, semantic integer version, state, source, split ratios, sample/annotation/byte counts, frozen timestamp and optimistic version.
- `dataset_samples`: version, safe media key/type/hash/dimensions, source name, split, extraction timestamp/frame, review state and duplicate group.
- `sample_annotations`: sample/category, normalized YOLO center/size, revision, creator/reviewer and timestamps.
- `dataset_changes`: append-only before/after operation history for undo/redo and audit.
- `quality_findings`: version/sample, code, severity, message, repair suggestion and resolution state.
- `lifecycle_jobs`: `extract|validate|train|evaluate|export`, state/progress/lease/attempt/config/error/log key and cancel flag.
- `training_metrics`: job, epoch and bounded loss/mAP/precision/recall/F1 values.
- `model_versions`: model family/size, source training job/version, trusted weight key/hash, model card, metrics, `draft|evaluating|published|archived`, approver and published timestamp.
- `model_deployments`: project plus active model version, rollout percentage, previous version and timestamps; one active deployment per project/scene.

## Import, Annotation and Quality Rules

- Accept JPEG/PNG/WebP images, bounded common videos and ZIP archives containing images plus YOLO `.txt` labels and optional `data.yaml`.
- Archive limits: 20,000 entries, 2 GB compressed upload, 10 GB declared extraction, 100:1 per-entry expansion, no absolute/traversal paths, device files, links or nested archives.
- Hash every stored file while streaming. Decode images/videos before committing database rows; partial files are removed on failure.
- YOLO labels contain exactly five finite numbers: known class index and normalized `cx cy width height`; width/height must be positive and the box must remain within `[0,1]` after conversion.
- Annotation updates use sample revision for optimistic concurrency and append a reversible change. Review is distinct from annotation authoring.
- Quality validation emits stable finding codes for corrupt media, empty annotation, invalid/out-of-bounds box, duplicate hash, class imbalance and cross-split duplicate leakage.
- Export generates `images/{train,val,test}`, `labels/{train,val,test}` and `data.yaml` in a versioned artifact; existing versions are never overwritten.

## Training, Evaluation and Publication

- Training config is bounded: epochs 1-1000, batch 1-256 or auto, image size 320-1536, learning rate `(0,1]`, device from the existing policy and a named local YOLO26 base artifact.
- Jobs are asynchronous, leased, cancellable between epochs/stages, retryable and store readable safe errors. Logs are bounded and never contain local secrets.
- Runner writes only under its generated run directory. The worker records `best.pt`, `last.pt`, CSV/plots and hashes only after files exist and remain inside that directory.
- Evaluation validates a trusted model against a frozen labeled test split and stores overall/per-class metrics, confusion matrix, PR curve and bounded example predictions when produced.
- Publication requires admin action, completed evaluation, model card and an existing hashed weight artifact. It never silently replaces all projects.
- Deployment is explicit per project with rollout 0-100. Rollback atomically restores `previous_model_version_id` and records audit history.
- The existing detection model registry remains the runtime compatibility boundary; publication synchronizes a governed model into it only after approval.

## API Surface

- Categories: admin list/create/update; enabled users read.
- Datasets/versions: admin create/freeze/archive/import/export; project members list/detail.
- Samples/annotations: authorized project member list/media/update/review with revision checks.
- Quality: validate, list findings and resolve supported findings.
- Jobs: create/list/detail/cancel/retry/log/metrics; training/evaluation create is admin-only.
- Models: list/detail/import trusted artifact metadata, evaluate, publish, archive, deploy and rollback; all mutation is admin-only.
- Every list is filtered and bounded; every mutation uses existing cookie auth and same-origin protection.

## Frontend

- “数据集” presents dataset/version state, counts, quality findings, import/freeze/export and a sample workspace.
- Annotation workspace uses a native canvas/SVG overlay for box draw, select, resize, class change, delete, undo/redo and review; no annotation UI dependency.
- “模型管理” presents lifecycle jobs, metrics, artifacts, model cards, publication state and project deployments/rollback.
- Status and quality use text plus color, Chinese/English resources stay in parity, keyboard controls and narrow screens remain usable.

## Security and Performance Boundaries

- Never trust archive names, MIME, YAML, labels, training output paths or Ultralytics result objects.
- Never load uploaded `.pt` in API. Only admin-approved local paths or platform-produced hashed artifacts reach the runner.
- Stream uploads/exports; bound archive entries, extracted bytes, labels, samples, logs, metrics and API page sizes.
- Keep transactions short; file writes stage before metadata commit and clean up on failure.
- Do not delete existing datasets, weights or runs. Archival is metadata-only in v1.4; 30-day deletion arrives with operations retention controls.

## Verification

- Migration upgrade/downgrade structure and constraints.
- Archive traversal/bomb/corrupt media/YOLO label tests.
- Deterministic split, duplicate/leakage, annotation revision/undo/review and quality tests.
- Fake extraction/train/evaluate runner lifecycle including lease, cancel, retry, artifact containment and metrics.
- Publication/deployment/rollback authorization and audit tests.
- Frontend component, canvas behavior, i18n, lint and build tests.
- Full v1.0-v1.3 regression, real database migration, no-secret/large-file scan and branch-only push.

## Deferred

- Distributed/multi-GPU training, hyperparameter search, external experiment tracking, model registry service, automatic base-weight download, active learning, segmentation/polygon labels, physical deletion and cross-site artifact replication.

## Success Criteria

- [ ] Safe project/versioned dataset import, annotation, validation, freeze and YOLO export work end to end.
- [ ] Training/evaluation jobs expose durable progress/cancel/retry/logs/metrics through a fake runner and are ready for real local YOLO26 execution.
- [ ] Trusted artifacts can be evaluated, approved, deployed per project and rolled back with audit history.
- [ ] Bilingual dataset/model interfaces pass component, responsive and accessibility checks.
- [ ] Full regression and five-axis review pass; only the development branch is pushed.

## Open Questions

None blocking. Real training duration and quality acceptance wait for an approved local dataset/base weight and sufficient disk capacity.
