# v1.1 Task Ledger: identity-access

Tasks are dependency-ordered. Each task is limited to approximately five implementation files; generated lockfiles and migration artifacts count as files. Check a task only after its verification command passes.

- [x] Task 1: Pin backend and frontend dependencies
  - Acceptance: Conda resolves `pwdlib[argon2]` and Node 24 LTS; npm direct/transitive versions are locked exactly; no unapproved runtime library is added.
  - Verify: `conda env update -n infrasentinel -f environment.yml --prune`; `npm --prefix frontend ci`; version checks; `pip check`.
  - Files: `environment.yml`, `frontend/package.json`, `frontend/package-lock.json`

- [x] Task 2: Configure the frontend compiler, lint, test, and proxy baseline
  - Acceptance: strict TypeScript, Vite `/api` proxy, ESLint, and Vitest run against an empty application shell.
  - Verify: `npm --prefix frontend run lint`; `npm --prefix frontend run test -- --run`; `npm --prefix frontend run build`.
  - Files: `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/eslint.config.js`, `frontend/index.html`, `frontend/src/vite-env.d.ts`

- [x] Task 3: Define the identity/access database model
  - Acceptance: typed models represent users, sessions, minimal projects, memberships, and audit events with approved enums, timestamps, uniqueness, and foreign keys.
  - Verify: model metadata tests assert tables, constraints, and indexes without writing secrets.
  - Files: `src/infrasentinel/models.py`, `src/infrasentinel/database.py`, `tests/test_identity_models.py`

- [x] Task 4: Add and round-trip the v1.1 migration
  - Acceptance: one reversible migration creates all five tables and an audit update/delete rejection trigger; downgrade removes only v1.1 objects.
  - Verify: `python -m alembic upgrade head`; `python -m alembic downgrade -1`; `python -m alembic upgrade head`; focused PostgreSQL assertions.
  - Files: `alembic/env.py`, `alembic/versions/20260901_0002_identity_access.py`, `tests/test_identity_migration.py`

- [x] Task 5: Implement password, token, session-expiry, and cookie primitives
  - Acceptance: Argon2 hash/verify/update, dummy verification, 32-byte opaque tokens, SHA-256 storage digests, idle/absolute expiry, and environment-correct cookie flags match the spec.
  - Verify: `python -m pytest tests/test_auth.py -q`.
  - Files: `src/infrasentinel/auth.py`, `src/infrasentinel/config.py`, `.env.example`, `tests/test_auth.py`

- [x] Task 6: Add bilingual error envelopes and request IDs
  - Acceptance: API and validation failures use stable codes, zh-CN/en messages, safe fields, and `X-Request-ID`; locale resources have identical keys.
  - Verify: `python -m pytest tests/test_errors.py -q`; Ruff.
  - Files: `src/infrasentinel/errors.py`, `src/infrasentinel/main.py`, `tests/test_errors.py`

- [x] Task 7: Add append-only audit writing and redaction
  - Acceptance: one insert-only audit helper removes passwords, hashes, tokens, cookies, API keys, and authorization values recursively; the database rejects audit update/delete.
  - Verify: `python -m pytest tests/test_audit.py -q` against unit and PostgreSQL paths.
  - Files: `src/infrasentinel/services.py`, `tests/test_audit.py`

- [x] Task 8: Implement registration and bootstrap administrator services
  - Acceptance: registration normalizes identity and creates only pending users; CLI bootstrap is secret-safe and idempotently creates one enabled admin; both write audit events transactionally.
  - Verify: focused service/CLI tests plus one real bootstrap run with temporary credentials.
  - Files: `src/infrasentinel/schemas.py`, `src/infrasentinel/services.py`, `src/infrasentinel/cli.py`, `tests/test_identity_services.py`, `.env.example`

- [x] Task 9: Implement session authentication routes and dependencies
  - Acceptance: register/login/logout/me/profile/password routes enforce account state, opaque session creation/revocation, generic invalid credentials, and authenticated user resolution.
  - Verify: `python -m pytest tests/test_identity_api.py -q` with PostgreSQL.
  - Files: `src/infrasentinel/identity_api.py`, `src/infrasentinel/dependencies.py`, `src/infrasentinel/main.py`, `tests/test_identity_api.py`

