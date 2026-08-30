# RT-J inference feasibility tests

Date: 2026-08-30

Status: isolated, private, noncommercial feasibility evidence. This is not product
functionality, a performance benchmark, a model-quality result, or acceptance evidence for
the H&M backend milestones.

## Question tested

Can the pinned Relational Transformer runtime and RT-J classification checkpoint execute a
bounded zero-shot inference request on externally managed compute while keeping credentials
and model artifacts outside this repository?

The checks first used Daytona because it is the provider named in the current architecture.
After Daytona GPU allocation was blocked by account capacity, the same bounded request was
completed on a Modal GPU using the locally configured Modal CLI credential.

## Safety and permission boundary

- The work was authorized only as a private, noncommercial experiment.
- No OpenAI credential was used. Provider credentials remained in the trusted local
  controller and were not injected into an inference container.
- No source checkout, model weight, dataset content, context, entity identifier, label,
  prediction, or evaluator truth was committed or retained in this repository.
- Runtime source, checkpoint, and sample data were downloaded into ephemeral filesystems.
  No persistent Modal Volume was attached.
- Public availability did not resolve the external permission gate. The RT-J checkpoint is
  marked CC BY-NC-SA 4.0, and the inspected Relational Transformer revision has no root
  licence. See [data and licensing boundaries](data-and-licensing.md).

## Pinned inputs

| Input | Revision |
| --- | --- |
| [Relational Transformer source](https://github.com/stanford-star/relational-transformer) | `455df27c1458e093eac00133d5bbf41a8263a2e3` |
| [RT-J checkpoint repository](https://huggingface.co/stanford-star/rt-j) | `a2c204c79d493ed0056661140e6fd24db3118381` |
| [RelBench preprocessed snapshot](https://huggingface.co/datasets/stanford-star/relbench-preprocessed) | `1016626ddb30c027b92458bf866903850cc205e1` |

The sample used `rel-f1/driver-dnf`, the test split, the classification checkpoint, five
items, a context length of 128, and a local context length of 64. It asked for the
probability that each sampled Formula 1 driver would fail to finish the race. No natural
language prompt was passed to RT-J; this sentence only describes the structured task.

## Test record

### Daytona

Private CPU sandboxes were created to validate the lifecycle and runtime path. Requested
resize and custom-image configurations encountered organization plan limits. A larger CPU
attempt reached the inference path after correcting a dtype incompatibility, but CPU
execution did not complete within a useful smoke-test window and was cancelled.

A subsequent GPU request was rejected before sandbox creation because the organization had
no GPU credits. This is an infrastructure-capacity result, not an RT-J failure. Controller
cleanup ran after success, rejection, and cancellation paths; the test left no Daytona
sandbox running.

### Modal

The fallback used an ephemeral Modal app with:

- one NVIDIA L4 GPU;
- four CPUs and 8 GiB of memory;
- Python 3.12.10;
- PyTorch 2.13.0 with CUDA 13.0; and
- RT-J model parameters and inputs in bfloat16.

The reusable image contained public build and Python runtime dependencies only. The pinned
Relational Transformer source, checkpoint, and preprocessed sample were fetched at function
runtime rather than baked into that image.

The first function definition requested a custom 20 GiB ephemeral disk allocation, which
Modal rejected because custom reservations begin at a higher size. Removing the unnecessary
override allowed execution. Two later attempts completed remote inference but exposed
controller-reporting defects: one assumed a scalar evaluator count, and one returned a
PyTorch-specific version object that the local client could not deserialize. Returning a
plain JSON report removed that client/runtime coupling.

The final attempt completed and returned five finite classification probabilities within
the expected `[0, 1]` interval. The values themselves are intentionally not recorded here.
Observed timing for this single run was:

- model inference: 10.475 seconds; and
- total remote function time: 126.987 seconds, including setup and downloads.

These timings are one smoke observation, not a throughput, cost, latency, or capacity
benchmark. A post-run app audit showed all four smoke-test app records stopped with zero
active tasks.

## What the result establishes

- The pinned source and classification checkpoint can load and execute a bounded RT-J
  forward pass on a Modal L4.
- The selected software versions interoperate on the observed CUDA runtime.
- JSON is an appropriate narrow return boundary for a controller that does not share the
  worker's ML dependencies.
- Ephemeral execution can avoid persisting RT-J source, weights, input rows, and predictions
  in the repository or a provider volume.

## What the result does not establish

The run does not satisfy the [H&M backend roadmap](backend-roadmap.md):

- it used `rel-f1/driver-dnf`, not `rel-hm/user-churn` or `rel-hm/item-sales`;
- it exercised classification only, not the regression checkpoint;
- it did not consume an H&M task package produced by the guarded materializer;
- it did not seal predictions, join evaluator-owned truth, calculate task metrics, or verify
  entity/timestamp ordering;
- five short-context rows do not establish full-cohort memory, latency, cost, concurrency,
  timeout, or cancellation behavior; and
- The roadmap now assigns SQL materialization to Daytona and GPU inference to Modal; this
  feasibility run predates the approved split and remains non-production evidence.

The repository's [RT-J worker](../workers/rtj/README.md) therefore remains a placeholder.
This record does not authorize implementing that worker or starting Milestone 3.

## Required follow-up

1. Record the source, checkpoint, dataset, storage, retention, and permitted-use decisions
   required by the external permission gate.
2. Implement the approved Daytona SQL-to-Modal GPU artifact boundary without exposing sealed
   evaluator truth to inference.
3. Complete Milestone 2 and produce mechanically validated H&M task packages with sealed
   evaluator truth.
4. Run one bounded live cohort for each H&M default: churn classification and item-sales
   regression.
5. Verify prediction/entity/timestamp alignment, sealed evaluation, failure cleanup, and
   intended context and cohort resource ceilings before treating compute capacity as proven.
