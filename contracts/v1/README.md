# StructAgent V1 contracts

These files are frontend integration artifacts, not live API responses.

- Pydantic models in `apps/api/src/structagent_api/contracts` are the source of truth.
- `schemas/` contains deterministic JSON Schema snapshots.
- `examples/` contains metadata-only or synthetic placeholder messages.
- `make contracts-export` regenerates schemas.
- `make contracts-check` rejects schema drift.

The API currently exposes only `GET /healthz`. No task-drafting or run endpoint serves
these messages yet.
