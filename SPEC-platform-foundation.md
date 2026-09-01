# Spec: platform-foundation (v1.0)

## Objective

Create the smallest production-shaped foundation on which every approved InfraSentinel AI capability can be built without rewriting deployment, configuration, persistence, health or security basics.

The v1.0 result is not an end-user product. It is a reproducible Windows development/runtime baseline with a versioned FastAPI service, dependency health checks, an initial relational schema, local media-storage conventions, safe configuration handling, and preserved YOLO26 inference code.

## Confirmed assumptions

1. The project is a new repository rooted at `E:\python_code\InfraSentinel_AI`; the old repository at `E:\python_code\yolo` remains untouched.
2. Only reusable source, tests, and non-secret configuration are copied from the old Demo. Datasets, weights, engines, videos and run outputs remain local assets and are ignored by Git.
3. Windows 11 and an RTX 4060 Laptop GPU are the v1 acceptance host. Docker Desktop with WSL2 runs data services; the application runs in Conda on Windows.
4. The Conda environment is named `infrasentinel` and uses Python 3.11.
5. PostgreSQL is the business source of truth, Redis is the queue/status/cache dependency, and Milvus is deployed and health-checked only as a reserved RAG dependency.
6. Web clients are expected on the same LAN. Public hosting, production TLS certificates and internet exposure are outside v1.
7. Missing LLM credentials never block detection or rule processing; cloud adapters are implemented in `alert-intelligence`.

## Scope

### Included

- Repository layout, ignore rules, licensing carry-over and developer commands.
- Pinned `environment.yml` targeting the already-created `infrasentinel` environment.
- FastAPI application factory, `/api/v1/health/live` and `/api/v1/health/ready`.
- Typed environment configuration with no committed secrets.
- PostgreSQL connection layer and an initial migration for platform metadata/audit-ready identifiers.
- Redis and Milvus connectivity probes without business collections or RAG behavior.
- Local storage roots, path-containment validation and capacity configuration.
- Docker Compose for PostgreSQL, Redis and Milvus standalone dependencies.
- Windows PowerShell start, stop, initialization and health-check entry points.
- Migration of the existing `vision_inspection` package and its tests without changing CLI/inference behavior.

### Excluded

- Authentication screens or business permissions.
- Durable detection task execution, model loading through the platform, training or reports.
- React/Electron feature UI beyond directory ownership documentation.
- LLM calls, Agent/RAG collections, external alerts, backup/restore and public deployment.

## Tech stack

- Python 3.11.16 in Conda environment `infrasentinel`.
- Existing vision baseline: Ultralytics 8.4.117 and Torch 2.13.0/CUDA 13, installed only on GPU hosts.
- FastAPI 0.141.1, Uvicorn 0.52.1 and Pydantic Settings 2.15.0.
- SQLAlchemy 2.0.52, Alembic 1.19.1 and Psycopg 3.3.4.
- PostgreSQL 17.11, Redis 8.2.9 and Milvus standalone 2.6.22.
- Pytest 9.1.1 for Python verification.

Versions are explicit to make v1.0 reproducible. Dependency upgrades require a compatibility test and specification update.

## Commands

```powershell
# Create/update the environment
conda env update -n infrasentinel -f environment.yml --prune

# Run backend locally
conda run -n infrasentinel uvicorn infrasentinel.main:app --app-dir src --host 0.0.0.0 --port 8090

# Run tests
conda run -n infrasentinel python -m pytest -q

# Validate environment and configuration
conda run -n infrasentinel python scripts/verify_environment.py

# Start/stop dependencies
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
powershell -ExecutionPolicy Bypass -File scripts/stop.ps1

# Readiness check
powershell -ExecutionPolicy Bypass -File scripts/health.ps1
```

## Project structure

```text
src/infrasentinel/          FastAPI application and platform services
src/vision_inspection/      Preserved YOLO26 inference package
frontend/                   React application (implemented from v1.1 onward)
desktop/                    Electron host (implemented in v1.6)
alembic/                    PostgreSQL migrations
deploy/                     Docker dependency configuration
scripts/                    Windows lifecycle and verification scripts
tests/                      Unit and integration tests
runtime/                    Ignored local media/cache/model roots
tasks/                      Approved plans and task ledger
```

## Code style

Use typed Python, small domain modules, dependency injection only at real boundaries, and explicit error messages. Configuration is read once through a cached settings function.

```python
@router.get("/health/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse(status="ok", service="api")
```

- `snake_case` for Python functions/modules, `PascalCase` for types, kebab-case for module ids.
- Ruff-compatible formatting with a 100-character line target.
- API payloads use stable English field names; user-facing text comes from i18n resources in later modules.
- No generic repository/service abstraction until a second implementation proves it necessary.

## Testing strategy

- Unit tests cover configuration validation, safe storage paths and health aggregation without external services.
- Integration tests verify PostgreSQL/Redis/Milvus readiness when Docker services are available and are explicitly marked.
- Existing vision tests must continue to pass without requiring model weights.
- Configuration files are parsed in CI/local verification; Docker Compose is validated with `docker compose config`.
- v1.0 acceptance does not require downloading GPU packages or model weights if the preserved vision tests pass structurally.

## Boundaries

- Always: validate untrusted paths and configuration; keep secrets out of logs; use UTC timestamps and UUID identifiers; run tests before a milestone commit; preserve old Demo behavior.
- Ask first: change a database schema after approval; add a dependency; change Docker service versions; modify the old repository; push or tag a remote repository.
- Never: commit `.env`, API keys, passwords, media, datasets, weights, ONNX/TensorRT files or training outputs; silently weaken a failed readiness check; implement RAG business behavior in v1.

## Success criteria

1. `conda env update -n infrasentinel -f environment.yml --prune` resolves a Python 3.11 environment.
2. The API starts and exposes OpenAPI plus versioned liveness/readiness endpoints.
3. Readiness reports PostgreSQL, Redis, Milvus and storage independently, with readable degraded results.
4. Docker Compose configuration validates and pins every image version.
5. Secrets have example placeholders only; runtime settings reject unsafe production defaults.
6. Storage code prevents paths from escaping configured roots.
7. The initial migration upgrades and downgrades cleanly against the local PostgreSQL service.
8. Preserved vision unit tests and new foundation unit tests pass.
9. Windows scripts provide start, stop and health entry points without hard-coded Conda installation paths.
10. `AGENT.md` records commands, verification evidence, known limitations and the next module.

## Open questions

None. Product defaults and this module's boundaries were approved by the user on 2026-09-01. Cloud-model API credentials will be supplied later and are not needed for v1.0.
