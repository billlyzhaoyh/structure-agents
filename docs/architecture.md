# Architecture

## Current implementation

StructAgent currently consists of four implemented pieces:

1. a Python 3.12 `uv` workspace;
2. a FastAPI shell exposing health and fixture-backed V1 demo routes;
3. versioned Pydantic contracts, generated JSON Schemas, and synthetic fixtures; and
4. a dependency-free Decision OS frontend that consumes those demo contracts.

```text
apps/web/                 contract-backed demo workspace
        |
        | V1 metadata, task, run, and evaluation fixtures
        v
apps/api/                 health route + synthetic contract routes
        |
        | future approved run bundle
        v
workers/rtj/              documentation placeholder

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

## Planned control and compute planes

The following remains a direction for later milestones, not implemented behavior:

```text
Frontend
   |
   v
Trusted API control plane
   |-- reviewed H&M schema and default-task catalog
   |-- natural-language custom-task compiler
   |-- guarded SQL validation tools
   |-- deterministic validation
   |-- human approval and budget gate
   |
   v
Isolated execution plane
   |-- read-only H&M task materialization
   |-- RT-J classification or regression inference
   |-- sealed prediction output
   |
   v
Trusted evaluator
   |-- one-to-one truth alignment
   |-- point-in-time and leakage checks
   |-- batch metrics and provenance
```

OpenAI and Daytona credentials remain in the trusted API process. Browser code receives
neither. The execution worker receives only narrowly scoped inputs required for an
approved run. Predictions must be sealed before evaluator truth is joined.

The planned V1 supports the reviewed H&M `user-churn` and `item-sales` defaults without a
language-model call. Custom tasks are limited to customer or article entity prediction,
binary classification or regression, and horizons from one through seven days. The OpenAI
agent may submit DuckDB SQL only through guarded tools; it does not receive general sandbox
shell access or raw H&M rows.

The fixture-backed route shapes are now exercised by the frontend, but the execution
milestones, test plans, and definitions of done remain in the backend roadmap.
Authentication, arbitrary databases, production persistence, streaming, and deployment
are still deferred.
