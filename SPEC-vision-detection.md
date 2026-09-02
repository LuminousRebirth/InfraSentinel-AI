# Spec: vision-detection (v1.2)

## Status

- Module id: `vision-detection`
- Milestone: `v1.2`
- Depends on: `platform-foundation` (`v1.0`), `identity-access` (`v1.1`)
- State: approved by the user on 2026-09-02; implementation authorized through final review
- Scope source: `PROJECT_REQUIREMENTS.md`, `CAPABILITY_MAP.md`, the existing `src/vision_inspection` inference code, and the approved 2026-09-01 defaults

## Assumptions

1. v1.2 is one cohesive capability: image, video, and one OBS virtual-camera stream share the same model registry, inference adapter, durable job lifecycle, project authorization, media storage, and result schema.
2. Existing trained pipeline and PPE `.pt`, ONNX, and TensorRT files under `E:\python_code\yolo` are read-only local acceptance assets. They are referenced through environment configuration and are never copied, modified, downloaded, or committed.
3. A detection belongs to an active project. Until rich site/asset/OBS point management arrives in v1.5, the project itself is the only selectable point and its id is stored as the provisional point boundary.
4. Administrators can access every detection record. Normal users can create and view only their own jobs in assigned active projects; project membership alone does not expose another user's records.
5. Every image and video request is a durable asynchronous job. OBS is a single durable live session which occupies one worker slot and produces durable snapshots/observations while its preview frames remain ephemeral.
6. TensorRT is preferred when a configured compatible engine exists, then PyTorch `.pt` is used as fallback. ONNX is registered as metadata but is not a third runtime path in v1.2.
7. LLM analysis, rule-based severity, alert creation, cross-frame event merging, reports, retention deletion, model training/publishing, and Electron offline sync remain in v1.3-v1.6. v1.2 preserves the raw observations and metadata those modules need.
8. No cloud-model API is required for v1.2. Missing or invalid YOLO assets mark only the affected model unavailable and do not prevent the application from starting.

## Objective

Deliver an operable Web detection workflow on the approved Windows + RTX 4060 host:

- register the existing pipeline-defect and PPE models without importing their binary files;
- upload one or many images and one video with strict streamed validation;
- start and stop one server-side OBS virtual-camera session;
- execute durable jobs outside Web requests with two configurable worker processes;
- expose progress, cancellation, retry, readable failures, performance metrics, and crash recovery;
- persist originals, annotated outputs, detections, frame timestamps, parameters, model identity, checksums, ownership, and audit events;
- show bilingual create, queue, live preview, history, and detail screens under the existing project/role guards;
- keep the existing `vision-inspection infer` CLI and its result fields compatible.

Success means an authorized user can select a project and available model, complete image and video detections, run a single OBS preview, inspect durable annotated results, cancel or retry work, and never gain access to another user's records.

## Out of Scope

- Cloud LLM calls, object-level narrative analysis, rules, severity decisions, alerts, alert deduplication, or merged events.
- Dataset import, annotation, training, evaluation, model publishing, model rollback, or a general model-management UI.
- Multiple simultaneous cameras, RTSP/HTTP streams, browser camera capture, or desktop offline inference/sync.
- Report generation, bulk export, full-text search, record deletion/quarantine, dashboards, or capacity analytics.
- TensorRT engine building, automatic model conversion, weight downloads, or moving legacy datasets/weights into this repository.
- Audio analysis. Annotated video may omit source audio; this must be disclosed in the UI.

## Tech Stack and Minimal Design

- Reuse Python 3.11, FastAPI, SQLAlchemy/Alembic, PostgreSQL, Redis, OpenCV, FFmpeg, Ultralytics, PyTorch/CUDA, React, TypeScript, and native browser APIs already present.
- Add only `python-multipart` for FastAPI streamed multipart uploads. Do not add Celery, RQ, Dramatiq, a WebSocket library, an API client, a media framework, or a component suite.
- PostgreSQL is the durable queue. Independent Windows worker processes claim work with `FOR UPDATE SKIP LOCKED`; a lease timestamp makes abandoned work reclaimable after a crash.
- `scripts/start.ps1` starts two independent worker processes by default. Windows process spawning is used so CUDA state is never inherited through `fork`.
- Redis holds only short-lived OBS preview JPEGs and performance samples. Durable state always remains in PostgreSQL and the storage root; Redis loss may interrupt preview but cannot lose a completed record.
- FastAPI's native WebSocket support forwards the latest OBS preview/status. Reconnection obtains current durable session state before resuming ephemeral frames.
- FFprobe validates video metadata and FFmpeg/OpenCV produce browser-playable H.264 MP4 output. No user-controlled shell string is constructed; subprocess arguments are passed as a list.

