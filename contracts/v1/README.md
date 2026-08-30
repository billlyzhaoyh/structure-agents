# StructAgent V1 contracts

These files define the V1 frontend boundary. The H&M dataset and default-task catalog
schemas have matching metadata routes, while selected synthetic examples back deterministic
demo routes.

- Pydantic models in `apps/api/src/structagent_api/contracts` are the source of truth.
- `schemas/` contains deterministic JSON Schema snapshots.
- `examples/` contains metadata-only or synthetic placeholder messages.
- `make contracts-export` regenerates schemas.
- `make contracts-check` rejects schema drift.

Implemented catalog routes:

- `GET /v1/datasets/rel-hm`;
- `GET /v1/tasks/defaults?dataset_id=rel-hm`.

Both responses remain explicitly metadata-only. The API also serves selected reviewed H&M
examples through `POST /v1/task-drafts`, `GET /v1/runs/{run_id}`, and
`GET /v1/runs/{run_id}/evaluation`. These are deterministic demo responses, not database
ingestion, task compilation, materialization, RT-J execution, or observed model results.

Implemented internal materialization boundaries:

- `task-sql-artifact.schema.json` describes reviewed SQL, its normalized digest, provenance,
  and static validation evidence;
- `materialization-result.schema.json` describes the separated model-input and evaluator-truth
  packages, file digests, invariant report, and package provenance.

These contracts are currently consumed by local services and Make-driven scripts, not by a
public API route.
