# Simulation demo happy path

## Decision

The first end-to-end simulation shown in Decision Studio will be the reviewed
`rel-hm/promo-conjoint-v1` promotional-offer screening study.

This is the strongest first use case because its typed study, deterministic design, Daytona
boundary, EDSL execution seam, and canonical result contract already exist. It also produces a
decision the current product can describe honestly: which promotional offer profiles deserve a
later field experiment. It must not be presented as observed customer behavior, causal uplift,
incrementality, elasticity, revenue, or an expected percentage change.

The result shown in the browser will come from a completed, credentialed simulation run. It will
be cached only after contract validation, validation-gate evaluation, digest verification, and
sandbox cleanup. CI fixtures remain synthetic and can never populate the demo result cache.

## Current seam

The merged application currently has three separate pieces:

- the frontend can launch real synthetic H&M-shaped materialization in Daytona, but its model
  evaluation and Decision Studio percentages are fixture-backed or hard-coded;
- the API exposes the reviewed promotional study as metadata, but exposes no simulation-run
  route; and
- the simulation package can generate the full 400-agent, ten-task design and can execute three
  real EDSL responses for one task in Daytona, but it does not yet derive H&M personas, execute
  the full design, estimate effects, validate a result, or persist a terminal artifact.

The happy path joins these pieces without routing the simulation through the RT-J prediction
fixture. Prediction and simulation remain different evidence types attached to an objective.

## User journey

1. The operator connects the fashion-retail demo and defines the business guardrail.
2. In Objectives, the operator selects **Choose a promotional offer to field-test**.
3. Decision Studio loads the reviewed study card from
   `GET /v1/simulation-studies/defaults?dataset_id=rel-hm` and shows:
   - the eligible H&M customer population;
   - two offer alternatives plus no purchase;
   - the bounded offer attributes;
   - 400 simulated respondents and ten tasks per respondent; and
   - the limitation that the output is simulated screening evidence.
4. The operator selects **Run promotional offer screening**. Selecting a reviewed default is
   the execution approval; provider configuration and spend remain product-owned.
5. `POST /v1/simulation-runs` resolves the immutable study digest to a verified cached terminal
   run. The browser never receives credentials, raw rows, prompts, individual responses, or
   private artifact paths.
6. While the result is loading, the UI uses the existing store transition. A cache hit must be
   labelled as loading a verified prior run, not as starting a new sandbox.
7. Decision Studio shows validation before findings. A passing run may show:
   - up to three ranked promotional profiles;
   - rank stability;
   - suppressed or unsuppressed simulated-choice diagnostics; and
   - plain-language limitations.
8. A failed or stale hard gate shows why the recommendation was withheld and exposes no ranking.
9. The next action is **Stage a field experiment**. The product does not claim that the
   simulation has measured business impact.

The current hard-coded candidate-intervention percentages and “expected lift” scorecard are not
used in this journey. They must be removed from the simulation result view rather than relabelled
as model output.

## Actual-run and cache boundary

An artifact is eligible for the demo cache only when all of the following are true:

- it used the approved, checksum-verified RelBench H&M snapshot;
- personas were derived cutoff-safely from the approved aggregate trait projection;
- every admitted respondent call used the pinned EDSL and respondent-model versions;
- new-run responses were requested fresh rather than reused from the provider cache;
- the estimator and all required certification and run gates completed;
- the canonical `SimulationRunResult` validates and its digest matches the manifest; and
- the Daytona sandbox and temporary secret were synchronously deleted.

The product cache is distinct from the provider response cache. A refresh produces fresh model
responses, then stores the validated terminal result locally for replay during the demo.

The cache key is the digest of:

- study artifact and random seed;
- dataset revision and manifest digest;
- trait-query and persona-template digests;
- respondent model, EDSL, estimator, validation, and worker versions; and
- certification digest.

Changing any input produces a cache miss. Results are immutable beneath
`.artifacts/simulation-results/<cache-key>/`; an atomic latest pointer may select the current
approved artifact for the reviewed study. Generated results, individual responses, raw data,
and the local cache remain ignored by Git.