## Commands

```powershell
conda activate infrasentinel

# Dependencies and migration
conda env update -n infrasentinel -f environment.yml --prune
python -m alembic upgrade head
python -m alembic downgrade -1
python -m alembic upgrade head

# Register configured local model assets without copying them
python -m infrasentinel.cli sync-vision-models

# Worker and integrated application
python -m infrasentinel.worker
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
powershell -ExecutionPolicy Bypass -File scripts/health.ps1
powershell -ExecutionPolicy Bypass -File scripts/stop.ps1

# Verification
python -m pytest -q --basetemp runtime/pytest-v1.2 -p no:cacheprovider
ruff check src tests scripts/verify_environment.py alembic
Push-Location frontend
npm run test -- --run
npm run lint
npm run build
Pop-Location
```

## Project Structure

```text
src/infrasentinel/
  detection_api.py       # upload, job, record, media, and OBS endpoints
  detection_models.py    # v1.2 SQLAlchemy enums/tables
  detection_schemas.py   # typed API contracts
  detection_service.py   # authorization, lifecycle, storage, audit transactions
  worker.py              # PostgreSQL claim loop and image/video/OBS execution

src/vision_inspection/
  infer.py               # compatible public CLI facade
  runtime.py             # shared loaded-model adapter and annotation primitives

frontend/src/
  pages/DetectionPage.tsx
  pages/DetectionHistoryPage.tsx
  pages/DetectionDetailPage.tsx
  api/detections.ts

tests/
  test_detection_models.py
  test_detection_api.py
  test_detection_worker.py
  test_detection_acceptance.py
```

Files may be combined when that is clearer. There is one concrete worker and one concrete model adapter; generic provider, repository, event-bus, or workflow interfaces are prohibited until a second implementation exists.

## Configuration and Model Registration

The following environment values contain local paths or operational defaults, never model bytes:

- `INFRASENTINEL_PIPELINE_PT`, `INFRASENTINEL_PIPELINE_ENGINE`
- `INFRASENTINEL_PPE_PT`, `INFRASENTINEL_PPE_ENGINE`
- `INFRASENTINEL_VISION_DEVICE=auto`
- `INFRASENTINEL_VISION_WORKERS=2`
- `INFRASENTINEL_OBS_CAMERA_INDEX=0`
- `INFRASENTINEL_TASK_LEASE_SECONDS=120`
- `INFRASENTINEL_IMAGE_MAX_MB=50`, `INFRASENTINEL_VIDEO_MAX_GB=5`
- `INFRASENTINEL_VIDEO_MAX_SECONDS=7200`

`sync-vision-models` resolves paths, rejects directories and unsupported extensions, reads class names/input size, calculates SHA-256, and upserts two stable model records. A TensorRT engine is available only when its metadata matches the current GPU/runtime and a smoke inference passes. Otherwise the registered `.pt` fallback remains selectable and the reason is visible. The command is idempotent and never writes beside source assets.

## Data Model

All identifiers are UUIDs and timestamps are timezone-aware UTC.

### `vision_models`

- `id`, stable unique `code`, `name_zh`, `name_en`, `scene: pipeline | ppe`
- `pt_path`, optional `engine_path`, `asset_sha256`, `classes_json`, `input_size`
- `preferred_backend: auto | trt | pt`, `availability: available | unavailable`, optional bounded `unavailable_reason`
- `version_label`, `synced_at`, `created_at`, `updated_at`

The table is a minimal deployment registry, not the v1.4 model lifecycle. Only the local CLI writes it in v1.2.

### `detection_jobs`

