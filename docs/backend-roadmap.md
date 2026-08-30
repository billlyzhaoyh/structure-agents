# H&M backend roadmap

This document defines the backend delivery sequence for the first executable StructAgent
demo. Milestone 1 implements metadata-only catalog behavior, and Milestone 2 implements
guarded materialization of the reviewed defaults. Milestones 3 through 5 remain plans rather
than descriptions of working model execution.

## Product boundary

V1 focuses on RelBench H&M and supports two paths:

```text
Reviewed default task -------------------------+
                                                |
Natural language -> clarification -> task SQL -+-> task materialization
                                                        |
                                                        v
                                              RT-J zero-shot inference
                                                        |
                                                        v
                                                sealed evaluation
```

The reviewed defaults are:

- `rel-hm/user-churn`: customer-level binary classification over seven days;
- `rel-hm/item-sales`: article-level regression over seven days.

Default tasks never call a language model. Custom tasks may predict a binary or numeric
target for a customer or article over a horizon from one through seven days. Recommendation,
multiclass, intervention, causal, policy-learning, and longer-horizon tasks are outside V1.

The seven-day maximum preserves RelBench H&M's temporal contract. Its validation and test
cutoffs are seven days apart, and the standard task lifecycle requires the prediction horizon
to fit within that interval. Moving the cutoffs would create a different derived benchmark.

The OpenAI agent remains in the trusted API process. It can submit candidate SQL only through
narrow validation and materialization tools. Daytona receives reviewed SQL and scoped files,
not the OpenAI API key. Modal receives approved model assets and the model-visible task
package, not a natural-language prompt or evaluator truth.

## External permission gates

Technical feasibility does not grant permission to use or redistribute external assets.
The H&M materialization decision recorded on 2026-08-30 approves the pinned
`stanford-star/relbench-v1` revision
`d8e976fd0a4b78877204bc8dfbcfc9a9f7f48600` for private research and hackathon
demonstration only. It does not approve redistribution, production use, or public data and
results. The current Daytona account cannot access persistent volumes, so the approved
implementation uploads checksum-verified files to a private ephemeral sandbox for each run.

Before the RT-J milestone starts, also record an approved decision for:

- the exact Relational Transformer source revision and its permitted use;
- the exact RT-J classification and regression checkpoints and their terms;
- storage and execution of the runtime and model assets in private Modal infrastructure.

The released RT-J checkpoints are currently marked CC BY-NC-SA 4.0, and the inspected
Relational Transformer source revision did not contain a root licence. Keep the repository's
[data and licensing boundaries](data-and-licensing.md) current. No source, weights, raw data,
task tables, predictions, or evaluator truth may be committed.

## Milestone 1 - H&M catalog and reviewed defaults

Status: implemented.

Branch: `feat/hm-task-catalog`

Ordered commits:

1. `feat: define H&M task catalog contracts`
2. `test: add H&M default task fixtures`
3. `docs: document frontend task catalog handoff`

Implementation:

- Make `rel-hm` the active V1 dataset while retaining Amazon fixtures as deferred reference
  material.
- Define stable default task IDs and pin the reviewed upstream task artifacts and digests.
- Add planned catalog routes `GET /v1/datasets/rel-hm` and
  `GET /v1/tasks/defaults?dataset_id=rel-hm`.
- Add a discriminated task source of `default` or `custom` for later run requests.
- Preserve explicit fixture and provenance markers until observed execution exists.

Test plan:

- Validate the exact entity, time, target, horizon, task type, and metrics for both defaults.
- Reject unknown, duplicate, recommendation, and non-H&M default tasks.
- Verify the generated JSON Schemas and OpenAPI surface.
- Prove the catalog works without provider credentials or network calls.

Definition of done:

- The frontend can list and select both defaults through stable contracts.
- The definitions match revision-pinned RelBench artifacts.
- `make check-all` passes and no provider dependency has been introduced.

## Milestone 2 - Guarded H&M task materialization

