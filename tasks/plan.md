# v1.2 Implementation Plan: vision-detection

## Scope and authorization

This plan implements the user-approved `SPEC-vision-detection.md`. On 2026-09-02 the user explicitly authorized uninterrupted implementation through final review, so the plan and task phases do not pause for separate approval. LLM, rule grading, alerts, event merging, reports, deletion, model training/lifecycle, and Electron remain out of scope.

## Dependency graph

```text
approved specification
  └─ configuration + model deployment registry + migration
      ├─ shared inference runtime and annotation
      └─ durable job/media/observation services
          ├─ streamed image/video upload API
          ├─ PostgreSQL worker claim/lease/retry lifecycle
          │   ├─ image execution
          │   ├─ video execution
          │   └─ single OBS execution + Redis preview
          └─ authorized list/detail/media/OBS API
              └─ bilingual create/history/detail/live Web UI
                  └─ full regression + hardware/browser acceptance + review
```

## Build sequence

### Slice 1 — Persistence and configured model assets

1. Pin only `python-multipart` and add bounded vision settings.
2. Add v1.2 enums/tables and one reversible Alembic migration.
3. Add an idempotent CLI that registers the two configured legacy model deployments by path and checksum without copying bytes.

Checkpoint: schema round-trip passes and both local scenes can be represented as available/unavailable without preventing startup.

### Slice 2 — Shared runtime, storage, and lifecycle

1. Preserve the public `vision_inspection.infer` contract while exposing reusable typed detections and deterministic annotation.
2. Implement server-generated storage keys, chunked hashing, decoder validation, atomic finalization, and media metadata.
3. Implement legal job transitions, project/owner authorization, atomic PostgreSQL claim, heartbeat lease, cancellation, retry, and audit writes.

Checkpoint: pure tests prove transition, storage, authorization, fallback, and legacy compatibility behavior without GPU or real weights.

### Slice 3 — Image and video vertical flows

1. Add streamed image batch/video upload and durable job creation.
2. Execute image inference and persist annotated images/observations/metrics.
3. Execute sampled video inference, write browser-playable annotated video/keyframes, report progress, and cooperate with cancellation.
4. Expose authorized list/detail/media/cancel/retry routes.

Checkpoint: synthetic adapters and media prove complete, failed, cancelled, recovered, and retried flows; Web requests never execute inference.

### Slice 4 — Single OBS flow

1. Enforce one queued/running OBS job transactionally.
2. Add camera capture, dynamic parameters, bounded durable observations/keyframes, Redis latest-frame TTL, and clean stop/device-loss behavior.
3. Add authorized live status/preview delivery with explicit stale/reconnect state.

Checkpoint: fake camera tests cover concurrency, dynamic updates, disconnect, cancellation, and preview expiry; real OBS acceptance follows when the local device is available.

### Slice 5 — Bilingual Web experience

1. Add typed API contracts and detection navigation.
2. Build image/video/OBS create controls and upload/queue feedback.
3. Build history/detail media, object, timeline, progress, cancellation, and retry views.
4. Extend the industrial dark system for 360px/1280px, keyboard, focus, and non-color status cues.

Checkpoint: focused component tests, locale parity, lint, and production build pass.

### Slice 6 — Integrated acceptance and final review

1. Run full Python/frontend tests, Ruff, build, migration cycle, dependency/config/PowerShell checks, and secret/large-file scan.
2. Restart the live system, register real model assets, run image/video detections, verify two workers, and exercise one OBS session when a camera is available.
3. Perform multi-axis correctness/security/performance/maintainability/accessibility review and fix all required findings.
4. Update README, specification checkboxes, task evidence, and `AGENT.md`; leave the milestone uncommitted/unpushed for the user's final review.

## Key decisions

- PostgreSQL is the queue and source of truth; Redis is only short-lived OBS transport.
- Two independent Windows worker processes avoid CUDA fork inheritance and satisfy the approved two-job ceiling.
- One concrete adapter, worker, and storage layout are used; no generic broker/provider/repository abstractions.
- Model binaries remain read-only external assets selected by environment variables.
- Every API access applies both project access and ownership, with administrator global visibility.
- Outputs publish only after atomic filesystem finalization and a successful database transaction.

## Risks and mitigations

- **Low E-drive capacity:** reject unsafe uploads at a critical free-space floor; use tiny generated acceptance media; preserve the existing warning.
- **GPU/TensorRT mismatch:** smoke-test availability and expose `.pt` fallback; never fail application startup because a model is absent.
- **Worker crash or duplicate output:** claim with row locks, heartbeat leases, attempt-scoped temporary files, and conditional final transition.
- **Large/untrusted media:** chunked byte limits, decoder/FFprobe validation, UUID storage keys, bounded subprocess arguments, and authorized media ids.
- **OBS unavailable in automation:** cover the complete flow with a fake capture adapter and record real-device acceptance separately without weakening required code.
- **Long video result volume:** store only detected observations and sampled metrics; paginate observation API.
- **Scope creep:** retain raw observations for v1.3 but do not implement event grouping, risk, LLM, or alert concepts now.

## Verification matrix

| Area | Automated evidence | Live/manual evidence |
|---|---|---|
| Schema/models | metadata tests; Alembic up/down/up | tables/indexes inspected |
| Model registry/runtime | checksum/fallback/CLI tests | real pipeline and PPE assets synchronized |
| Storage/uploads | size/decoder/path/hash tests | invalid and valid generated media uploads |
| Queue/workers | claim/lease/cancel/retry tests | two worker processes and restart recovery |
| Image/video | synthetic inference integration | real YOLO image and short video outputs |
| OBS | fake capture/Redis/reconnect tests | one OBS virtual camera when available |
| Authorization | owner/project/admin matrix | two-account media isolation |
| Frontend | Vitest, locale parity, ESLint, build | zh-CN/en, keyboard, 360px/1280px |
| Release | full regression, diff/secret/large-file checks | user final review before Git/tag/push |

## Completion rule

v1.2 reaches final review only when the durable lifecycle, authorization, media safety, image/video/OBS paths, bilingual UI, regression suite, live stack, and review findings are documented together. Hardware unavailable at runtime is recorded honestly and may not be replaced by a false success claim.