- `id`, `kind: image | video | obs`, `status: queued | running | cancelling | cancelled | succeeded | failed`
- `project_id`, provisional `point_id` equal to `project_id`, `owner_id`, `model_id`
- `scene`, `parameters_json`, `progress_percent`, optional `progress_detail`
- `attempt`, `max_attempts=3`, optional `retry_of_id`
- lease fields `claimed_by`, `lease_expires_at`, `heartbeat_at`
- cancellation/failure fields `cancel_requested_at`, `cancelled_at`, `error_code`, bounded `error_detail`
- `queued_at`, `started_at`, `finished_at`, `created_at`, `updated_at`

Only queued jobs can be claimed. Cancellation is cooperative between frames/files. Retrying creates a new job linked to the failed/cancelled job and reuses immutable input media; successful jobs are not retried.

### `detection_media`

- `id`, `job_id`, `role: original | annotated | keyframe`, `media_type: image | video`
- server-generated `storage_key`, safe original display name, MIME type, byte size, SHA-256
- optional width, height, duration, FPS, frame count; `created_at`

Paths are never accepted from clients or returned directly. The API authorizes a media id, resolves it beneath `storage_root`, and serves it with range support where applicable.

### `detection_observations`

- `id`, `job_id`, nullable `media_id`, `frame_index`, `timestamp_ms`
- `class_name`, `confidence`, `x1`, `y1`, `x2`, `y2`
- `inference_ms`, `created_at`

Image objects use frame zero. Video/OBS persist only frames containing detections plus sampled performance summaries; empty-frame rows are not stored. v1.3 may group these immutable raw observations into events without rewriting them.

### `detection_metrics`

- `id`, `job_id`, `sample_at`, `processed_frames`, `effective_fps`, `inference_p50_ms`
- optional `gpu_percent`, `gpu_memory_used_mb`, `gpu_memory_total_mb`

Metrics are sampled at bounded intervals, not once per frame.

## Storage Contract

- Uploads stream to `runtime/storage/staging/<job-id>/` while hashing and enforcing byte limits; successful validation atomically moves them to `originals/<yyyy>/<mm>/<job-id>/`.
- Annotated outputs live under `annotated/<yyyy>/<mm>/<job-id>/`; OBS keyframes live under `keyframes/...`.
- Server-generated UUID names are used on disk. The sanitized client filename is display metadata only.
- Images accept JPEG, PNG, and WebP after decoder validation. Videos accept MP4, MOV, AVI, and MKV only when FFprobe can decode metadata and duration is at most two hours.
- Batch image creation accepts at most 100 files and 2 GB total per request; each file becomes its own job so failures, retry, progress, and ownership stay independent.
- Failed validation removes only its own staging file. Failed processing retains the original and partial diagnostic metadata but never publishes a partial annotated output as complete.
- v1.2 exposes no deletion endpoint. Originals and successful annotated artifacts are retained for later audited quarantine policy.
- Before accepting an upload, the service checks configured storage warning/critical thresholds and returns a localized capacity error when the operation cannot be safely completed.

## Inference and Job Lifecycle

### Shared inference adapter

- Refactor the current handlers without changing `infer(scene, image, conf, save, backend)` output fields.
- The internal adapter accepts `conf`, `iou`, `imgsz`, and `device`; validates ranges; returns pixel-space boxes, class name/id, confidence, backend, input/output size, and inference duration.
- Defaults: confidence `0.35`, IoU `0.70`, model input size, device `auto`. Allowed input sizes are 320-1280 and multiples of 32.
- `auto` selects a validated TensorRT engine, otherwise CUDA PyTorch, otherwise CPU PyTorch. A backend fallback is recorded in the job result and UI rather than hidden.
- Models are cached once per worker process and never loaded in a FastAPI request process.

### Image

- One job processes one image, persists every detection, writes one annotated image, class counts, dimensions, timings, backend, and model checksum/version.
- Batch uploads create independent jobs and return their ids in original order.

### Video

