# v1.3 Implementation Plan: alert-intelligence

Implement `SPEC-alert-intelligence.md` on `codex/v1.2-vision-detection`. Existing defaults and uninterrupted-build authorization cover all phases. No main merge or new tag occurs.

## Slice 1 — Durable foundation

1. Add rules/events/alerts/actions/attachments/providers/credentials/analyses/call tables.
2. Add one reversible migration with workflow, uniqueness, bounds and ownership indexes.
3. Seed global default rules idempotently.

Checkpoint: metadata/migration/seed tests and round trip pass; plaintext credentials cannot appear in API models.

## Slice 2 — Events, rules and workflow

1. Implement pure IoU/time grouping and deterministic fingerprints.
2. Upsert events/one alert per event and backfill successful jobs.
3. Implement access, assignment, legal transitions, deadlines, notes, level override and append-only actions.
4. Hook completed vision jobs and periodic OBS commits into idempotent refresh.

Checkpoint: grouping boundaries, project precedence, uniqueness, workflow and audit pass; live backfill creates alerts without LLM.

## Slice 3 — Provider configuration and analysis worker

1. Derive Fernet encryption from application secret and add write-only system/personal credential services.
2. Implement one bounded OpenAI-compatible multimodal request with strict response validation.
3. Add analysis claim/lease/wait/retry/finalization and one intelligence worker.
4. Add provider, credential and manual analysis APIs with fake transport tests.

Checkpoint: encryption/redaction, endpoint/response bounds, worker recovery and rule independence pass.

## Slice 4 — APIs and evidence

1. Add authorized bounded alert list/detail.
2. Add workflow/assignment/override and safe attachment upload/download.
3. Add admin rule/provider and personal credential routes.

Checkpoint: role matrix, illegal transitions, horizontal access, audit and safe-media tests pass.

## Slice 5 — Bilingual Web workflow

1. Add typed alert client, routes/navigation/status resources.
2. Build alert center and evidence detail/timeline with workflow controls.
3. Build minimal admin rules/provider and personal credential controls.

Checkpoint: component tests/lint/build and 360px/1280px review pass; missing API is clearly non-blocking.

## Slice 6 — Acceptance and branch archive

1. Run migration round trip, seed/backfill twice, full regressions, scripts and live workflow.
2. Run fake-provider end-to-end; real provider remains pending credentials.
3. Perform five-axis review and fix all critical/required findings.
4. Update docs/scans and push only the development branch.

## Risks and Controls

- Cloud API absent: waiting state + fake transport; rules never depend on cloud.
- Alert storms: deterministic fingerprint, unique event alert, merge window/cooldown.
- Secrets: Fernet, write-only schemas, redacted audit/logs, secret scan.
- SSRF/oversize: HTTPS/loopback checks, redirects off, time/body bounds.
- Workflow races: row locking/version checks and database constraints.
- Scope creep: no DSL, SDK, external notification, dashboard, report, RAG or deletion.

## Completion Rule

All ledger checks pass, exceptions are honest, no-key operation is usable, and only `codex/v1.2-vision-detection` is pushed.
