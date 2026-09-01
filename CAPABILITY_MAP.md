# Capability Map: InfraSentinel AI

This map turns the approved v1.0-v1.6 milestones into stable module ids. The ids are permanent references for specifications, plans, tasks, migrations, and release notes.

| Module id | Milestone | Responsibility | Depends on |
|---|---:|---|---|
| `platform-foundation` | v1.0 | Repository baseline, Conda, configuration, local storage, PostgreSQL, Redis, Milvus reservation, health checks, security defaults | — |
| `identity-access` | v1.1 | Registration, approval, authentication, two-role authorization, project membership, i18n and audit foundation | `platform-foundation` |
| `vision-detection` | v1.2 | YOLO26 image, video and single OBS stream inference, durable tasks and records | `platform-foundation`, `identity-access` |
| `alert-intelligence` | v1.3 | LLM adapters, structured object analysis, rule grading, event merging, alerts and evidence chain | `identity-access`, `vision-detection` |
| `dataset-model-lifecycle` | v1.4 | Dataset/version management, annotation, quality checks, training, evaluation, publishing and rollback | `platform-foundation`, `vision-detection` |
| `operations-insights` | v1.5 | Dashboard, reports, projects/sites, health, cost controls and system settings | `alert-intelligence`, `dataset-model-lifecycle` |
| `desktop-offline` | v1.6 | Electron packaging, offline inference queue, idempotent synchronization and full deployment acceptance | `identity-access`, `vision-detection`, `alert-intelligence`, `operations-insights` |

Build order: `platform-foundation` → `identity-access` → `vision-detection` → (`alert-intelligence`, `dataset-model-lifecycle`) → `operations-insights` → `desktop-offline`.

Cross-cutting requirements such as security, auditability, accessibility, Chinese/English resources, unified errors and versioned APIs are implemented in the first module that needs them and retained by every later module.