- Parameters include detection FPS (`0.5-30`, default min(source FPS, 10)) and output quality (`standard | high`). Frames between inference samples reuse no fabricated boxes.
- Progress is processed source time divided by duration. Cancellation is checked at least once per decoded second.
- The result contains annotated MP4, detection timeline, keyframes selected from detected frames, per-class counts, processed/source FPS, elapsed time, and model identity.
- v1.2 does not claim that repeated boxes are one event. That deterministic grouping is implemented and tested with the v1.3 rule/alert module.

### OBS live session

- Only one `obs` job may be running or queued system-wide; the database enforces this through a transactional advisory lock plus status check.
- Start validates the configured Windows camera index, model, project access, resolution (640p or 720p), target detection FPS (`1-30`), confidence, and IoU.
- The worker reads continuously, dynamically skips frames to approach the selected target, and allows the owner/admin to change target FPS, confidence, IoU, and resolution without restarting the session.
- Redis stores only the latest annotated JPEG and recent performance snapshot with a short TTL. The browser reconnects automatically and shows an explicit stale/disconnected state.
- Detected observations and bounded keyframes are durable. Stop/cancel closes the capture device, finalizes metrics, and marks the session cancelled with a normal user-stop reason; device loss marks it failed and allows retry.
- The UI shows preview, actual FPS, inference/preview latency, backend/model, parameters, GPU/memory when available, and a raw detection activity list. Alert events are not shown until v1.3.

### Recovery and concurrency

- Workers update heartbeats while running. A worker may reclaim a job only after its lease expires; processing writes to attempt-specific temporary outputs so a reclaimed job cannot publish another worker's file.
- Database state change and final media/observation registration commit together after the output is atomically finalized.
- Default two worker processes allow two GPU jobs. The single OBS session consumes one slot. PostgreSQL claiming prevents duplicate execution.
- Retryable errors include transient decoder/device/GPU failures. Invalid media, missing model assets, unsafe parameters, and authorization failures are not automatically retried.

## API Contract

All routes are under `/api/v1` and use the existing cookie session, same-origin checks, localized error envelope, and request ids.

| Method and path | Access | Behavior |
|---|---|---|
| `GET /vision/models` | Enabled user | List available/unavailable registered models safely |
| `POST /detections/images` | Enabled user | Stream 1-100 images and create one durable job per image |
| `POST /detections/videos` | Enabled user | Stream one video and create a durable job |
| `GET /detections/jobs` | Enabled user | Cursor list; admin all, user own; filter by project/kind/status/model/time |
| `GET /detections/jobs/{id}` | Authorized owner/admin | Job, parameters, progress, result summary, media, observations, metrics |
| `POST /detections/jobs/{id}/cancel` | Authorized owner/admin | Idempotently request cooperative cancellation |
| `POST /detections/jobs/{id}/retry` | Authorized owner/admin | Create linked retry when state permits |
| `GET /detections/media/{id}` | Authorized owner/admin | Serve authorized original/annotated media with safe headers/ranges |
| `POST /detections/obs` | Enabled user | Start the single OBS session |
| `PATCH /detections/obs/{id}` | Owner/admin | Dynamically update allowed live parameters |
| `POST /detections/obs/{id}/stop` | Owner/admin | Stop and finalize the live session |
| `WS /detections/obs/{id}/preview` | Owner/admin | Latest preview/status stream; no durable data depends on socket delivery |

List default is 50 and maximum 200. Bounding-box detail is cursor-paginated for long videos. Upload routes use request-level and user-level Redis rate limits and return 503 when their safety limiter is unavailable.

## Authorization, Validation, and Audit

- Project access and ownership are resolved server-side before job creation, listing, detail, media, cancellation, retry, OBS update, or preview.
- A normal user may never name another user as owner. Administrators may inspect all records but created work still records the actual actor.
- Model id, scene, project, parameters, upload bytes, decoder metadata, and media id are validated independently of frontend controls.
- Media responses use `nosniff`, safe content disposition, and no path information. SVG, HTML, executables, archives, and unknown decoders are rejected.
- Audit events cover job create/start/cancel/retry/fail/succeed, OBS parameter updates, model sync results, and authorized media access where an original is downloaded. Audit JSON contains ids/checksums and safe parameters, never binary data or local absolute asset paths.

## Frontend Experience

