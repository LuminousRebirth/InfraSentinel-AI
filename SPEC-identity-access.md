# Spec: identity-access (v1.1)

## Status

- Module id: `identity-access`
- Milestone: `v1.1`
- Depends on: `platform-foundation` (`v1.0`)
- State: draft for human review
- Scope source: `PROJECT_REQUIREMENTS.md`, `CAPABILITY_MAP.md`, and the approved 2026-09-01 defaults

## Assumptions

1. The Web UI and later Electron client use the same cookie-authenticated API; v1.1 does not expose bearer tokens to browser JavaScript.
2. Only two roles exist: `admin` and `user`. There is no organization hierarchy, custom role editor, OAuth, SSO, MFA, or external identity provider in v1.1.
3. A self-registered account starts as `pending` and cannot use protected capabilities until an administrator enables it.
4. Administrators can access all projects. Normal users can access only explicitly assigned projects and only their own future business records unless a later spec grants more.
5. The first administrator is created by an idempotent local CLI command whose credentials come from environment variables, never command-line arguments.
6. Backend error messages and the new identity UI ship in Simplified Chinese and English. Simplified Chinese is the default.

## Objective

Deliver the smallest secure identity and access foundation that a real user can operate from the browser:

- self-registration, login, logout, current-session lookup, profile locale update, and password change;
- administrator account approval, rejection, enable/disable, and project assignment;
- database-backed opaque sessions with server-side revocation;
- two-role and project-scope authorization enforced by backend dependencies;
- append-only audit records for identity and permission changes;
- a React/TypeScript application shell with login, registration, pending-account, user home, user approval, and audit pages;
- stable bilingual error codes/resources that later modules reuse.

Success means an unapproved visitor cannot enter the system, an approved user can see only assigned projects, an administrator can manage the lifecycle from the Web UI, and all security-sensitive transitions are testable and auditable.

## Out of Scope

- Email/SMS delivery, password-reset email, invitations, OAuth/OIDC, SSO, MFA, WebAuthn, LDAP, or Active Directory.
- Custom roles, per-field policies, organization/tenant hierarchy, or a generic policy engine.
- Full project/site management; v1.1 creates only the minimal project record needed for access assignment. Rich project/site fields remain in `operations-insights` v1.5.
- Dashboard, detection, alert, dataset, model, LLM, and desktop-offline business screens.
- Long-lived API tokens for third-party integrations.

## Tech Stack

### Backend

- Python 3.11.16, FastAPI 0.141.1, Pydantic Settings 2.15.0, SQLAlchemy 2.0.52, Alembic 1.19.1, PostgreSQL 17, and Redis 8 from v1.0.
- `pwdlib[argon2]==0.3.1` for password hashing. `PasswordHash.recommended()` currently selects Argon2; the implementation stores only encoded hashes.
- Python standard-library `secrets` generates opaque session tokens and `hashlib.sha256` creates the stored token digest.
- No JWT package, authentication framework, ORM wrapper, or policy-engine dependency.

### Frontend

- Node.js 24.19.0 LTS (latest Windows Conda Forge build available during v1.1 implementation), React/React DOM 19.2.8, TypeScript 6.0.3, Vite 8.2.2, and React Router 8.3.1. TypeScript 7 was not forced because the approved lint toolchain currently requires `<6.1`.
- Vitest 4.1.11 plus React Testing Library for focused component tests; exact transitive versions are locked in `frontend/package-lock.json`.
- A small typed locale resource module is sufficient for v1.1; do not add a general i18n framework until message volume or pluralization requires it.
- Native `fetch`, HTML controls, CSS, and browser validation are preferred over API clients, component suites, form frameworks, or global state libraries.

## Commands

```powershell
conda activate infrasentinel

# Install/update all Python and Node runtime prerequisites
conda env update -n infrasentinel -f environment.yml --prune
Push-Location frontend
npm ci
Pop-Location

# Database migration
python -m alembic upgrade head
python -m alembic downgrade -1
python -m alembic upgrade head

# First administrator (values are read from .env/process environment)
python -m infrasentinel.cli init-admin

# Backend verification
python -m pytest -q --basetemp runtime/pytest-v1.1 -p no:cacheprovider
ruff check src tests scripts/verify_environment.py alembic

# Frontend development and verification
Push-Location frontend
npm run dev
npm run test -- --run
npm run lint
npm run build
Pop-Location

# Integrated application
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
powershell -ExecutionPolicy Bypass -File scripts/health.ps1
```

