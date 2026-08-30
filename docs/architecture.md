# Architecture

## Current implementation

StructAgent currently consists of seven implemented pieces:

1. a Python 3.12 `uv` workspace;
2. a FastAPI shell exposing health, H&M catalog, and fixture-backed V1 demo routes;
3. a reviewed, revision-pinned H&M default-task catalog;
4. versioned Pydantic contracts, generated JSON Schemas, and synthetic fixtures;
5. a dependency-free Decision OS frontend that consumes those demo contracts;
6. a guarded DuckDB materializer that separates model input from evaluator truth; and
7. an opt-in Daytona CPU executor for private, ephemeral SQL materialization.

The natural-language task compiler, arbitrary-database adapters, Modal RT-J worker, live run
orchestration, and model-evaluation runtime do not exist yet.

```text
apps/web/                 contract-backed demo workspace
        |
        | V1 metadata, task, run, and evaluation fixtures
        v
apps/api/                 health + H&M catalog + synthetic contract routes
        |
        | reviewed default task definitions
        v
materialization/          guarded SQL + local DuckDB materializer
        |
        | local execution or private ephemeral upload
        v
Daytona                   CPU-only SQL execution [implemented by opt-in CLI]
        |
        | future model-visible task package
        v
workers/rtj/ + Modal      GPU inference placeholders

contracts/v1/             generated schemas + validated frontend fixtures
```

The SQL, Snowflake, Redshift, and BigQuery choices remain mock UI. The API does not ingest a
database, compile a live task, call RT-J, or report observed results. Browser code receives no
provider credentials.

## Contract-backed demo boundary

The frontend reads the reviewed H&M relational descriptor, submits a V1 task-draft request,
and renders the matching synthetic run and evaluation records. The supported journey follows
the seven-day article-sales regression fixture. Business knowledge, scenario interventions,
and experiments remain browser-side demo state because public contracts for those modules do
not exist yet.

## Why a lightweight monorepo

The frontend and backend can be deployed independently while reviewing their shared
messages in one repository. The root Makefile is the stable developer interface and the
root `uv.lock` reproduces all Python packages. The repository does not need Turborepo,
Nx, Supabase, a JavaScript workspace, or multiple Python lockfiles at this stage.

The engineering foundation adapts the useful repository discipline from the local
`ai-project-cookiecutter`: strict typing, locked dependencies, deterministic tests,
pre-commit and pre-push gates, read-only CI permissions, and dependency automation. It
does not inherit the cookiecutter's Supabase or Vite application assumptions.

## H&M control and compute planes

The following separates the implemented catalog boundary from later control-plane and
compute milestones:

```text
Frontend
   |
   v
Trusted API control plane
   |-- reviewed H&M schema and default-task catalog [implemented]
   |-- natural-language custom-task compiler [planned]
   |-- guarded SQL policy and deterministic materializer [defaults implemented]
   |-- human approval and budget gate [planned HTTP workflow]
   |
   v
Daytona SQL execution plane
   |-- private, ephemeral H&M inputs [implemented by opt-in CLI]
   |-- read-only task materialization [implemented for defaults]
   |-- model/evaluator artifact separation [implemented]
   |
   v
Modal GPU execution plane
   |-- RT-J classification or regression inference [planned]
   |-- sealed prediction output [planned]
   |
   v
Trusted evaluator
   |-- one-to-one truth alignment [planned for model predictions]
   |-- point-in-time and leakage checks [planned]
   |-- batch metrics and provenance [planned]
```

OpenAI, Daytona, and Modal credentials remain in the trusted control-plane environment.
Browser code receives none of them. Daytona is limited to CPU-based SQL materialization; it
does not receive model source, checkpoints, or GPU work. A future Modal worker will receive
only the model-visible task package and approved model assets. Predictions must be sealed
before evaluator truth is joined.

The reviewed H&M `user-churn` and `item-sales` definitions can be materialized without a
language-model call through local services and scripts. No materialization HTTP endpoint or
model execution exists. Custom tasks are limited by the planned V1 contract to customer or
article entity prediction, binary classification or regression, and horizons from one
through seven days. The OpenAI agent may eventually submit DuckDB SQL only through guarded
tools; it will not receive general sandbox shell access or raw H&M rows.

The fixture-backed route shapes are exercised by the frontend. The route shapes, milestone
boundaries, test plans, and definitions of done are in the
[backend roadmap](backend-roadmap.md). The catalog and guarded materialization milestones are
implemented. Authentication, arbitrary databases, model inference, production persistence,
streaming, and deployment are still deferred.
