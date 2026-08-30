# StructAgent

StructAgent is the working name for an interactive StructureML research demo that will
translate natural-language prediction questions into reviewed, executable contracts for
foundational models on structured data.

StructureML is an independent research initiative. It is not currently incorporated,
and no trademark registration or employer affiliation is claimed.

## Status

This repository is a lightweight monorepo. It currently contains a typed API, a metadata-only
H&M task catalog, guarded default-task materialization, versioned interface fixtures, a
dependency-free frontend demo, and documented extension points for a future task compiler
and RT-J execution worker.

Implemented today:

- a typed FastAPI application with health, catalog, synthetic Daytona materialization, and
  fixture-backed V1 demo routes;
- reviewed customer-churn and article-sales definitions in the H&M default-task catalog;
- strict V1 Pydantic contracts with generated JSON Schemas;
- validated, synthetic Amazon classification and H&M regression interface journeys;
- an interactive Decision OS frontend demo;
- reviewed, normalized DuckDB SQL for both H&M defaults behind a read-only SQL policy;
- deterministic local materialization into model-visible train, validation, and masked-test
  packages plus evaluator-owned test truth;
- checksum-verified staging of the approved, revision-pinned private H&M snapshot;
- opt-in SQL materialization in a private ephemeral Daytona CPU sandbox, with network
  blocking, output validation, parity checks, and verified cleanup; and
- explicit, synthetic-only Daytona launches from the frontend for either reviewed default;
- explicit placeholders for the OpenAI task compiler and Modal RT-J worker.

It does not yet:

- call a language model;
- expose private H&M materialization or model-run orchestration through HTTP;
- download or execute RT-J on Modal;
- ingest arbitrary databases;
- generate custom prediction tasks; or
- report observed model predictions or evaluation metrics.

`apps/web` contains a dependency-free interactive Decision OS demo for the hackathon
journey. Its fashion retail content is a small synthetic placeholder; its SQL database,
Snowflake, Redshift, and BigQuery connection choices are mock UI only. The demo connects
to reviewed synthetic contracts served by the local API and can explicitly request bounded
synthetic Daytona materialization. It does not add database or model integrations.

See [architecture](docs/architecture.md), [product flow](docs/product-flow.md), the
[H&M backend roadmap](docs/backend-roadmap.md), the isolated
[RT-J inference feasibility tests](docs/rtj-inference-feasibility.md), and
[data and licensing boundaries](docs/data-and-licensing.md).

## Development

The supported developer interface is Make:

```bash
make sync
make hooks
make check-all
make serve-api
make serve-web
make contracts-check
make test-materializer
make materialize-hm-local
```

The local API listens on `http://127.0.0.1:8000`. Alongside `GET /healthz`, it serves the
reviewed H&M metadata and default-task catalog plus task-draft, run, and evaluation fixtures
under `/v1` for frontend integration. `POST /v1/materializations/daytona` launches one or two
explicitly approved reviewed tasks against generated H&M-shaped data. It requires
`DAYTONA_API_KEY` only in the ignored server environment and does not execute RT-J.

The frontend demo will listen on `http://127.0.0.1:4173`.

## Testing the H&M default tasks

The commands below always exercise both reviewed defaults:

- `rel-hm/user-churn`: seven-day customer-level binary classification;
- `rel-hm/item-sales`: seven-day article-level regression, including zero-sales articles.

Run the deterministic policy, materializer, asset, Daytona-adapter, and parity unit tests:

```bash
make test-materializer
```

Materialize both tasks locally against generated H&M-shaped data without credentials or
network access:

```bash
make materialize-hm-local
```

The command prints one validation status and package digest per task. Model-visible train,
validation, and masked-test files are kept separate from evaluator truth beneath
`.artifacts/runs/<timestamp>-local-synthetic/tasks/{user-churn,item-sales}/`. The entire
`.artifacts/` tree is ignored by Git.

To exercise the same two-task workflow in an ephemeral Daytona CPU sandbox, place
`DAYTONA_API_KEY` in the ignored local `.env` file and run:

```bash
make materialize-hm-daytona-smoke
```

The private pinned-data parity run is deliberately separate and permission-gated:

```bash
make hm-data-sync
make hm-data-verify
STRUCTAGENT_ALLOW_REAL_HM=1 make materialize-hm-daytona-live
```

The live command requires the explicit acknowledgement shown above, verifies both outputs
against the pinned official label files, transfers only checksum-verified inputs, and deletes
the sandbox after execution. It is never part of CI. None of these commands runs a model:
Modal remains the planned GPU boundary for RT-J inference.

## Repository workflow

The first push is the sole direct push permitted to `main`. Every later change must use
a focused branch and reviewed pull request. Pull requests must not be merged without
explicit approval from Tony Kwok.

## License

Original StructAgent code is licensed under the [MIT License](LICENSE). Third-party
models, source code, and datasets retain their own terms and are not relicensed by this
repository.