## Project Structure

```text
src/infrasentinel/
  auth.py              # password and opaque-session primitives
  dependencies.py      # current-user, role, and project-scope guards
  errors.py            # stable error envelope and locale selection
  identity_api.py      # auth, profile, and administrator routes
  models.py            # identity/access/audit SQLAlchemy models
  schemas.py           # request/response contracts
  services.py          # lifecycle operations and audit writes
  cli.py               # health plus idempotent init-admin command

alembic/versions/      # v1.1 identity/access migration

frontend/
  src/api/             # native-fetch boundary and typed API errors
  src/auth/            # session context and route guards
  src/i18n/            # zh-CN/en resource maps and locale helper
  src/pages/           # login, register, pending, home, users, audit
  src/styles/          # tokens and accessible industrial-dark styling
  src/test/            # shared frontend test setup

tests/
  test_auth.py         # password/session primitives
  test_identity_api.py # lifecycle and authorization API behavior
  test_audit.py        # immutable audit behavior and redaction
```

Files may be combined when that reduces indirection without mixing unrelated responsibilities. No repository/service interface is required when one concrete implementation suffices.

## Data Model

All identifiers are UUIDs and all timestamps are timezone-aware UTC.

### `users`

- `id`, normalized unique `email`, normalized unique `username`, `display_name`
- `password_hash`; plaintext passwords never reach logs, audit JSON, or responses
- `role`: `admin | user`
- `status`: `pending | enabled | disabled | rejected`
- `locale`: `zh-CN | en`
- `reviewed_by`, `reviewed_at`, optional `rejection_reason`
- `last_login_at`, `created_at`, `updated_at`

### `auth_sessions`

- `id`, `user_id`, unique `token_hash`, `created_at`, `last_seen_at`, `expires_at`, `revoked_at`
- diagnostic `source_ip` and bounded `user_agent`
- raw session tokens are returned only as cookies and are never stored

### `projects`

- Minimal v1.1 boundary: `id`, unique `code`, `name`, `status: active | disabled`, `created_at`, `updated_at`
- v1.5 extends this record with site/asset/OBS metadata without replacing its identity

### `project_memberships`

- `user_id`, `project_id`, `assigned_by`, `created_at`
- unique pair `(user_id, project_id)`
- only `user` accounts require memberships; administrators bypass project membership checks

### `audit_events`

- `id`, nullable `actor_id` for system/bootstrap events, `source_ip`, bounded `user_agent`
- `action`, `target_type`, optional `target_id`, redacted `before_state`, redacted `after_state`, `result`, `created_at`
- application code exposes insert and query only; a PostgreSQL trigger rejects update/delete
- passwords, hashes, cookies, session tokens, API keys, and authorization headers are always removed before persistence

## Authentication and Security Contract

### Registration and passwords

- Registration accepts email, username, display name, password, and locale.
- Email is lowercased and validated; username is lowercased and limited to 3-32 ASCII letters, digits, `.`, `_`, and `-`.
- Password length is 6-128 characters. Spaces are allowed; arbitrary composition rules are not imposed.
- Duplicate email/username returns one generic conflict code without identifying which field belongs to an existing account.
- New registrations are always `role=user`, `status=pending`; request payloads cannot override role or status.

### Login and sessions

- Login accepts email-or-username plus password and returns the same generic invalid-credentials error for unknown identifiers and wrong passwords; unknown users still run a dummy Argon2 verification.
- Correct credentials for `pending`, `disabled`, or `rejected` accounts return a stable status-specific error but create no session.
- A successful login creates a 32-byte opaque random token. Only its SHA-256 digest is stored.
- Cookie name: `infrasentinel_session`; `HttpOnly`, `SameSite=Lax`, path `/`; `Secure` is mandatory in production and disabled only for the approved local HTTP deployment.
- Sessions expire after 30 minutes idle or 7 days absolute. Successful authenticated requests may advance `last_seen_at` at most once every 5 minutes.
- Logout revokes the current session. Password change, account disable/reject, or role change revokes every session for that user.
- Unsafe cookie-authenticated requests require a same-origin `Origin` or `Referer`; wildcard CORS with credentials is forbidden.
- Redis fixed-window limits login failures to 10 per 15 minutes per normalized identifier plus source IP, and registration to 5 per 15 minutes per source IP. If Redis is unavailable, these endpoints return a localized 503 rather than silently disabling the limit.

### Authorization