- Add primary navigation for “智能检测 / Detection” and “检测记录 / History”.
- Create screen offers Image, Video, and OBS modes; project, scene/model, confidence, IoU, input size, device policy, and mode-specific parameters have explicit labels, safe defaults, and concise help.
- Upload uses native file inputs and XMLHttpRequest only where upload progress is required; all other API calls keep native `fetch`.
- Queue cards show status text/icon, progress, elapsed time, retry/cancel actions, model/backend, and readable failure details. Status never depends only on color.
- Detail renders original/annotated media, class totals, object table, coordinates/confidence, video timeline markers, parameters, model checksum/version, timings, and linked retry.
- Image bounding boxes are selectable and synchronized with the object table. Video detail seeks to observation timestamps.
- OBS screen requires an explicit start gesture, shows live/stale/disconnected states, allows runtime FPS/threshold changes, and requires confirmation before stopping another user's session as administrator.
- All new strings and errors have identical `zh-CN` and `en` keys; controls remain keyboard reachable, focus visible, and layouts work at 360px and 1280px.

## Code Style

- Keep orchestration in explicit typed functions and SQL transactions. Do not hide job transitions in ORM hooks.
- Centralize legal transitions and enforce them with conditional updates:

```python
updated = session.execute(
    update(DetectionJob)
    .where(DetectionJob.id == job_id, DetectionJob.status == JobStatus.QUEUED)
    .values(status=JobStatus.RUNNING, claimed_by=worker_id)
)
if updated.rowcount != 1:
    raise JobNotClaimedError(job_id)
```

- Stream and hash media in bounded chunks; never call `await upload.read()` without a size bound.
- Use `Path`, `safe_path`, argument-list subprocess calls, UTC-aware timestamps, strict TypeScript, named React exports, typed locale keys, and native semantic controls.
- Deliberate single-host ceilings are documented with `ponytail:` comments at the worker claim loop and single-OBS guard, naming the multi-host upgrade point.

## Testing Strategy

### Unit tests

- Parameter bounds and presets, legal job transitions, retryability classification, lease expiry, storage key safety, streamed size/hash validation, annotation coordinates, frame sampling, model fallback, and legacy CLI schema compatibility.
- Synthetic images/video and fake inference adapters; ordinary tests do not require weights, GPU, OBS, Docker, or network.

### PostgreSQL/Redis integration tests

- Migration upgrade/downgrade/upgrade and indexes/constraints.
- Atomic job claim with two workers, lease recovery, cooperative cancellation, retry linkage, and one-OBS exclusion.
- Ownership/project/admin access across list/detail/media/WebSocket paths.
- Original/output finalization, rollback after processing failure, Redis preview expiry, and audit completeness/redaction.
- Upload limits, decoder rejection, path traversal attempts, range responses, localized errors, and rate-limiter failure.

### Frontend tests

- Image/video/OBS form validation, bilingual key parity, upload and processing progress, cancel/retry, record filtering, object selection, and authorization/error states.
- WebSocket live/stale/reconnect behavior with mocked messages.
- TypeScript, lint, production build, 360px layout, keyboard focus, and non-color status cues.

### Hardware/manual acceptance

1. Register both legacy trained models and verify TensorRT preferred with `.pt` fallback visible.
2. Submit pipeline and PPE images, including a batch with one invalid file; verify independent outcomes and annotated details.
3. Process a common video, observe progress, cancel one run, retry it, and play/seek/download the completed annotated MP4.
4. Run two simultaneous GPU jobs and confirm neither duplicates or blocks Web requests.
5. Start OBS with a local video in OBS Virtual Camera, switch 640p/720p and target FPS while running, reconnect the browser, then stop cleanly.
6. On RTX 4060, sustain one 640p/720p OBS stream for one hour at at least 15 effective FPS, median end-to-end latency at most 300 ms, with no queue growth or crash.
7. Restart a worker during a job and verify lease-based recovery without duplicate published output.
8. Confirm a normal user cannot read another user's jobs or media, while an administrator can.

## Boundaries

### Always

