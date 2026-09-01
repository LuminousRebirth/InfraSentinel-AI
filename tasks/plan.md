# v1.0 Implementation Plan: platform-foundation

## Dependency graph

1. Repository and environment baseline has no internal dependency.
2. Typed configuration depends on the repository layout.
3. Storage, database and service probes depend on typed configuration.
4. FastAPI health endpoints depend on all probes.
5. Docker Compose and Windows scripts provide the external services used by integration verification.
6. Existing vision code is migrated independently, then verified together with the new backend.

## Build sequence

1. Initialize repository metadata, ignore rules, package layout and `environment.yml`.
2. Add configuration and local-storage safety primitives with unit tests.
3. Add database session/base metadata, platform tables and Alembic migration.
4. Add Redis/Milvus/PostgreSQL/storage probes and versioned FastAPI health endpoints.
5. Add pinned dependency Compose stack and Windows lifecycle scripts.
6. Copy the reusable vision package/config/tests while excluding all user assets and generated files.
7. Run unit/config tests, then optional Docker-backed integration checks.
8. Review security, dependency surface and documentation; update `AGENT.md`.

## Risks and mitigations

- Docker Desktop may not be running: keep unit tests independent and report readiness per dependency.
- Milvus has transitive etcd/MinIO services: use the official standalone topology and pin its release.
- CUDA/TensorRT packages are host-sensitive: keep them in an optional environment section and preserve PT fallback.
- The old Demo contains hard-coded absolute paths: migrate only package code and replace runtime paths with typed configuration in later vision work.
- Conda and PowerShell locations vary: use `conda run` and command discovery, never `D:\Anaconda` in scripts.

## Verification checkpoints

- Baseline: environment file parses and repository exclusions cover all protected assets.
- Core: unit tests pass without Docker or model weights.
- Data services: `docker compose config` passes; health probes degrade cleanly before startup and become ready after startup.
- Migration: Alembic upgrade/downgrade cycle succeeds on the local PostgreSQL container.
- Regression: existing weight-free vision tests pass from the new repository.
