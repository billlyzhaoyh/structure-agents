# StructAgent

StructAgent is the working name for an interactive StructureML research demo that will
translate natural-language prediction questions into reviewed, executable contracts for
foundational models on structured data.

StructureML is an independent research initiative. It is not currently incorporated,
and no trademark registration or employer affiliation is claimed.

## Status

This repository is a lightweight monorepo. It currently contains a typed API, a metadata-only
H&M task catalog, guarded default-task materialization, a bounded natural-language task
compiler, versioned interface fixtures, a dependency-free frontend demo, a sealed RT-J
inference core, and guarded OpenAI, Daytona, and Modal provider boundaries.

Implemented today:

- a typed FastAPI application with health, catalog, and fixture-backed V1 demo routes;
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
- a revision-pinned RT-J H&M adapter, masked-test preparation, sealed evaluator, and
  deterministic classification/regression vertical slices; and
- a fakeable Modal controller enforcing exact uploads, isolation policy, preflight projection,
  a combined 16-hour/$25 ceiling, and cleanup across success and failure paths;
- a guarded OpenAI task compiler that can clarify, reject, or produce review-required custom
  H&M SQL after aggregate-only validation in one private Daytona sandbox; and
- a concrete undeployed Modal adapter using one anonymous volume, network-separated asset
  staging and inference functions, exact model uploads, bounded admission, and verified cleanup.

It does not yet:

- expose live materialization or run orchestration through HTTP;
- complete the paid full-split RT-J acceptance run for both reviewed tasks;
- ingest arbitrary databases;
- execute custom prediction tasks without human review; or
- report observed model predictions or evaluation metrics.

`apps/web` contains a dependency-free interactive Decision OS demo for the hackathon
journey. Its fashion retail content is a small synthetic placeholder; its SQL database,
Snowflake, Redshift, and BigQuery connection choices are mock UI only. The demo connects
to the local API. Catalog, run, and evaluation data remain fixtures; task drafting uses the
live compiler when configured and otherwise shows an explicit unavailable state.

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
make test-rtj
make test-compiler
make materialize-hm-local
```

The local API listens on `http://127.0.0.1:8000`. Alongside `GET /healthz`, it serves the
reviewed H&M metadata and default-task catalog plus run and evaluation fixtures under `/v1`.
Task-draft routes compile custom H&M tasks only when both provider credentials are configured;
otherwise they return a sanitized `503`. No route executes RT-J.

The frontend demo will listen on `http://127.0.0.1:4173`.

## Testing the task compiler

Run the deterministic compiler, guarded SQL, and API tests without credentials or network:

```bash
make test-compiler
```

For local live compilation, add `OPENAI_API_KEY` and `DAYTONA_API_KEY` only to the ignored
`.env`, verify the pinned H&M cache with `make hm-data-verify`, then start `make serve-api`.
OpenAI runs only in the trusted API and receives reviewed schema metadata plus sanitized
aggregate evidence. Daytona runs only the statically validated SQL in a private ephemeral CPU
sandbox. Generated tasks always require human review before later materialization or inference.

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

## Testing RT-J and the Modal boundary

Run the deterministic RT-J adapter, worker-preparation, sealed-evaluation, upload-isolation,
budget, and cleanup tests without credentials, model weights, or network access:

```bash
make test-rtj
```

The tests cover both reviewed H&M defaults at the fixed context-256 protocol. Deterministic
tests use synthetic predictions and do not claim observed model results. The live adapter is
opt-in and never runs in CI.

For local Modal authentication, prefer a profile stored outside the repository:

```bash
uv run modal token set --profile structure-agents
```

Set only `MODAL_PROFILE=structure-agents` in the ignored `.env`, then verify it with
`make modal-auth-check`. A headless trusted controller may instead receive
`MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` from its secret manager. These account credentials
must never be attached through `modal.Secret` or passed to the RT-J worker.

After `materialize-hm-daytona-live` succeeds, a bounded real-data classification cohort can
exercise the pinned RT-J source and checkpoint on an L4. Pass the pinned database directory,
the downloaded `user-churn` materialization directory, and a new ignored output directory:

```bash
STRUCTAGENT_ALLOW_REAL_HM=1 STRUCTAGENT_ALLOW_RTJ_MODAL=1 \
RTJ_DATASET_ROOT=.artifacts/rel-hm/<revision>/rel-hm/db \
RTJ_MATERIALIZATION_ROOT=.artifacts/runs/<daytona-run>/tasks/user-churn \
RTJ_OUTPUT_ROOT=.artifacts/runs/<new-rtj-run> \
make rtj-modal-live
```

The default is a deterministic balanced cohort of 32 real test entities. Modal receives the
three database tables, model-visible train/validation labels, and masked cohort rows; test
truth remains local and is joined only after predictions are downloaded and sealed. Private
predictions, metrics, and provenance are written below the ignored output directory. This is
an integration and resource smoke test, not a full-split quality benchmark.

RT-J use in this repository is limited to private, independent, non-commercial hackathon
research. The source licence remains unresolved; do not redistribute or publicly deploy the
source, weights, H&M data, predictions, or observed results.

## Repository workflow

The first push is the sole direct push permitted to `main`. Every later change must use
a focused branch and reviewed pull request. Pull requests must not be merged without
explicit approval from Tony Kwok.

## License

Original StructAgent code is licensed under the [MIT License](LICENSE). Third-party
models, source code, and datasets retain their own terms and are not relicensed by this
repository.
