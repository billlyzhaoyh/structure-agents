# Private RT-J Modal worker

This package implements the network-isolated inference boundary for the two reviewed H&M
defaults. Source, model weights, data, and predictions remain ephemeral and are never
committed to this repository.

The worker receives six digest-verified, model-visible Parquet files. It creates a private
copy of masked test rows with a zero-valued placeholder target because RT's task-table
preprocessor requires that column. Evaluator truth and metric computation stay outside the
container and are never uploaded.

The Modal credential belongs only in the trusted API control plane. OpenAI and Daytona
credentials are not function secrets or environment variables. See
[`docs/rtj-modal.md`](../../docs/rtj-modal.md) for the fixed protocol and permission boundary.
