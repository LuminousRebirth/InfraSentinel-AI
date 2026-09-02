# v1.2 Task Ledger: vision-detection

Tasks are dependency-ordered. The user authorized continuous execution through final review on 2026-09-02. Check a task only after its verification passes.

- [x] Task 1: Approve and freeze the v1.2 contracts
  - Acceptance: specification state, plan, task ledger, data/API boundaries, deferred scope, and authorized continuous workflow are recorded.
  - Verify: document review; `git diff --check`.
  - Files: `SPEC-vision-detection.md`, `tasks/plan.md`, `tasks/todo.md`, `AGENT.md`

- [x] Task 2: Add vision configuration and the one approved dependency
  - Acceptance: bounded upload/worker/lease/OBS/model path settings validate safely; only `python-multipart` is added.
  - Verify: focused config tests; environment resolution; `pip check`.
  - Files: `environment.yml`, `.env.example`, `src/infrasentinel/config.py`, `tests/test_config.py`

- [x] Task 3: Define v1.2 database models
  - Acceptance: model deployment, job, media, observation, and metric models encode approved enums, ownership, project, retry, lease, indexes, and constraints.
  - Verify: metadata/model tests.
  - Files: `src/infrasentinel/detection_models.py`, `src/infrasentinel/models.py`, `tests/test_detection_models.py`

- [x] Task 4: Add and round-trip the v1.2 migration
  - Acceptance: one reversible migration creates only v1.2 objects and protects valid state/relationship constraints.
  - Verify: Alembic upgrade/downgrade/upgrade and focused PostgreSQL assertions.
  - Files: `alembic/env.py`, `alembic/versions/20260902_0003_vision_detection.py`, `tests/test_detection_migration.py`

- [x] Task 5: Implement model synchronization and shared inference runtime
  - Acceptance: both scenes sync by external path/checksum, unavailable assets are safe, backend fallback is visible, annotation is deterministic, and the old CLI schema remains compatible.
  - Verify: model/runtime/legacy tests and real idempotent sync.
  - Files: `src/infrasentinel/vision_models.py`, `src/infrasentinel/cli.py`, `src/vision_inspection/infer.py`, `tests/test_vision_runtime.py`, `tests/test_infer.py`

- [x] Task 6: Implement safe media storage and validation
  - Acceptance: bounded chunked writes, SHA-256, UUID keys, decoder/FFprobe checks, atomic original/output finalization, and safe authorized resolution work.
  - Verify: synthetic image/video, oversize, corrupt, traversal, and rollback tests.
  - Files: `src/infrasentinel/detection_media.py`, `src/infrasentinel/storage.py`, `tests/test_detection_media.py`

- [x] Task 7: Implement durable job lifecycle and authorization
  - Acceptance: create/claim/heartbeat/complete/fail/cancel/retry/reclaim transitions are conditional and audited; owner/project/admin access matches the spec.
  - Verify: unit and PostgreSQL concurrency/access tests.
  - Files: `src/infrasentinel/detection_service.py`, `src/infrasentinel/dependencies.py`, `tests/test_detection_service.py`

- [x] Task 8: Implement streamed upload and record APIs
  - Acceptance: image batch/video uploads create independent durable jobs; list/detail/media/cancel/retry endpoints are bounded, localized, and authorized.
  - Verify: API tests with valid/invalid generated media and role/project matrix.
  - Files: `src/infrasentinel/detection_api.py`, `src/infrasentinel/detection_schemas.py`, `src/infrasentinel/main.py`, `tests/test_detection_api.py`

- [x] Task 9: Implement image and video workers
  - Acceptance: no inference runs in Web requests; workers persist progress, observations, metrics, annotated outputs, cancellation, failures, and lease recovery.
  - Verify: fake-runtime worker tests plus real short image/video detection.
  - Files: `src/infrasentinel/worker.py`, `src/infrasentinel/detection_service.py`, `src/infrasentinel/detection_media.py`, `tests/test_detection_worker.py`

- [x] Task 10: Implement the single OBS lifecycle and preview
  - Acceptance: one-session exclusion, fake/real capture, dynamic parameters, durable observations/keyframes, Redis TTL preview, reconnect state, stop, and device loss work.
  - Verify: fake capture/API/Redis tests and real OBS check when available.
  - Files: `src/infrasentinel/worker.py`, `src/infrasentinel/detection_api.py`, `src/infrasentinel/detection_service.py`, `tests/test_detection_obs.py`

- [x] Task 11: Integrate two workers with Windows lifecycle scripts
  - Acceptance: start/stop tracks exactly two worker processes and the API; stale PID recovery is safe; health shows queue/worker/model status without exposing paths.
  - Verify: PowerShell parse, start/health/stop/restart, port and PID checks.
  - Files: `scripts/start.ps1`, `scripts/stop.ps1`, `scripts/health.ps1`, `src/infrasentinel/health.py`, `tests/test_health.py`

- [x] Task 12: Add the typed frontend detection foundation
  - Acceptance: typed contracts/client helpers, routes/navigation, status labels, and full zh-CN/en key parity exist.
  - Verify: locale/client/route tests and strict TypeScript build.
  - Files: `frontend/src/api/detections.ts`, `frontend/src/i18n/index.ts`, `frontend/src/App.tsx`, `frontend/src/test/detection-routing.test.tsx`

- [x] Task 13: Build create, history, detail, and OBS pages
  - Acceptance: upload/progress/cancel/retry, annotated media, object/timeline details, live/stale OBS states, keyboard use, and responsive industrial styling match the spec.
  - Verify: component tests, lint/build, and manual 360px/1280px bilingual browser review.
  - Files: `frontend/src/pages/DetectionPage.tsx`, `frontend/src/pages/DetectionHistoryPage.tsx`, `frontend/src/pages/DetectionDetailPage.tsx`, `frontend/src/styles/detection.css`, `frontend/src/test/detections.test.tsx`

- [x] Task 14: Run integrated vision acceptance
  - Acceptance: migrations, full regression, real model sync, image/video jobs, worker concurrency/recovery, access isolation, live routes, CUDA, and OBS availability are evidenced accurately.
  - Verify: full Python/npm/lint/build/config/PowerShell suite and recorded live acceptance.
  - Files: `tests/test_detection_acceptance.py`, `scripts/verify_environment.py`, `SPEC-vision-detection.md`

- [x] Task 15: Review, fix, document, and prepare final user review
  - Acceptance: no unresolved critical/required finding; success criteria/task evidence/README/AGENT are current; secrets/media/weights remain excluded; no commit/tag/push occurs before final user approval.
  - Verify: multi-axis code review, full rerun, `git diff --check`, secret/large-file scan, live readiness.
  - Files: `README.md`, `AGENT.md`, `SPEC-vision-detection.md`, `tasks/plan.md`, `tasks/todo.md`
