# Product flow

StructAgent's intended hackathon story ends at evaluated batch predictions. Enterprise
decision optimization, reinforcement learning, and contextual bandits remain future
research directions and are not represented as working features.

## Planned H&M journeys

Reviewed defaults and natural-language custom tasks share one execution path after task
review. Default tasks do not call a language model.

### Reviewed defaults

1. **Select a task** — choose H&M customer churn or article sales from the reviewed catalog.
2. **Review the task** — inspect the pinned entity, horizon, target, and evaluation contract.
3. **Approve execution** — explicitly approve materialization and compute spend.
4. **Run and evaluate** — materialize the pinned task, invoke the matching RT-J head, seal
   predictions, and report batch metrics and provenance.

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
7. **Run inference** — a future worker materializes train, validation, masked test, and sealed
   truth artifacts, then invokes an approved RT-J classification or regression checkpoint
   without feature engineering or task-specific model training.
8. **Evaluate** — align sealed predictions with evaluator-owned truth, run integrity checks, and
   report task-appropriate batch metrics and provenance.

## Current catalog and fixture coverage

- `rel-hm`: the metadata-only catalog exposes reviewed customer-churn and article-sales
  defaults. Article sales includes every known article and zero-fills articles without a
  transaction in the future window.
- `rel-amazon`: customer churn remains a deferred binary-classification reference fixture.

The catalog records pinned definitions and metrics but no observed execution. The remaining
journey fixtures test interface shape only: their metrics are deliberately synthetic, their
integrity checks are `not_run`, and their query artifacts contain no SQL.

## Deferred beyond V1

Recommendation tasks, horizons longer than seven days, arbitrary database ingestion,
production persistence, real-time progress transport, authentication, model-context tuning,
and deployment architecture remain deferred. See the
[backend roadmap](backend-roadmap.md) for the decided V1 route and contract direction.