Status: implemented.

Branch: `feat/hm-task-materialization`

Ordered commits:

1. `docs: separate Daytona SQL from Modal inference`
2. `feat: define task materialization contracts`
3. `feat: add guarded H&M task SQL policy`
4. `feat: add guarded DuckDB task materializer`
5. `feat: stage pinned H&M artifacts outside Git`
6. `feat: add ephemeral Daytona SQL execution`
7. `test: verify default task materialization parity`
8. `fix: verify Daytona SQL runtime before upload`
9. `docs: document local H&M materialization workflow`

Implementation:

- Define a `TaskSqlArtifact` containing DuckDB SQL, entity and target columns, task type,
  one-to-seven-day horizon, normalized-query digest, provenance, and validation report.
- Supply the query with reviewed H&M tables and a deterministic `timestamps` relation based
  on the official validation/test cutoffs and horizon-stepped training schedule.
- Require exactly `timestamp`, the declared entity ID, and the declared target in query output.
- Parse SQL before execution. Permit read-only selections, CTEs, joins, filters, aggregates,
  and reviewed functions. Reject DDL, DML, `COPY`, `ATTACH`, `INSTALL`, `LOAD`, pragmas,
  filesystem/network functions, and undeclared tables or columns.
- Execute against a read-only H&M database in a private Daytona CPU sandbox. Upload scoped,
  checksum-verified inputs for each run and delete the ephemeral sandbox afterward. Revisit a
  private persistent volume only if the Daytona account gains volume access.
- Validate uniqueness by `(timestamp, entity)`, complete outcome windows, non-empty splits,
  finite targets, binary `0/1` labels, class balance, null rates, and bounded row counts.
- Materialize full labels, then separate model-visible support labels, masked test task rows,
  and evaluator-owned sealed test truth.

Test plan:

- Exercise H&M-shaped synthetic data locally and through a fake Daytona adapter.
- Reject unsafe SQL, hallucinated schema references, duplicate rows, incomplete future windows,
  invalid binary targets, non-finite regression targets, and empty splits.
- Materialize both pinned default queries and compare their schemas, row counts, target
  statistics, and digests with reviewed artifacts.
- Keep one credentialed Daytona materialization smoke opt-in, permission-gated, and outside CI.

Definition of done:

- Both defaults produce valid RT-compatible task packages without OpenAI.
- Test truth cannot enter model-input construction.
- Sandbox cleanup is verified for success, rejection, timeout, and cancellation.
- Raw or generated data remains untracked and `make check-all` passes.

## Milestone 3 - Default RT-J vertical slice

Branch after the external permission gate: `feat/hm-rtj-defaults`

Ordered commits:

1. `feat: add RT-J H&M worker adapter`
2. `feat: add sealed batch evaluator`
3. `test: verify default RT-J run contracts`

Implementation:

- Build a private, revision-pinned Modal GPU image for the approved RT runtime.
- Transfer only the model-visible task package and approved dataset inputs to Modal; evaluator
  truth remains in the trusted evaluation boundary.
- Route `user-churn` to the approved classification checkpoint and `item-sales` to the
  approved regression checkpoint.
- Consume the exact task packages produced by the materializer. Do not perform task-specific
  feature engineering, gradient training, or checkpoint modification.
- Seal per-row predictions before joining evaluator truth.
- Report classification metrics for churn and regression metrics for item sales, with dataset,
  source, checkpoint, snapshot, query, context, and runtime provenance.

Test plan:

- Use a fake model for deterministic prediction alignment and metric tests.
- Cover checkpoint/task mismatch, missing rows, duplicates, point-in-time failures, cleanup,
  and regression de-normalization.
- Run a small credentialed live cohort for each default outside CI.
- Verify prediction ordering against the pinned task rows.

Definition of done:

- Both default tasks complete from reviewed selection to evaluated predictions.
- Prediction/entity/timestamp alignment is mechanically verified.
- Every result is identified as observed, synthetic, or failed.
- The milestone does not start until the permission gate is recorded.

