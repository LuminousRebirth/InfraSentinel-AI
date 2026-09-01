# v1.0 Task Ledger

- [x] Task: Create repository and Conda baseline
  - Acceptance: layout, ignore rules, package metadata and `environment.yml` exist; protected assets are excluded.
  - Verify: `conda env update -n infrasentinel -f environment.yml --prune`; ignore-pattern checks.
  - Files: `.gitignore`, `environment.yml`, `pyproject.toml`, `README.md`

- [x] Task: Implement typed configuration and safe storage paths
  - Acceptance: environment-driven settings load without secrets; path traversal outside storage roots is rejected.
  - Verify: focused Pytest unit tests.
  - Files: application configuration/storage modules and tests

- [x] Task: Establish PostgreSQL schema and migrations
  - Acceptance: SQLAlchemy session works; the initial migration creates platform metadata and can downgrade.
  - Verify: Alembic upgrade/downgrade against Compose PostgreSQL.
  - Files: database modules, Alembic configuration and initial migration

- [x] Task: Add dependency health API
  - Acceptance: liveness is unconditional; readiness reports each dependency and storage without leaking credentials.
  - Verify: API unit tests plus optional integration test.
  - Files: FastAPI main/health modules and tests

- [x] Task: Add pinned Docker and Windows lifecycle tooling
  - Acceptance: PostgreSQL, Redis and Milvus standalone dependencies have health checks and persistent volumes; scripts do not hard-code Conda paths.
  - Verify: `docker compose config`; PowerShell parser checks; live health when Docker is available.
  - Files: `compose.yaml`, `deploy/*`, `scripts/*.ps1`

- [x] Task: Preserve reusable YOLO26 Demo code
  - Acceptance: only source/config/tests are copied; CLI and weight-free tests retain behavior; no dataset/model/output files enter the repository.
  - Verify: existing unit tests and Git ignore checks.
  - Files: `src/vision_inspection/*`, selected `configs/*`, selected `tests/*`

- [x] Task: Review and record v1.0 evidence
  - Acceptance: tests and configuration validation pass; security/dependency review has no unresolved high-severity finding; handoff ledger is current.
  - Verify: recorded commands and results in `AGENT.md`.
  - Files: `AGENT.md`, task ledger, release notes if approved for commit
