# Spec: alert-intelligence (v1.3)

## Status and Assumptions

- Module id: `alert-intelligence`; depends on `identity-access` and `vision-detection`.
- Existing defaults were approved in `PROJECT_REQUIREMENTS.md`; continuous implementation is authorized.
- Cloud credentials arrive later. Their absence must never block deterministic rules or alerts.
- Rules are authoritative; LLM results are advisory and cannot change final severity.
- Pipeline classes `CK`, `PL`, `SG`, `SL`, `TL`, `ZW` default to medium risk; `no_helmet` defaults high; `helmet` creates no alert by default.
- Image observations remain distinct. Same-class video/OBS observations merge at time gap <=3 seconds and IoU >=0.30.
- One merged event produces at most one alert. Automatic LLM analysis defaults on, with `waiting_configuration` when no usable key exists.
- Qwen, DeepSeek, and GLM use one configurable OpenAI-compatible HTTP adapter. No provider SDK is added.
- System/personal API keys use Fernet encryption derived from the existing application secret and are never returned or logged.
- External notifications, dashboard, reports, deletion, project-point expansion, cost dashboards, RAG, and desktop sync stay in later modules.

## Objective

Turn v1.2 observations into a durable, auditable response workflow:

- merge repeated video/OBS observations into stable events;
- evaluate configurable global/project rules and create one alert per event;
- optionally request structured object/global cloud analysis;
- expose evidence, rule hits, LLM state, assignment, deadlines, notes, attachments, and immutable action history;
- support `pending_confirmation -> assigned -> processing -> resolved | false_positive`;
- remain bilingual, authorized, and usable when cloud service is absent.

## Tech Stack and Minimal Design

- Reuse FastAPI, SQLAlchemy/Alembic, PostgreSQL, Redis, React/TypeScript, `cryptography`, and `httpx` already pinned. Add no dependency, broker, SDK, rules DSL, workflow engine, or notification framework.
- PostgreSQL stores rules, events, alerts, analyses, provider metadata, encrypted credentials, call logs, attachments, and append-only actions.
- One intelligence worker claims analysis jobs with PostgreSQL leases. Rule evaluation/event grouping are local and never wait for cloud I/O.
- Provider output is bounded and validated with strict Pydantic models before success.

## Commands

```powershell
conda activate infrasentinel
python -m alembic upgrade head
python -m infrasentinel.cli seed-alert-rules
python -m infrasentinel.cli backfill-intelligence
python -m infrasentinel.intelligence_worker
python -m pytest -q
ruff check src tests alembic
Push-Location frontend; npm run test -- --run; npm run lint; npm run build; Pop-Location
```

## Project Structure

```text
src/infrasentinel/
  intelligence_models.py      # rules, events, alerts, analyses and evidence
  intelligence_schemas.py     # API and structured LLM contracts
  intelligence_service.py     # grouping, grading, workflow, authorization and audit
  intelligence_api.py         # alert/rule/provider/analysis routes
  llm_adapter.py              # encryption and bounded OpenAI-compatible request
  intelligence_worker.py      # leased analysis jobs

frontend/src/
  api/alerts.ts
  pages/AlertCenterPage.tsx
  pages/AlertDetailPage.tsx
  pages/AdminRulesPage.tsx
  pages/AdminLlmPage.tsx
```

Files may be combined to remove indirection. There is one rule evaluator and one HTTP adapter.

## Data Model

### Rules, events, alerts, and evidence

- `alert_rules`: stable code/name, optional project/class, minimum confidence, `low|medium|high`, merge window, IoU, cooldown, priority, enabled, creator/timestamps.
- `detection_events`: job/project/owner/model/scene/class, first/last frame/time, duration/count/max confidence, representative observation/keyframe, `open|closed`, deterministic unique fingerprint.
- `alerts`: unique event, matched rule, final level, workflow status, title/summary, assignee, response/close deadlines, resolution note, version and timestamps.
- `alert_actions`: append-only actor/action/before/after/result timeline.
- `alert_attachments`: safe generated storage key, display name, MIME, bytes, hash, uploader/time.

### Providers and analyses

- `llm_provider_configs`: provider, HTTPS endpoint, model, vision capability, timeout, retries, enabled/default and timestamps.
- `llm_credentials`: encrypted key and system/user scope; API responses expose only configured state.
- `llm_analyses`: image job or event, status, structured result, attempts/lease, safe error, provider/model and timestamps.
- `llm_calls`: duration/status/request-response sizes/token counts when supplied/safe error; never key, prompt, image, path, or raw secret.

## Event and Rule Algorithm

1. Sort observations by class, timestamp, frame, id.
2. Image: one deterministic event per observation.
3. Video/OBS: append to latest same-class event only within merge window and IoU threshold; otherwise close/start.
4. Highest-confidence observation is representative; duration/count update monotonically.
5. Select highest-priority enabled project rule, then global rule, matching class/confidence. No match means no alert.
6. Upsert alert by unique event id and copy the rule level as final level. Admin override requires a reason/action record.
7. Queue automatic analysis once per image job or closed event. Manual retry reuses the analysis record with a new attempt.