- Every protected backend endpoint resolves the session and account status server-side.
- `require_admin` checks `role=admin`; no frontend-only authorization is accepted.
- Project-scoped dependencies allow administrators globally and require a matching membership for normal users.
- Object ownership remains an additional check in later modules: project membership alone never grants access to another user's private record unless that module's spec explicitly permits it.

### Bootstrap administrator

`python -m infrasentinel.cli init-admin` reads:

- `INFRASENTINEL_BOOTSTRAP_ADMIN_EMAIL`
- `INFRASENTINEL_BOOTSTRAP_ADMIN_USERNAME`
- `INFRASENTINEL_BOOTSTRAP_ADMIN_PASSWORD`
- optional display name and locale

The command creates one enabled administrator and a system audit event. Re-running with the same normalized email/username succeeds without changing the password; conflicting identity or role fails clearly. Values are never printed.

## API Contract

All routes are under `/api/v1`.

| Method and path | Access | Behavior |
|---|---|---|
| `POST /auth/register` | Public, rate-limited | Create pending user; return 201 and safe profile |
| `POST /auth/login` | Public, rate-limited | Create session cookie; return current safe profile |
| `POST /auth/logout` | Authenticated | Revoke current session and clear cookie; idempotent 204 |
| `GET /auth/me` | Authenticated | Return safe profile, role, status, locale, assigned projects |
| `PATCH /auth/me` | Authenticated | Update display name and locale only |
| `POST /auth/change-password` | Authenticated | Verify old password, replace hash, revoke all sessions |
| `GET /projects` | Authenticated | Admin: all; user: assigned active projects |
| `POST /admin/projects` | Admin | Create minimal project record |
| `GET /admin/users` | Admin | Paginated/filterable safe user list |
| `PATCH /admin/users/{user_id}/status` | Admin | Enable, disable, or reject with optional reason |
| `PUT /admin/users/{user_id}/projects/{project_id}` | Admin | Idempotently assign project |
| `DELETE /admin/users/{user_id}/projects/{project_id}` | Admin | Idempotently remove project |
| `GET /admin/audit-events` | Admin | Cursor-paginated, filterable audit stream |

Status changes must prevent the last enabled administrator from disabling or rejecting itself. API list defaults are 50 items and cap at 200.

## Error and Internationalization Contract

Errors use a stable machine-readable envelope:

```json
{
  "error": {
    "code": "auth.invalid_credentials",
    "message": "用户名或密码错误",
    "request_id": "019...",
    "fields": null
  }
}
```

- Locale order: authenticated user's preference, then supported `Accept-Language`, then `zh-CN`.
- Error codes, enum values, and field names never change with locale.
- Validation errors are converted into this envelope and use safe field-level messages.
- Every response carries `X-Request-ID`; a valid inbound request ID may be reused, otherwise the server generates one.
- Frontend text and status labels come only from typed `zh-CN` and `en` resource maps with identical keys.

## Frontend Experience

- `/login` and `/register`: compact, keyboard-complete forms with explicit labels, visible validation, password visibility toggle, language switch, and no decorative animation that delays use.
- `/pending`: explains that administrator approval is required and offers logout/session refresh.
- `/app`: authenticated shell showing identity, role, locale, authorized projects, service status link, and clearly disabled future modules.
- `/admin/users`: pending-first table, safe filters, approval/rejection/disable actions, project assignment, confirmation for destructive status changes.
- `/admin/audit`: chronological filterable audit table; details render sanitized JSON, never raw HTML.
- Industrial-dark visual direction from the requirements: charcoal/navy surfaces, cyan operational accent, semantic risk colors, visible focus rings, minimum 4.5:1 normal-text contrast, and status conveyed by text/icon in addition to color.
- Layout supports 1280px desktop and 360px narrow browser widths. All actions are keyboard reachable and form errors are announced accessibly.
- Vite development proxies `/api` to `http://127.0.0.1:8090`. Production builds are served by FastAPI from `frontend/dist`, making UI and cookie API same-origin. `/docs` remains available; `/` serves the application after a production build.

## Code Style

Backend business rules live in small explicit functions with typed inputs and transactional database boundaries:

```python
def require_project_access(user: User, project_id: UUID, memberships: set[UUID]) -> None:
    if user.role != UserRole.ADMIN and project_id not in memberships:
        raise ForbiddenError("auth.project_access_denied")
```

Frontend components use typed props and native controls; visible text is a locale key:

