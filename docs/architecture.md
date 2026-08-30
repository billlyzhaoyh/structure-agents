# Architecture

## Current implementation

StructAgent currently consists of three implemented pieces:

1. a Python 3.12 `uv` workspace;
2. a FastAPI shell exposing only `GET /healthz`; and
3. versioned Pydantic contracts, generated JSON Schemas, and synthetic fixtures.

The web application, task compiler, database adapters, execution worker, and evaluation
runtime do not exist yet.

```text
apps/web/                 documentation placeholder
        |
        | future HTTP integration
        v
apps/api/                 health route + contract source models
        |
        | future approved run bundle
        v
workers/rtj/              documentation placeholder

contracts/v1/             generated schemas + validated frontend fixtures
```

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

The following is a direction for later milestones, not implemented behavior:

```text
Frontend
   |
   v
Trusted API control plane
   |-- schema inspection tools
   |-- natural-language task compiler
   |-- deterministic validation
   |-- human approval and budget gate
   |
   v
Isolated execution plane
   |-- database preprocessing
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

Concrete routes, persistence, streaming, authentication, deployment, provider models,
SQL dialect behavior, and sandbox configuration are deliberately deferred.