This does not claim tracking across occlusion/camera cuts. Add a tracker only when real acceptance proves the deterministic grouping insufficient.

## LLM Contract

Structured output contains bounded object analyses keyed by observation id plus `global_risk`, conclusion, priorities, and associations. Each object includes advisory severity, explanation, possible causes, and repairs. Unknown ids, invalid JSON/schema, oversize response, timeout, redirect, non-2xx, and rate limits are safe failures.

Provider selection prefers an authorized personal key when requested, then the enabled system default. No usable config/key becomes `waiting_configuration`. Provider endpoints require HTTPS except loopback in development; redirects are disabled.

## API Contract

All routes use existing cookie auth, same-origin mutation checks, localization, request ids, audit, and project scope.

| Method and path | Access | Behavior |
|---|---|---|
| `GET /alerts` | Enabled user | Admin all; user own/assigned; bounded filters/page |
| `GET /alerts/{id}` | Authorized user | Event, evidence, rule, analysis and actions |
| `PATCH /alerts/{id}` | Owner/assignee/admin | Versioned state, assignment, note, deadlines; admin level override |
| `POST /alerts/{id}/attachments` | Owner/assignee/admin | Bounded evidence attachment |
| `GET /alerts/attachments/{id}` | Authorized user | Safe evidence response |
| `POST /alerts/{id}/analyze` | Authorized user | Queue/retry analysis |
| `GET/POST/PATCH /admin/alert-rules` | Admin | Manage bounded deterministic rules |
| `GET/POST/PATCH /admin/llm/providers` | Admin | Manage provider metadata/system key replacement |
| `GET/PUT/DELETE /profile/llm-credential` | Enabled user | Write-only personal key |

## Authorization, Security, and Audit

- Users see alerts only when they own the source detection or are assigned and still hold project membership; admins see all.
- Transitions are server-side, versioned, constrained; close requires a note and assignment requires an enabled project member.
- Keys are write-only/encrypted/redacted. Provider request time, redirects, body size, response size, endpoint and schema are bounded.
- Rule/config/credential changes, analysis states, alert creation/assignment/transition/override, and attachments are audited.

## Frontend Experience

- “预警中心 / Alerts” supports level/status/project/class/assignee/time filtering.
- Detail orders evidence as source/event -> observations -> rule/final level -> LLM advice/state -> actions/attachments.
- Risk/status use text plus color; only valid workflow actions render and all failures are visible.
- Admin rule form edits bounded fields without an expression builder. Admin/personal key controls are write-only.
- No API shows “LLM analysis waiting for configuration”; alert handling remains complete.

## Testing Strategy

- Migration/models: reversible constraints/indexes and secret-response exclusion.
- Grouping: image objects, IoU/time boundaries, class separation, idempotent reruns.
- Rules/workflow: defaults, project precedence, uniqueness, transitions, assignment, required close note, audit.
- Adapter: Fernet, endpoint checks, fake transport success/timeout/non-2xx/oversize/invalid schema, redaction.
- Worker/API: lease/wait/retry/success, no severity mutation, owner/assignee/admin matrix, safe attachment.
- Frontend: list/detail/rules/settings, bilingual parity, keyboard/narrow viewport, lint/build.
- Live acceptance uses fake provider responses until real credentials arrive.

## Boundaries

- Always: rules complete without LLM; validate output; encrypt keys; authorize evidence; audit transitions; bound lists/text/files/network; run full review and secret scan.
- Ask first: new dependency/SDK, default-risk change, non-HTTPS remote endpoint, more cloud media, new states, external notifications, arbitrary rules, face redaction, or LLM-driven final severity.
- Never: commit/log keys or local paths; block detection/rules on LLM; alert per frame; trust client ownership/state; implement later-module dashboards/reports/deletion/RAG.

## Success Criteria

- [ ] Reversible migration and idempotent seed create safe schema/default rules.
- [ ] Existing/new detections produce deterministic events and one matched alert per event.
- [ ] Rule defaults/project precedence/confidence/override work independently of LLM.
- [ ] Alert authorization, workflow, assignment, deadlines, notes, attachments and actions are transactional/audited.
- [ ] Keys are write-only/encrypted; adapter validates bounded structured output.
- [ ] Analysis worker supports auto/manual, waiting configuration, retry/failure/success without changing severity.
- [ ] Bilingual alert center/detail/admin rule/provider UI is responsive and accessible.
- [ ] Full regression, migration, fake provider, live no-key rule/backfill, review and scans pass.
- [ ] Evidence/deviations are recorded and only the development branch is pushed.

## Open Questions

None blocking. Real endpoint/model/API-key acceptance waits for user credentials; fake provider tests define the contract meanwhile.
