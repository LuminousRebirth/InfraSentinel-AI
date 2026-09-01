# v1.1 Implementation Plan: identity-access

## Scope and gate

This plan implements the user-approved `SPEC-identity-access.md`. It does not add OAuth/SSO/MFA, password recovery, custom roles, a generic policy engine, or business modules scheduled after v1.1. Implementation starts only after the human approves this plan and `tasks/todo.md`.

## Dependency graph

```text
approved spec
  └─ dependency/toolchain pins
      ├─ PostgreSQL identity schema + migration
      │   ├─ password/session primitives
      │   ├─ error/i18n/request-id foundation
      │   └─ append-only audit writer
      │       └─ registration + bootstrap services
      │           └─ session/authentication API
      │               └─ admin lifecycle + project-access API
      │                   └─ rate-limit/CSRF hardening
      └─ frontend compiler/test scaffold
          └─ typed API + locale + route guards
              ├─ login/register/pending pages
              └─ app/users/audit pages
                  └─ production static serving

backend + frontend complete
  └─ migration cycle + full regression + live/manual acceptance
      └─ review, documentation, v1.1 commit/tag/push
```

## Build sequence

### Slice 1 — Reproducible dependencies and persistence

1. Pin `pwdlib[argon2]` and the approved Node/frontend packages in Conda/npm manifests.
2. Create the minimal frontend compiler, lint, test, and Vite proxy configuration without application features.
3. Add SQLAlchemy models and one Alembic migration for users, sessions, projects, memberships, audit events, constraints, indexes, and the audit immutability trigger.
4. Prove migration upgrade/downgrade/upgrade against the real PostgreSQL container before building services on it.

Checkpoint: environment resolution succeeds, frontend empty build succeeds, and the v1.1 schema round-trips cleanly.

### Slice 2 — Security primitives and shared contracts

1. Implement Argon2 password hash/verify/update, dummy verification, opaque token generation/digest, expiry, and secure cookie settings.
2. Implement stable bilingual error resources, locale resolution, validation-error conversion, and `X-Request-ID` middleware.
3. Implement a single audit insertion/redaction path; application code receives no update/delete API.
4. Unit-test these primitives without Docker wherever possible.

Checkpoint: focused unit tests prove passwords/tokens are never echoed, error keys have zh-CN/en parity, and audit state is redacted.

### Slice 3 — Account lifecycle, sessions, and authorization API

1. Add schemas and transactional services for normalized registration and idempotent administrator bootstrap.
2. Add current-user, administrator, and project-access dependencies.
3. Add registration/login/logout/me/profile/password routes with database-backed session revocation.
4. Add administrator user-status, minimal project, membership, and audit-query routes.
5. Add Redis fixed-window limits and same-origin checks to unsafe cookie-authenticated operations.
6. Keep routes thin: validation and HTTP translation in routes, lifecycle rules and audit writes in transactional service functions.

Checkpoint: PostgreSQL/Redis integration tests cover pending → enabled → disabled, last-admin protection, project isolation, rate limits, CSRF rejection, and secret-free audit records.

### Slice 4 — Operable bilingual Web UI

1. Build a typed native-fetch boundary, locale resources, session context, and anonymous/pending/user/admin route guards.
2. Build accessible login, registration, and pending-approval pages.
3. Build the authenticated shell, authorized-project summary, user approval/status table, project assignment controls, and audit table.
4. Use the required industrial-dark visual system with native controls, strong focus states, semantic status labels, and 360px/1280px layouts.
5. Keep `/docs`; serve `frontend/dist` from FastAPI so the production UI and cookie API are same-origin.

Checkpoint: Vitest/component tests pass, TypeScript strict build passes, and manual browser checks cover keyboard navigation, both locales, narrow layout, and role-specific routes.

### Slice 5 — Integrated acceptance and milestone

1. Run full Python tests, Ruff, npm tests/lint/build, `pip check`, Compose validation, PowerShell parsing, and Alembic cycle.
2. Restart the live stack and run the approved bootstrap/register/approve/assign/login/disable/audit acceptance path.
3. Review security, authorization boundaries, dependencies, secret/large-file exclusions, and accessibility.
4. Update `README.md`, `AGENT.md`, spec deviations, and task evidence.
5. After user review and explicit GitHub approval, commit, tag `v1.1`, and push.

Checkpoint: every success criterion in `SPEC-identity-access.md` is checked with recorded evidence and no unresolved required/critical review finding.

## Transaction and authorization design

- Each lifecycle mutation and its audit event commit in one PostgreSQL transaction.
- Routes never accept role/status/owner decisions from the client beyond the exact administrator action schema.
- Session cookies contain only the raw opaque token; PostgreSQL stores only its SHA-256 digest.
- Account disable/reject, password change, and role change revoke sessions within the same transaction.
- Administrator global project access is implemented once in a shared dependency; normal-user access requires membership, and later modules add ownership checks.
- Failed login audit and Redis counters must not reveal whether an identifier exists.

## Parallel opportunities

- After API schemas and error codes are frozen, locale resources and frontend page layout can be developed independently from remaining backend endpoint internals.
- Pure password/session/error tests can run without Docker while migration and integration checks use PostgreSQL/Redis.
- Visual QA and backend security review can run independently after the integrated build exists.

No parallel work may create duplicate API contracts, domain enums, error-code sets, or locale sources.

## Risks and mitigations

- **Authentication regression:** write focused security tests before routes; use generic credential errors and dummy Argon2 verification.
- **Cookie auth on approved LAN HTTP:** keep `Secure=false` only in development; production validation requires `Secure=true`; enforce SameSite and same-origin checks in both modes.
- **Last-admin lockout:** reject any transition that would leave zero enabled administrators; cover concurrent transitions with a database transaction and test.
- **Audit tampering or leakage:** central redaction plus PostgreSQL update/delete rejection; test with representative secret keys and raw tokens.
- **Schema rollback:** keep all v1.1 objects in one reversible migration and prove upgrade/downgrade/upgrade before API work proceeds.
- **Redis outage:** fail registration/login with localized 503 instead of silently disabling rate limits; keep already-authenticated reads independent of Redis.
- **Frontend dependency churn:** pin direct and transitive versions in `package-lock.json`; add no UI/state/form/i18n framework without a demonstrated need.
- **Static-app routing conflict:** reserve `/api` and `/docs` before SPA fallback; test root, deep links, OpenAPI, and health routes.
- **Disk capacity:** v1.1 stores little media, but the existing 12.04 GB warning remains visible and blocks no identity work.

## Verification matrix

| Checkpoint | Automated evidence | Manual evidence |
|---|---|---|
| Toolchain | Conda update, npm clean install, empty frontend build | Node/Python versions recorded |
| Persistence | Alembic upgrade/downgrade/upgrade, schema integration tests | Tables/indexes/trigger inspected |
| Security primitives | Pytest password/token/error/audit suites | No secret appears in logs/responses |
| Identity API | API and PostgreSQL/Redis integration tests | Register → approve → login → disable |
| Authorization | Role/project matrix tests | User sees one assigned project; admin sees all |
| Frontend | Vitest, ESLint, TypeScript/Vite build | zh-CN/en, keyboard, 360px/1280px |
| Deployment | Compose config, PowerShell parse, live readiness | `/` UI, `/docs`, API and restart behavior |
| Release | Git diff/secret/large-file checks | User review before `v1.1` push |

## Completion rule

The module is not complete because pages render or endpoints return 200. It is complete only when the full lifecycle, authorization matrix, audit immutability/redaction, bilingual UI, production build, live restart, and documented verification all pass together.
