# v1.4 Implementation Plan: dataset-model-lifecycle

Implement `SPEC-dataset-model-lifecycle.md` on `codex/v1.2-vision-detection`. No main merge or tag occurs.

## Slice 1 — Schema and safe imports

1. Add categories, datasets, versions, samples, annotations, changes, findings, jobs, metrics, model versions and deployments.
2. Add one reversible constrained migration and seed eight categories.
3. Implement streaming image/video/ZIP import with archive and YOLO-label validation.

Checkpoint: migration/model/seed tests and malicious archive fixtures pass; staged failures leave no files or rows.

## Slice 2 — Versioning, annotation and quality

1. Add project/version authorization and immutable-state rules.
2. Add annotation revision, review and reversible change services.
3. Add deterministic split, duplicate/leakage and quality validation.
4. Add contained YOLO export.

Checkpoint: concurrency, undo, split stability, quality codes and repeat export tests pass.

## Slice 3 — Lifecycle jobs and governed models

1. Add leased extract/train/evaluate/export job orchestration and a single worker.
2. Add fake runner plus bounded local Ultralytics runner boundary.
3. Record metrics/artifacts/model cards; implement publish/archive/deploy/rollback.
4. Synchronize only approved trusted weights into the detection registry.

Checkpoint: fake lifecycle, cancellation/retry, artifact containment, authorization and audit pass.

## Slice 4 — APIs and Web workflows

1. Add bounded category/dataset/version/sample/annotation/quality/job/model APIs.
2. Build bilingual dataset list/detail/import/version/quality views.
3. Build native annotation workspace with keyboard and revision feedback.
4. Build training/evaluation/model publication/deployment views.

Checkpoint: API role matrix, components, i18n, lint/build and responsive browser review pass.

## Slice 5 — Acceptance and branch archive

1. Run real PostgreSQL migration/seed plus tiny image/ZIP import/export.
2. Run fake extraction/train/evaluate/publish/deploy/rollback end to end.
3. Run full regression, scripts, scans and five-axis review.
4. Commit and push only `codex/v1.2-vision-detection`.

## Controls

- Preserve all existing datasets, weights, media and runs; archive rather than delete.
- Do not download weights or start long real training automatically.
- Keep storage limits and current 11.86 GB capacity warning visible.
- No new dependency without a blocking need and explicit approval.