If the cache is absent, invalid, stale, or tampered with, the API returns a typed
`simulation_result_unavailable` response. It never falls back to the current fixture metrics or
hard-coded strategy claims.

## Minimal API contract

`POST /v1/simulation-runs` accepts only the reviewed study identity in the first slice:

```json
{
  "schema_version": "1",
  "study_artifact_id": "rel-hm/promo-conjoint-v1"
}
```

It returns a small envelope containing the cache disposition and the existing canonical
`SimulationRunResult`:

```json
{
  "schema_version": "1",
  "cache_status": "verified_hit",
  "result_digest": "sha256:<digest>",
  "result": {}
}
```

The trusted API resolves the cache root from server configuration, revalidates the JSON through
Pydantic, recomputes the digest, verifies the study ID and cache key, and returns only the
sanitized result. There is no browser-supplied artifact path, force-refresh flag, provider name,
or arbitrary study program.

Two operator-only commands manage the real artifact:

- `make simulation-demo-refresh` performs a new full credentialed run and atomically promotes a
  validated terminal artifact; and
- `make simulation-demo-verify` validates the current cached artifact without network access.

## Frontend result contract

The objective stores the selected study ID, terminal run ID, result digest, and sanitized result.
The primary view renders contract fields rather than generated prose:

- **Validation:** ready or recommendation withheld;
- **Population:** one H&M-conditioned eligible population, with no segmentation;
- **Shortlist:** complete promotional profiles and rank stability when permitted;
- **Diagnostics:** simulated-choice percentage-point estimates, clearly separated from business
  impact; and
- **Limitations:** always visible before the field-experiment action.

Infrastructure, model selection, token usage, provider billing, secret transport, and sandbox
IDs remain absent from the SaaS UI. The canonical backend provenance remains available for audit
and verification.

## Implementation slices

1. **H&M population package** — derive and test the approved aggregate traits at the reviewed
   cutoff, select 400 pseudonymous agents deterministically, and pin the dataset manifest.
2. **Full worker** — execute the 4,000 base choice tasks plus the declared sentinel repeats via
   EDSL in Daytona with checkpoints and bounded concurrency.
3. **Estimator and gates** — calculate population-level rankings and diagnostics, run the
   certification and per-run gates, and suppress rankings on any hard failure.
4. **Verified artifact cache** — write canonical immutable results and manifests atomically,
   verify digests on read, and add refresh/verify Make targets.
5. **Read API** — add the bounded simulation-run request/response contracts and the one reviewed
   cache-backed route with sanitized failure codes.
6. **Decision Studio path** — add the promotional-screening objective, study review, truthful
   cache-loading state, validation-first result view, and field-experiment handoff. Remove
   percentage uplift claims from this path.
7. **Credentialed acceptance run** — refresh the cache with the approved H&M snapshot and
   `gpt-5.6-luna`, verify cleanup and artifact digests, then rehearse the browser journey with
   network access disabled after the cache is warm.

## Acceptance criteria

- The browser can select exactly one implemented simulation use case and render a result produced
  by real EDSL respondent calls over H&M-derived aggregate personas.
- Reloading the same reviewed study returns the same immutable cached terminal artifact without
  making paid calls.
- A missing or invalid cache cannot produce a ranking or fall back to fixture claims.
- No browser response or log contains credentials, raw rows, customer identifiers, prompts,
  individual responses, or private paths.
- The result contains no uplift, incrementality, elasticity, revenue projection, or expected
  percentage claim.
- A hard validation failure returns no shortlist.
- The full credentialed refresh proves sandbox and temporary-secret cleanup; default CI remains
  deterministic and network-free.
- `make check-all` passes, and the actual cached artifact remains outside Git.

## Explicitly deferred

Custom natural-language studies, additional simulation families, customer segmentation, live
browser-triggered refreshes, concurrent run orchestration, production object storage, and RT-J
prediction-to-simulation coupling remain separate follow-on work. The catalog and typed contracts
remain extensible; only the first displayed happy path is H&M promotional-offer screening.
