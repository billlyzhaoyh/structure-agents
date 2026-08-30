# StructAgent

StructAgent is the working name for an interactive StructureML research demo that will
translate natural-language prediction questions into reviewed, executable contracts for
foundational models on structured data.

StructureML is an independent research initiative. It is not currently incorporated,
and no trademark registration or employer affiliation is claimed.

## Status

This repository is a lightweight monorepo. The initial version contains only a
health-check API, versioned interface fixtures, and documented extension points for a
future frontend, task compiler, and RT-J execution worker.

Implemented today:

- `GET /healthz` in a typed FastAPI application shell;
- strict V1 Pydantic contracts with generated JSON Schemas;
- validated, synthetic Amazon classification and H&M regression UI journeys; and
- explicit placeholders for the frontend and isolated RT-J worker.

It does not yet:

- call a language model;
- connect to Daytona;
- download or execute RT-J;
- ingest a database;
- generate prediction tasks; or
- report real model results.

See [architecture](docs/architecture.md), [product flow](docs/product-flow.md), the
[H&M backend roadmap](docs/backend-roadmap.md), the isolated
[RT-J inference feasibility tests](docs/rtj-inference-feasibility.md), and
[data and licensing boundaries](docs/data-and-licensing.md).

## Development

The supported developer interface is Make. After the bootstrap milestone:

```bash
make sync
make hooks
make check-all
make serve-api
make contracts-check
```

The local API will listen on `http://127.0.0.1:8000`; its implemented endpoint will be
`GET /healthz`.

No frontend development server or port is configured. Frontend contributors can start
from the schemas and clearly marked fixtures under `contracts/v1` without provider keys.

## Repository workflow

The first push is the sole direct push permitted to `main`. Every later change must use
a focused branch and reviewed pull request. Pull requests must not be merged without
explicit approval from Tony Kwok.

## License

Original StructAgent code is licensed under the [MIT License](LICENSE). Third-party
models, source code, and datasets retain their own terms and are not relicensed by this
repository.
