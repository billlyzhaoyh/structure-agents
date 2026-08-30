# Architecture

## Current implementation

StructAgent currently consists of ten implemented pieces:

1. a Python 3.12 `uv` workspace;
2. a FastAPI shell exposing health, H&M catalog, and fixture-backed V1 demo routes;
3. a reviewed, revision-pinned H&M default-task catalog;
4. versioned Pydantic contracts, generated JSON Schemas, and synthetic fixtures;
5. a dependency-free Decision OS frontend that consumes those demo contracts;
6. a guarded DuckDB materializer that separates model input from evaluator truth; and
7. an opt-in Daytona CPU executor for private, ephemeral SQL materialization; and
8. a synthetic-only HTTP bridge and frontend controls for either reviewed H&M default;
9. a guarded OpenAI and Daytona natural-language task compiler; and
10. a disabled-by-default local HTTP bridge for one bounded observed `user-churn` Modal run.

Arbitrary-database adapters, durable run orchestration, observed `item-sales` and custom-task
inference, and production deployment of paid inference do not exist yet.

```text
apps/web/                 contract-backed demo workspace
        |
        | V1 metadata, synthetic Daytona requests, simulated or bounded observed evaluation
        v
apps/api/                 trusted catalog, compiler, materialization, and inference controls
        |
        | reviewed default task definitions
        v
materialization/          guarded SQL + local DuckDB materializer
        |
        | local execution or private ephemeral upload
        v
Daytona                   CPU-only SQL execution [implemented by CLI + synthetic API route]
        |
        | verified model-visible task package
        v
workers/rtj/ + Modal      bounded private user-churn inference

contracts/v1/             generated schemas + validated frontend fixtures
```

The SQL, Snowflake, Redshift, and BigQuery choices remain mock UI. The API does not ingest an
arbitrary database or run an approved custom task. A local-only route can call RT-J for one
bounded reviewed cohort and return sanitized observed evaluation; browser code receives no
provider credentials, task rows, truth, predictions, or artifact paths.

## Contract-backed demo boundary

The frontend reads the reviewed H&M relational descriptor and both default tasks. An explicit
button click can launch either default against generated H&M-shaped data in Daytona and render
only sanitized materialization evidence after cleanup. Customer churn can use a separately
configured real materialization for a 32-customer observed Modal run; article sales and custom
task previews remain simulated and fixture-backed. Business knowledge, scenario
interventions, and experiments remain browser-side demo state because public contracts for
those modules do not exist yet.

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
   |-- natural-language custom-task compiler [implemented for draft + validation]
   |-- guarded SQL policy and deterministic materializer [defaults implemented]
   |-- explicit synthetic-materialization approval [implemented]
   |-- explicit local approval + budget gate [implemented for bounded churn]
   |-- durable authenticated approval [planned]
   |
   v
Daytona SQL execution plane
   |-- private, ephemeral H&M inputs [implemented by opt-in CLI]
   |-- generated synthetic H&M-shaped inputs [implemented by HTTP route]
   |-- read-only task materialization [implemented for defaults]
   |-- model/evaluator artifact separation [implemented]
   |
   v
Modal GPU execution plane
   |-- RT-J classification inference [implemented for bounded churn]
   |-- regression and custom-task inference [planned]
   |-- sealed prediction output [implemented]
   |
   v
Trusted evaluator
   |-- one-to-one truth alignment [implemented]
   |-- point-in-time and leakage checks [implemented for reviewed materialization]
   |-- batch metrics and provenance [implemented]
```

OpenAI, Daytona, and Modal credentials remain in the trusted control-plane environment.
Browser code receives none of them. Daytona is limited to CPU-based SQL materialization; it
does not receive model source, checkpoints, or GPU work. The Modal worker receives only the
model-visible task package and approved model assets. Predictions are sealed before evaluator
truth is joined.

The reviewed H&M `user-churn` and `item-sales` definitions can be materialized without a
language-model call through local services and scripts. The synchronous synthetic HTTP route
accepts only those reviewed IDs and returns after verified sandbox deletion. Private pinned
H&M inputs remain configured server-side; the opt-in local Modal route accepts only a fixed
32-customer `user-churn` request. Custom tasks are limited to customer or article entity
prediction, binary classification or regression, and horizons from one through seven days.
The OpenAI agent submits DuckDB SQL only through guarded tools; it does not receive general
sandbox shell access or raw H&M rows.

The fixture-backed route shapes are exercised by the frontend. The route shapes, milestone
boundaries, test plans, and definitions of done are in the
[backend roadmap](backend-roadmap.md). The catalog and guarded materialization milestones are
implemented. Authentication, arbitrary databases, full-split inference, production
persistence, streaming, and paid-inference deployment are still deferred.
