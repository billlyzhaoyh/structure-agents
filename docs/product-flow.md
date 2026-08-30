# Product flow

StructAgent's intended hackathon story ends at evaluated batch predictions. Enterprise
decision optimization, reinforcement learning, and contextual bandits remain future
research directions and are not represented as working features.

## H&M journeys

Reviewed defaults and natural-language custom tasks share one execution path after task
review. Default tasks do not call a language model.

### Reviewed defaults

1. **Select a task** — choose H&M customer churn or article sales from the reviewed catalog.
2. **Review the task** — inspect the pinned entity, horizon, target, and evaluation contract.
3. **Approve execution** — explicitly approve materialization and compute spend.
4. **Materialize** — create the model-visible package and separately sealed truth through the
   implemented local path, CLI path, or frontend-triggered synthetic Daytona path.
5. **Run and evaluate** — the local-only `user-churn` path can invoke the reviewed RT-J head
   on a deterministic 32-customer cohort, seal predictions, and return batch metrics and
   provenance after cleanup. `item-sales` remains simulated in the frontend.

### Custom tasks

1. **Inspect H&M** — use the reviewed customer, article, and transaction schema.
2. **Describe intent** — ask a natural-language prediction question.
3. **Clarify semantics** — resolve material ambiguity in the entity, eligibility cohort,
   prediction time, one-to-seven-day horizon, label, and output type.
4. **Validate SQL** — the trusted OpenAI agent submits a candidate DuckDB task-table query
   through guarded Daytona tools. Only sanitized errors and aggregate evidence return to the
   model.
5. **Review the task** — inspect the typed contract, SQL, and validation evidence.
6. **Approve execution** — explicitly approve materialization and compute spend.
7. **Run inference** — future orchestration applies the guarded materializer to the approved
   custom SQL, then invokes an approved RT-J classification or regression checkpoint on Modal
   without feature engineering or task-specific model training.
8. **Evaluate** — align sealed predictions with evaluator-owned truth, run integrity checks, and
   report task-appropriate batch metrics and provenance.

## Current catalog and fixture coverage

- `rel-hm`: the metadata-only catalog exposes reviewed customer-churn and article-sales
  defaults. Article sales includes every known article and zero-fills articles without a
  transaction in the future window. Both reviewed defaults have guarded SQL, deterministic
  synthetic coverage, private artifact verification, opt-in Daytona materialization, and a
  synthetic frontend launch for either reviewed task and an opt-in observed `user-churn`
  evaluation backed by separately configured private artifacts.
- `rel-amazon`: customer churn remains a deferred binary-classification reference fixture.

Observed inference is limited to the bounded private `user-churn` cohort. The remaining
journey fixtures test interface shape only: their metrics are deliberately synthetic, their
integrity checks are `not_run`, and their query artifacts contain no SQL.

## Deferred beyond V1

Recommendation tasks, horizons longer than seven days, arbitrary database ingestion,
production persistence, real-time progress transport, authentication, model-context tuning,
and deployment architecture remain deferred. See the
[backend roadmap](backend-roadmap.md) for the decided V1 route and contract direction.
