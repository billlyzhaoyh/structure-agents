# Product flow

StructAgent's intended hackathon story ends at evaluated batch predictions. Enterprise
decision optimization, reinforcement learning, and contextual bandits remain future
research directions and are not represented as working features.

## Planned journey

1. **Select data** — choose a supported relational database and inspect its tables,
   primary keys, relationships, and time columns.
2. **Describe intent** — ask a natural-language prediction question.
3. **Clarify semantics** — resolve material ambiguity in the entity, eligibility cohort,
   prediction time, horizon, label, and output type.
4. **Review the task** — inspect the typed classification or regression contract. SQL
   artifacts remain `not_generated` in V1 fixtures.
5. **Approve execution** — explicitly approve materialization and compute spend.
6. **Run inference** — a future worker prepares context and invokes an approved RT-J
   endpoint without feature engineering or task-specific model training.
7. **Evaluate** — align sealed predictions with held-out truth, run integrity checks, and
   report task-appropriate batch metrics and provenance.

## Current fixture coverage

- `rel-amazon`: customer churn as a binary-classification example.
- `rel-hm`: article sales as a regression example.

These journeys test interface shape only. Their metrics are deliberately synthetic,
their integrity checks are `not_run`, and their query artifacts contain no SQL.

## Not yet decided

The frontend framework, API routes, answer-submission format, generated SQL contract,
arbitrary database ingestion, execution persistence, real-time progress transport,
authentication, model context policy, and deployment architecture will be decided in
the milestones that implement them.
