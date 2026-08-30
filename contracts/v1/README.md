# StructAgent V1 contracts

These files are versioned frontend integration artifacts backed by synthetic demo routes.

- Pydantic models in `apps/api/src/structagent_api/contracts` are the source of truth.
- `schemas/` contains deterministic JSON Schema snapshots.
- `examples/` contains metadata-only or synthetic placeholder messages.
- `make contracts-export` regenerates schemas.
- `make contracts-check` rejects schema drift.

The API serves the reviewed H&M examples through `GET /v1/datasets/rel-hm`,
`POST /v1/task-drafts`, `GET /v1/runs/{run_id}`, and
`GET /v1/runs/{run_id}/evaluation`. These are deterministic demo responses, not database
ingestion, task compilation, RT-J execution, or observed model results.