## Milestone 4 - Natural-language custom task compiler

Branch: `feat/hm-custom-task-agent`

Ordered commits:

1. `feat: add H&M custom task clarification contracts`
2. `feat: add guarded OpenAI SQL compiler`
3. `test: add custom task compiler evals`

Implementation:

- Add planned routes `POST /v1/task-drafts` and
  `POST /v1/task-drafts/{draft_id}/clarifications`.
- Keep continuation stateless: resubmit the original prompt, prior questions, and typed answers.
- Require explicit entity, eligibility cohort, target semantics, aggregation or condition,
  target type, and a horizon from one through seven days.
- Return a typed unsupported outcome when the request cannot map to an executable V1 task.
- Use one OpenAI Agents SDK agent in the trusted API. Give it only schema inspection, static
  SQL validation, sandbox query testing, and aggregate validation-evidence tools.
- Allow one initial query plus at most two repair attempts.
- Return only sanitized SQL errors, column metadata, row counts, null rates, and target
  balance or range to the model. Never return raw H&M rows.
- Require human review of the task semantics, SQL, and validation evidence before execution.

Test plan:

- Use a deterministic fake agent for complete prompts, ambiguous cohorts or targets,
  unsupported tasks, invalid horizons, unsafe SQL, hallucinated columns, repair success,
  repair exhaustion, refusal, timeout, and provider failure.
- Keep live compiler cases opt-in and outside CI.
- Grade semantic and SQL validity rather than exact prose.
- Verify OpenAI and Daytona credentials never cross their trusted boundaries.

Definition of done:

- A custom request produces useful clarification, an explicit unsupported outcome, or a
  reviewed and validated task artifact.
- Generated SQL passes the same materializer and invariants as reviewed defaults.
- Default tasks still make no model call.
- Deterministic evals, schema checks, and `make check-all` pass.

## Milestone 5 - Approved asynchronous workflow

Branch: `feat/hm-run-orchestration`

Ordered commits:

1. `feat: add approved asynchronous run lifecycle`
2. `feat: connect H&M tasks to execution and evaluation`
3. `test: verify default and custom product journeys`

Implementation:

- Add planned routes:
  - `POST /v1/runs` creates an `awaiting_approval` run;
  - `POST /v1/runs/{run_id}/approve` accepts explicit approval and a runtime ceiling;
  - `GET /v1/runs/{run_id}` supports polling;
  - `GET /v1/runs/{run_id}/evaluation` returns the final evaluation.
- Accept either a pinned default task ID or a complete validated custom task artifact.
- Revalidate custom SQL and its digest at the execution boundary; never trust browser status.
- Persist local demo state in SQLite behind a repository interface.
- Run the same materialization, inference, and sealed-evaluation path for both task sources.
- Defer SSE, authentication, arbitrary databases, production persistence, and deployment.

Test plan:

- Cover approval enforcement, state transitions, restart recovery, timeout, cancellation,
  tampered contracts, replay, sandbox cleanup, and terminal failures.
- Exercise both journeys with fake providers in CI.
- Keep one explicit credentialed H&M end-to-end smoke outside CI.

Definition of done:

- The frontend can run defaults without clarification.
- The frontend can compile, review, approve, run, and evaluate a custom task.
- No compute begins before approval, and terminal state survives API restart.
- Secrets, raw data, labels, and predictions remain absent from logs and Git.

## Delivery discipline

Each milestone starts from the latest approved `origin/main`, uses its own focused branch and
pull request, and remains independently reviewable. Every commit must leave the repository
valid and run the commit-level tests listed above. Every milestone ends with `make check-all`.
Pull requests are never merged without explicit approval from Tony Kwok.

Draft pull request #10 is non-production feasibility evidence for OpenAI/Codex credential
boundaries and a bounded Daytona canary. Production milestones may reuse validated findings,
but do not depend on merging or copying the spike wholesale. Codex is not a production provider.
