# StructAgent Decision OS demo

This is a dependency-free, interactive hackathon demo. It uses a small, synthetic
fashion-retail-shaped placeholder and does not connect to a database, call RT-J, or report real
model results. It exchanges versioned contracts with the local API and can explicitly launch
either reviewed default against synthetic data in Daytona. The mock workspace is stored in
the browser so that setup progress and objective records survive a refresh.

Run the API and web app in separate terminals from the repository root:

```bash
make serve-api
make serve-web
```

Then open <http://127.0.0.1:4173>. The app uses prerequisite-based access for data
connections, business knowledge, objectives, and experiments. Customer Insights and
Decision Studio live inside the objective that produced them. Multiple objective
records can be created and revisited independently. The supported demo objective follows
the V1 seven-day article-sales regression contract. An objective that cannot be backed
by the connected data branches into a data-collection plan instead of unlocking the
simulated inference view.

The frontend boundary also includes:

- versioned JSON Schemas in `contracts/v1/schemas`;
- Amazon and H&M example journeys in `contracts/v1/examples`;
- `GET http://127.0.0.1:8000/v1/datasets/rel-hm`; and
- `GET http://127.0.0.1:8000/v1/tasks/defaults?dataset_id=rel-hm`;
- `POST http://127.0.0.1:8000/v1/materializations/daytona`.

The default-task response is represented by
`contracts/v1/schemas/default-task-catalog.schema.json`, with a matching example at
`contracts/v1/examples/rel-hm/default-tasks.json`. The stable task IDs, in display order,
are `rel-hm/user-churn` and `rel-hm/item-sales`.

Catalog entries use `source: "default"`; draft-task fixtures use `source: "custom"`.
`benchmark_metric` names the pinned RelBench scoring metric, while
`diagnostic_metrics` lists the additional metrics planned for StructAgent evaluation.

The live catalog is still marked `fixture: true` and has an implementation status of
`metadata_only`. Every example result remains synthetic. The UI must preserve a visible
demo/fixture treatment and must not present task metadata, metrics, run state, provenance,
or integrity checks as observed model behavior.

Default catalog access makes no language-model or compute-provider call. A click on either
reviewed task explicitly approves synthetic Daytona SQL materialization; the provider key
remains in the API environment, and the response arrives only after artifact verification
and sandbox deletion. This path does not transfer private H&M data or run RT-J. The separate
task-draft, run, and result routes remain fixture-backed preview contracts.

Run the deterministic API and interaction-model tests with `make test` and `make test-web`.
