# StructAgent Decision OS demo

This is a dependency-free, interactive hackathon demo. It uses a small, synthetic
fashion-retail-shaped placeholder and does not connect to a database, call RT-J, or report real
model results. It does exchange versioned schema, task, run, and evaluation fixtures with
the local API. The mock workspace is stored in the browser so that setup progress and
objective records survive a refresh.

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

Run the deterministic API and interaction-model tests with `make test` and `make test-web`.