- Run inference outside Web request processes; keep durable state in PostgreSQL/storage; authorize every media and preview access.
- Preserve originals and immutable observations, record model checksum/backend/parameters, and atomically publish completed outputs.
- Bound uploads, decoders, parameters, result pagination, WebSocket frame rate, failure text, and metrics frequency.
- Keep legacy media/weights read-only and excluded from Git; run migration, backend/frontend tests, lint/build, live health, CUDA, media, and OBS acceptance before v1.2 archive.

### Ask first

- Adding a dependency beyond `python-multipart`, another inference backend, model conversion/download, a second camera/source type, or more than two worker processes by default.
- Changing upload/duration/concurrency limits, retention behavior, model asset paths, result schema, or project/ownership visibility.
- Implementing event merging, rules, alerts, LLM analysis, reports, deletion, or model lifecycle ahead of their milestones.

### Never

- Commit or copy datasets, videos, weights, engines, ONNX files, generated media, `.env`, secrets, or absolute local asset paths into tracked files.
- Load a model or process a video synchronously inside an HTTP request.
- Trust client MIME type, filename, project/owner/model identity, box coordinates, or media paths without server validation.
- Serve storage by arbitrary path, expose another user's record, publish partial output as successful, or make Redis the only copy of business data.
- Fabricate event merging, risk severity, or LLM conclusions in v1.2.

## Success Criteria

- [x] One reversible Alembic migration creates the v1.2 model/job/media/observation/metric schema and required constraints/indexes.
- [x] Idempotent model sync registers both legacy scenes without copying assets; unavailable/fallback reasons are safe and visible.
- [x] Existing CLI tests remain compatible, while one shared adapter powers CLI, images, videos, and OBS.
- [x] Image batch and video uploads are streamed, bounded, decoder-validated, safely stored, hashed, and independently auditable.
- [x] Two Windows worker processes claim durable work atomically, heartbeat, recover expired leases, cancel cooperatively, and create linked retries.
- [x] Completed image/video jobs retain originals, annotated outputs, raw detections, parameters, model checksum/backend, progress, metrics, and readable failure state.
- [x] Exactly one OBS session runs; preview reconnects, parameters change live, observations persist, and stop/device-loss finalize correctly in fake-capture acceptance.
- [x] Normal users can access only their own jobs in assigned projects; administrators can access all; API and media tests prove both paths.
- [x] Detection create/history/detail/OBS Web screens are bilingual, responsive, keyboard operable, and accurately expose progress/fallback/stale/error states.
- [ ] Python tests/Ruff, frontend tests/lint/build, migration cycle, Compose/config, secret/large-file checks, live readiness, CUDA, media, and one-hour OBS acceptance pass.
- [x] Review findings, requirement deviations, operational commands, and verification evidence are recorded in `AGENT.md` before commit/tag/push.

## Implementation Evidence and Deviations

- Automated verification passes with 53 Python tests and 9 frontend tests; Ruff, ESLint, TypeScript/Vite, `pip check`, Compose configuration, PowerShell parsing, CUDA discovery, migration round-trip, model sync, and real image/video inference have passed on the acceptance host.
- OBS capture, preview TTL, reconnect, dynamic settings, keyframes, cancellation, device failure, and cleanup are covered with fake capture/Redis tests. The real OBS Virtual Camera was not active on camera index 0, so the one-hour hardware run remains the only unchecked acceptance item.
- Video metadata is decoder-validated with OpenCV rather than a separate FFprobe subprocess. FFmpeg still produces the browser-playable H.264 result.
- TensorRT compatibility is tried when each worker loads a configured engine; an incompatible engine falls back to `.pt` and the completed job records the actual backend. Model sync itself verifies path/type/checksum, not a standalone TensorRT smoke inference.
- Job detail returns a bounded first observation window and the list supports project/kind/status filters. Cursor pagination plus model/time filters remain a follow-up before very large archive use.
- GPU utilization/memory columns are reserved but are not sampled in v1.2; effective FPS and inference p50 are persisted. OBS hardware telemetry and one-hour stability evidence remain pending the real camera run.

## Open Questions

None. The assumptions use the user's approved defaults. On 2026-09-02 the user approved this specification and instructed implementation to continue without intermediate questions until final review.
