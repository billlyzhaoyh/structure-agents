# Private RT-J execution on Modal

Status: approved for a private, non-commercial hackathon demonstration only.

The approved execution boundary uses:

- Relational Transformer source revision
  `455df27c1458e093eac00133d5bbf41a8263a2e3`;
- RT-J checkpoint revision `a2c204c79d493ed0056661140e6fd24db3118381`;
- `sentence-transformers/all-MiniLM-L12-v2` revision
  `a50ef00143b4d5391434df20ae11632588ac25be`; and
- the revision-pinned private-use RelBench H&M snapshot already documented in this
  repository.

This approval does not grant commercial-use or redistribution rights. The RT-J checkpoints
declare CC BY-NC-SA 4.0, while the inspected Relational Transformer revision has no root
licence. Source, weights, H&M data, contexts, predictions, evaluator truth, and observed
results must not be committed, redistributed, or published.

## Security and evaluation boundary

Daytona remains the CPU-only SQL materialization plane. Modal receives the three verified
H&M database tables plus model-visible train, validation, and masked test task files. It
never receives `test-truth.parquet`, OpenAI credentials, Daytona credentials, or the Modal
controller token.

The pinned RT preprocessor requires the target column to exist in every task split. The
worker therefore adds a fixed zero-valued target column to a private copy of each masked test
file. This is a schema compatibility placeholder, not a label. Real test targets remain in
the trusted controller and are joined only after predictions have been sealed and downloaded.

The current live acceptance path covers a deterministic balanced 32-customer `user-churn`
cohort. For a larger run, a deterministic 512-row preflight measures elapsed time and cost;
the controller projects the full run with a 1.5 safety factor and fails closed if the combined
projection exceeds 16 hours or USD 25. Full-split acceptance for both reviewed defaults remains
future work. Live execution is always opt-in and outside CI.
