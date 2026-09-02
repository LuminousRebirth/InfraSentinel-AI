# v1.3 Task Ledger: alert-intelligence

- [x] Task 1: Freeze v1.3 defaults, spec, plan and ledger
  - Acceptance: risks, grouping, workflow, LLM degradation, security and deferred scope are explicit.
  - Verify: document review; `git diff --check`.

- [x] Task 2: Add models and reversible migration
  - Acceptance: all v1.3 tables encode constraints, ownership and indexes.
  - Verify: model/PostgreSQL migration tests and round trip.

- [x] Task 3: Seed deterministic default rules
  - Acceptance: six pipeline medium and one no-helmet high rule upsert without overriding edits.
  - Verify: repeat seed test/live CLI.

- [x] Task 4: Implement event grouping and idempotent backfill
  - Acceptance: image objects remain distinct; video/OBS class/time/IoU grouping is deterministic.
  - Verify: pure boundary tests and repeat backfill.

- [x] Task 5: Implement rule evaluation and alert creation
  - Acceptance: project precedence, confidence, no-match and one-alert behavior work; rule remains final authority.
  - Verify: service and completed-job tests.

- [x] Task 6: Implement authorization and workflow
  - Acceptance: owner/assignee/admin scope, assignment, versioned transitions, close note, deadlines, override reason and actions are transactional/audited.
  - Verify: state/access/concurrency tests.

- [x] Task 7: Add encrypted provider credentials
  - Acceptance: system/personal keys encrypt, replace/delete safely and never appear in responses/audit.
  - Verify: encryption/redaction/rotation tests.

- [x] Task 8: Implement bounded structured adapter
  - Acceptance: endpoint/redirect/timeout/size/schema rules handle fake success and failures.
  - Verify: fake HTTP transport tests.

- [x] Task 9: Implement analysis queue and worker
  - Acceptance: auto/manual lease, wait, retry/fail/succeed work without altering severity.
  - Verify: fake-provider worker tests and lifecycle.

- [x] Task 10: Integrate completed/live detections
  - Acceptance: new completion/periodic OBS refresh and old backfill are idempotent.
  - Verify: worker integration and repeat live backfill.

- [x] Task 11: Add alert/rule/provider/credential APIs
  - Acceptance: bounded authorized routes, valid transitions and write-only config are localized/audited.
  - Verify: API role matrix and invalid inputs.

- [x] Task 12: Add safe evidence attachments
  - Acceptance: bounded type/hash/storage, authorized download and action record work.
  - Verify: upload/corrupt/traversal/access tests.

- [x] Task 13: Add typed bilingual alert foundation
  - Acceptance: routes/nav/contracts/status/level resources have zh-CN/en parity.
  - Verify: route/i18n tests and TypeScript build.

- [x] Task 14: Build alert center and detail
  - Acceptance: filters, evidence, LLM state, workflow, assignment, notes/attachments are responsive/keyboard operable.
  - Verify: components, lint/build and browser review.

- [x] Task 15: Build admin rule/provider and personal credential UI
  - Acceptance: bounded rule form and write-only key controls expose errors and never echo secrets.
  - Verify: components and browser review.

- [x] Task 16: Run integrated v1.3 acceptance
  - Acceptance: migration, seed/backfill, fake provider, workflow, authorization, full regression and no-key live flow pass.
  - Verify: spec commands and recorded evidence.

- [x] Task 17: Review, document and push development branch only
  - Acceptance: no critical/required finding, current evidence/deviations, no secrets/large files, main/tag untouched.
  - Verify: five-axis review, full rerun, refs/status.