```tsx
export function LanguageSwitch({ locale, onChange }: Props) {
  return (
    <select aria-label={t(locale, "settings.language")} value={locale} onChange={onChange}>
      <option value="zh-CN">简体中文</option>
      <option value="en">English</option>
    </select>
  );
}
```

- Python: Ruff formatting/lint rules already configured, explicit return types, UTC-aware timestamps, no wildcard imports.
- TypeScript: strict mode, function components, named exports, no `any`, no business logic in JSX event handlers.
- Domain enums and error codes are centralized once; do not duplicate string literals across routes and pages.

## Testing Strategy

### Backend unit tests

- Password hash/verify, dummy verification path, token digesting, expiry, locale selection, safe audit redaction, and role/project guards.
- Use dependency injection or direct pure functions; unit tests remain runnable without Docker.

### PostgreSQL/Redis integration tests

- Migration upgrade/downgrade/upgrade.
- Registration uniqueness and status defaults; bootstrap idempotency.
- Login/session creation, idle/absolute expiry, logout, password-change revocation, disabled-account revocation.
- Approval/rejection and last-admin protection.
- Project membership visibility and admin bypass.
- Audit append-only trigger and secret redaction.
- Rate limits and localized 429/503 responses.

### Frontend tests

- Login/register validation and safe API-error rendering.
- Route guards for anonymous, pending, user, and admin sessions.
- Locale switch has full key parity and persists through profile update.
- Administrator approval and project assignment workflows with mocked HTTP responses.
- Production build succeeds with no TypeScript errors.

### Manual acceptance

1. Bootstrap an administrator from environment variables.
2. Register a normal account in Chinese, verify it cannot enter, approve it as admin, and log in.
3. Create two projects, assign only one, and confirm the normal account sees only that project.
4. Disable the account and confirm its active browser session is rejected on the next request.
5. Switch both UI and API errors to English.
6. Confirm the audit page contains registration, login, approval, assignment, password/status changes without secrets.

## Boundaries

### Always

- Normalize identity fields, validate every trust boundary, use parameterized ORM statements, and enforce authorization in backend dependencies.
- Hash passwords with Argon2 and store only session-token digests.
- Revoke sessions on security-sensitive identity changes.
- Audit every registration, login result, logout, approval/status change, password change, project assignment, and bootstrap action.
- Run backend and frontend tests, lint, build, migration cycle, and secret/large-file checks before the v1.1 milestone.

### Ask first

- Adding another role, authentication mechanism, external identity provider, email service, or public-network deployment.
- Changing cookie/session lifetime, password policy, rate-limit defaults, or the project-access rule.
- Adding dependencies beyond those named in this spec.
- Changing the schema or public routes beyond the tables/endpoints listed here.

### Never

- Commit `.env`, credentials, raw cookies/tokens, password hashes from real users, datasets, media, or weights.
- Return password hashes, token hashes, internal SQL errors, or sensitive audit fields through the API.
- Trust a role, status, project id, or user id supplied by the browser without server-side resolution.
- Disable CSRF-origin checks, TLS verification, password hashing, audit redaction, or authorization to simplify testing.
- Update or delete audit events.

## Success Criteria

- [x] A single Alembic migration creates the five v1.1 tables, constraints, indexes, and audit immutability trigger; upgrade/downgrade/upgrade passes.
- [x] Bootstrap CLI creates exactly one enabled administrator without exposing its password.
- [x] Public registration always creates a pending normal user; role/status injection is rejected or ignored safely.
- [x] Login uses Argon2 verification, generic invalid-credential errors, rate limiting, and opaque database sessions.
- [x] Cookie flags, expiry, revocation, origin checks, and account-status enforcement match this spec.
- [x] Normal users see only assigned projects; administrators have global access; backend tests prove both paths.
- [x] Administrators can manage user status and memberships from API and Web UI; the last enabled administrator is protected.
- [x] Audit events are append-only, queryable only by administrators, localized at presentation time, and demonstrably free of secrets.
- [x] Every backend error and every v1.1 UI string has matching `zh-CN` and `en` resources.
- [x] Anonymous, pending, user, and admin browser routes behave correctly at desktop and 360px widths with keyboard-visible focus.
- [x] Full Python tests, Ruff, frontend tests/lint/build, `pip check`, Compose validation, and live readiness all pass.
- [x] `AGENT.md`, requirements deviations, commands, and v1.1 verification evidence are updated before commit/tag/push.

## Open Questions

None. The assumptions above use the user's approved defaults. Any later change to roles, session policy, password recovery, or public deployment requires a spec update before implementation.
