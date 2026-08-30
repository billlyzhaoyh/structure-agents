# RT-J worker placeholder

This directory reserves the future isolated RT-J execution boundary. It intentionally
contains no Python package, container image, Daytona configuration, model source,
checkpoint, dataset, or runnable inference code.

The planned worker will eventually receive an approved, versioned task contract plus
external asset references and return sealed batch predictions with execution metadata.
Evaluation truth and metric computation stay outside model context construction.

Before worker implementation begins, the project must separately approve:

- the exact RT-J source and checkpoint revisions and their permitted use;
- classification and regression adapter contracts;
- database preprocessing and point-in-time validation;
- context construction, resource limits, and failure behavior;
- Daytona image, GPU, volume, secret, timeout, and cleanup policies; and
- prediction/evaluation artifact retention.

The Daytona API key belongs only in the trusted API control plane. OpenAI credentials
must not be sent to the execution sandbox. No external asset may be committed here.