- [x] Task 10: Implement administrator lifecycle and project-access routes
  - Acceptance: admins can list/filter users, change status, create minimal projects, manage memberships, and query audits; users see only assigned active projects; last enabled admin is protected.
  - Verify: `python -m pytest tests/test_admin_api.py -q` with the full role/project matrix.
  - Files: `src/infrasentinel/identity_api.py`, `src/infrasentinel/services.py`, `src/infrasentinel/schemas.py`, `tests/test_admin_api.py`

- [x] Task 11: Enforce Redis rate limits and cookie-request origin checks
  - Acceptance: registration/login limits return localized 429, Redis outage returns 503, unsafe cross-origin cookie requests fail, and allowed same-origin requests remain functional.
  - Verify: `python -m pytest tests/test_auth_security.py -q` with Redis and representative Origin/Referer cases.
  - Files: `src/infrasentinel/auth.py`, `src/infrasentinel/dependencies.py`, `src/infrasentinel/identity_api.py`, `tests/test_auth_security.py`

- [x] Task 12: Create frontend runtime, typed API boundary, and locale resources
  - Acceptance: React mounts, native fetch preserves cookies and parses safe errors, zh-CN/en resources have typed key parity, and route guards distinguish anonymous/pending/user/admin.
  - Verify: focused Vitest tests and strict TypeScript build.
  - Files: `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/api/client.ts`, `frontend/src/i18n/index.ts`, `frontend/src/auth/session.tsx`

- [x] Task 13: Build accessible login, registration, and pending pages
  - Acceptance: public forms have labels, visible/announced errors, password visibility control, language switch, keyboard support, and correct lifecycle navigation.
  - Verify: `npm --prefix frontend run test -- --run` for public identity flows; manual keyboard check at 360px and 1280px.
  - Files: `frontend/src/pages/LoginPage.tsx`, `frontend/src/pages/RegisterPage.tsx`, `frontend/src/pages/PendingPage.tsx`, `frontend/src/styles/auth.css`, `frontend/src/test/public-auth.test.tsx`

- [x] Task 14: Build the authenticated shell and user-administration page
  - Acceptance: the shell shows safe identity/role/project state; admin user table is pending-first and supports approve/reject/disable and project assignment with confirmations.
  - Verify: component tests for user/admin guards and lifecycle actions; manual narrow/desktop layout review.
  - Files: `frontend/src/pages/AppHomePage.tsx`, `frontend/src/pages/AdminUsersPage.tsx`, `frontend/src/components/ProjectAssignment.tsx`, `frontend/src/styles/app.css`, `frontend/src/test/admin-users.test.tsx`

- [x] Task 15: Build audit UI and finish bilingual resource coverage
  - Acceptance: admins can filter/paginate audit events and view sanitized JSON; normal users are blocked; every v1.1 visible key exists in both locales.
  - Verify: audit-page component tests, locale parity test, and manual English/Chinese review.
  - Files: `frontend/src/pages/AdminAuditPage.tsx`, `frontend/src/components/AuditDetails.tsx`, `frontend/src/i18n/index.ts`, `frontend/src/test/admin-audit.test.tsx`, `frontend/src/test/i18n.test.ts`

- [x] Task 16: Serve the production Web UI without breaking API/docs
  - Acceptance: FastAPI serves `frontend/dist` at `/` with SPA fallback; `/api/v1`, `/docs`, OpenAPI, health, and deep links remain correct; lifecycle scripts build/start the intended application process.
  - Verify: backend route tests, frontend production build, live restart, `/`, deep-link, `/docs`, and readiness checks.
  - Files: `src/infrasentinel/main.py`, `scripts/start.ps1`, `tests/test_api.py`, `frontend/vite.config.ts`, `README.md`

- [x] Task 17: Run integrated identity-access acceptance
  - Acceptance: bootstrap → register → pending → approve → login → project assignment/isolation → locale switch → password/session revocation → disable → audit succeeds on the live stack.
  - Verify: full Python/npm/lint/build/migration/Compose/PowerShell checks plus recorded manual browser evidence.
  - Files: `tests/test_identity_acceptance.py`, `scripts/verify_environment.py`, `SPEC-identity-access.md`

- [x] Task 18: Review, document, and prepare the v1.1 milestone
  - Acceptance: required/critical findings are resolved; task/spec success criteria and evidence are current; ignored secrets/runtime/media stay excluded; user has reviewed the result before push.
  - Verify: code-quality review, `git diff --check`, secret/large-file scan, full verification rerun, live health check.
  - Files: `AGENT.md`, `README.md`, `tasks/plan.md`, `tasks/todo.md`, `PROJECT_REQUIREMENTS.md`
