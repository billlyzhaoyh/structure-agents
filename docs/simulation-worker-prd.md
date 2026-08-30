# H&M Simulation Worker Product Requirements

## Problem Statement

An SME operator needs help screening candidate decisions before spending limited time and
money on a field experiment. StructAgent currently has only an API shell and cannot turn a
reviewed simulation study into an observed run. It has no simulation contracts, no
respondent-model execution, no Daytona worker, no validation evidence, and no result format
that the product can safely display.

The first demonstration must use the approved RelBench H&M snapshot because that is the
dataset being prepared by the backend roadmap. It must offer a reviewed promotional conjoint
study and also let a user describe a custom H&M discrete-choice study in natural language.
The product must not mistake simulated preferences for causal or commercial evidence: a
plausible ranking is useful only when the simulation machinery passes explicit validation
gates, and it must never be presented as uplift, incrementality, elasticity, or revenue.

## Solution

Add `simulation` as a run type in the shared asynchronous lifecycle. A user can run a pinned,
reviewed H&M promotion study in one action or describe a custom H&M discrete-choice study,
answer typed clarification questions, review an immutable study artifact, and approve it for
execution.

For each approved run, the control plane creates an ephemeral Daytona sandbox and mounts the
shared H&M dataset read-only. A simulation worker derives cutoff-safe aggregate traits,
projects only those minimized traits into deterministic personas, constructs randomized
choice tasks, and runs them through EDSL using one system-selected respondent language model.
The worker estimates population-level choice effects, applies current certification and
run-specific validation gates, and returns canonical versioned JSON. A failing or stale gate
prevents the product from returning a treatment recommendation.

The reviewed promotion study is data, not special worker code. The shared study artifact is
discriminated by study family so future simulation families can be added without changing the
run lifecycle. Version 1 implements only the discrete-choice family and only H&M-derived
populations.

## User Stories

1. As an SME operator, I want to select a reviewed H&M promotion study, so that I can run a
   credible demonstration without designing a study from scratch.
2. As an SME operator, I want a reviewed default study to start with one action, so that I am
   not asked to approve configuration the product already owns.
3. As an SME operator, I want to describe a custom decision in natural language, so that I do
   not need to understand conjoint-analysis configuration.
4. As an SME operator, I want the product to ask focused clarification questions, so that an
   ambiguous request is not silently converted into the wrong study.
5. As an SME operator, I want to review the population, decision, alternatives, attributes,
   control, and limitations before a custom run, so that I know what the simulation will test.
6. As an SME operator, I want material edits to invalidate an earlier approval, so that the
   executed study always matches what I reviewed.
7. As an SME operator, I want unsupported requests to be declined clearly, so that I do not
   receive a persuasive result for a study the system cannot execute safely.
8. As an SME operator, I want every choice task to include a no-choice option, so that the
   simulation does not force respondents to select an unwanted treatment.
9. As an SME operator, I want a control or baseline whenever the study estimand needs one, so
   that treatment comparisons have an explicit reference.
10. As an SME operator, I want one population-level treatment recommendation per run, so that
    the output matches a population-wide launch decision.
11. As an SME operator, I want customer segmentation excluded from the first version, so that
    thin or exploratory segments are not presented as reliable recommendations.
12. As an SME operator, I want validation status shown before rankings, so that I can tell
    whether the system considers its own result usable.
13. As an SME operator, I want no recommendation when a hard validation gate fails, so that a
    failed instrument cannot masquerade as a shortlist.
14. As an SME operator, I want a ranked shortlist when validation passes, so that I can choose
    which candidates deserve a real experiment.
15. As an SME operator, I want unstable or noise-sized effects suppressed, so that model
    randomness is not presented as preference.
16. As an SME operator, I want plain-language limitations in the result, so that I do not
    mistake H&M-conditioned agents for my own customers.
17. As an SME operator, I do not want simulated uplift, incrementality, elasticity, expected
    percentages, or revenue projections, so that demo outputs do not overclaim evidence.
18. As an SME operator, I want provider billing and infrastructure details hidden, so that the
    product behaves as one managed SaaS service.
19. As an SME operator, I want useful product-level failures, so that vendor errors and secret
    names are not exposed to me.
20. As a product reviewer, I want custom studies represented as immutable typed artifacts, so
    that semantics can be reviewed independently from runtime behavior.
21. As a product reviewer, I want the reviewed promotion study pinned and versioned, so that
    its meaning cannot drift between demonstrations.
22. As a product reviewer, I want findings framed as H&M-conditioned simulation results, so
    that they are not claimed to describe the general population or an SME account.
23. As a research reviewer, I want the dataset, cohort, cutoff, feature query, study,
    respondent model, prompt template, random seed, and runtime provenance recorded, so that I
    can audit how a result was produced.
24. As a research reviewer, I want persona conditioning calibrated against a sealed temporal
    holdout, so that decorative personas cannot pass certification unnoticed.
25. As a research reviewer, I want order-invariance testing, so that answer placement cannot
    determine the top-ranked treatment.
26. As a research reviewer, I want trait-ablation testing, so that the system must demonstrate
    that behavioral traits affect responses.
27. As a research reviewer, I want repeat-variance measurement, so that respondent-model
    stochasticity is measured instead of ignored.
28. As a research reviewer, I want markdown-proxy concordance and sensitivity analysis, so
    that the discount-affinity trait is treated as a proxy rather than an observed promotion.
29. As a research reviewer, I want certification invalidated by relevant version changes, so
    that evidence from an old model, dataset, prompt, or implementation is not reused.
30. As a data steward, I want only approved aggregate traits sent to the respondent model, so
    that customer identifiers and row-level purchase histories remain inside the trusted data
    boundary.
31. As a data steward, I want raw H&M data mounted read-only, so that simulation execution
    cannot mutate the shared dataset.
32. As a data steward, I want raw data, prompts, respondent outputs, credentials, and generated
    run artifacts excluded from Git, so that restricted and sensitive material is not
    redistributed.
33. As a platform operator, I want every run isolated in an ephemeral Daytona sandbox, so that
    failures and dependencies do not contaminate other runs.
34. As a platform operator, I want system-managed admission, cost, concurrency, retry, and
    runtime limits, so that users cannot create unbounded work.
35. As a platform operator, I want cleanup verified after success, failure, timeout, and
    cancellation, so that abandoned sandboxes and secrets do not accumulate.
36. As a platform operator, I want response-level checkpoints, so that an interrupted run can
    resume missing calls without replaying completed calls.
37. As a platform operator, I want completed artifacts copied out and digest-verified before
    sandbox destruction, so that terminal results are durable and untampered.
38. As a platform operator, I want run state to survive an API restart, so that asynchronous
    work remains observable and recoverable.
39. As a platform operator, I want one system-selected respondent model per run, so that a
    result does not mix incompatible model behavior.
40. As a platform operator, I want fresh responses for new runs and repeats, so that remote
    cache reuse does not create artificial stability.
41. As a developer, I want API and worker code to share one versioned Pydantic contract, so
    that artifact producers and consumers cannot drift silently.
42. As a developer, I want the study contract discriminated by study family, so that a future
    family can be added without changing the shared run lifecycle.
43. As a developer, I want only the discrete-choice family implemented now, so that extension
    does not create unused frameworks or placeholder behavior.
44. As a developer, I want deterministic network-free CI, so that normal repository checks do
    not require paid providers or credentials.
45. As a developer, I want credentialed boundary tests and real end-to-end smoke runs, so that
    test doubles are not mistaken for a functioning product.
46. As a frontend developer, I want canonical versioned JSON, so that the UI can stay simple
    and does not need to parse generated HTML.
47. As a frontend developer, I want typed validation and failure codes, so that the UI can
    explain why no recommendation was returned.
48. As a future study-family developer, I want population, provenance, execution, and reporting
    metadata shared across families, so that I can add a family without rebuilding orchestration.

## Implementation Decisions

- The feature extends the shared asynchronous run lifecycle with a discriminated `simulation`
  run type; prediction and simulation retain distinct request and result contracts.
- The control plane is trusted. It owns natural-language compilation, semantic review,
  approval, admission policy, persistence, and Daytona lifecycle management.
- The worker executes inside one ephemeral Daytona sandbox per run. It receives reviewed
  artifacts and scoped secrets, not the compiler's OpenAI key.
- The simulation worker consumes the upstream backend's versioned H&M snapshot and private
  read-only Daytona volume. It does not download, package, or independently ingest RelBench.
- A dataset handoff includes revision, manifest digest, cutoffs, provenance, and an internal
  volume reference resolved at execution time.
- The API's versioned Pydantic contract module is the source of truth for simulation schemas.
  Generated JSON Schemas define the later worker boundary without introducing a duplicate
  contract package.
- `SimulationStudyArtifact` contains common population, provenance, model-policy, execution,
  validation, and reporting metadata. Its `study_type` field discriminates typed study-family
  payloads.
- Version 1 implements only `discrete_choice`. The architecture permits later typed families
  but includes no generic plugin loader or placeholder implementations.
- The reviewed `rel-hm/promo-conjoint-v1` study is a pinned default artifact, not conditional
  worker logic.
- Custom studies use natural-language compilation, typed clarification, static validation,
  immutable artifacts, digests, and explicit semantic approval.
- Custom version 1 studies are limited to H&M-derived populations and discrete-choice designs.
  Users cannot provide executable Python, SQL, raw EDSL prompts, estimator code, or validation
  code.
- Default studies require no separate semantic approval. Selecting and running a default is
  the user's execution action. Material changes to a custom artifact require new approval.
- A discrete-choice study has two alternatives per task plus an explicit no-choice option.
  It declares a baseline/control when the estimand requires one and uses bounded categorical
  attributes and levels.
- Version 1 supports one predeclared eligible cohort and one population-wide treatment
  decision. Segment discovery and segment-specific effects are future work.
- The simulation package owns versioned trait derivation over the shared H&M dataset. The
  upstream task materializer remains responsible for dataset custody, schema, and cutoffs.
- Model-visible personas contain only approved aggregate traits. Customer IDs, postal-code
  hashes, exact dates, raw transactions, and article histories never enter provider prompts.
- The initial markdown proxy compares paid price with a cutoff-safe, quantized, article-level
  modal reference price over the preceding 28 days, excluding the current transaction and
  requiring sufficient history. Insufficient history is `unknown`.
- Markdown-proxy certification compares 14-, 28-, and 56-day windows. Materially unstable
  customer ordering fails concordance rather than selecting a favorable definition.
- Studies use proportional sampling within the eligible cohort. The reviewed default targets
  400 agents and accepts a bounded 300-to-600 range.
- EDSL runs with one system-selected and version-pinned respondent language model. Provider
  selection is not user-configurable in version 1.
- Daytona receives a dedicated internally budgeted Expected Parrot credential at runtime. EDSL
  remote jobs and results use private visibility. The trusted API's compiler credential and
  raw provider credentials do not cross into Daytona.
- New runs request fresh model responses. A private response ledger checkpoints completed
  agent-task-repeat calls and resumes only missing work within the same run.
- Full repeat testing occurs during certification. Each run repeats a deterministic sentinel
  subset to detect drift without tripling all model calls. Repeats are not independent agents.
- Certification is keyed by dataset revision, respondent-model version, EDSL version, persona
  template, trait derivation, and study-family implementation.
- Certification includes full repeat variance, order invariance, trait ablation, markdown
  concordance, and sealed temporal holdout calibration.
- The trusted evaluator compares pre-cutoff simulated purchase intent with sealed next-week
  churn truth. Truth never enters persona construction or model prompts. Above-chance temporal
  holdout performance is required but is not described as promotion-response validation.
- Per-run validation covers design invariants, randomization balance, applicable monotonicity
  constraints, sentinel repeat variance, certification currency, and suppression thresholds.
- Hard-gate failure or stale certification returns no treatment ranking.
- Estimation is population-level. Technical artifacts contain weighted AMCE estimates with
  agent-clustered uncertainty, but the product result emphasizes rankings, stability,
  suppression, and limitations.
- The result contract prohibits uplift, incrementality, price elasticity, revenue projection,
  and expected-percentage claims.
- Canonical versioned JSON is the only worker output contract. HTML reporting is not part of
  version 1.
- SQLite stores run state, approvals, digests, provenance, and artifact metadata. A private
  filesystem artifact store holds larger run artifacts for the hackathon demonstration.
- The API verifies artifact digests before accepting a terminal result and destroys the
  sandbox only after required artifacts are durable.
- User-facing approval concerns study semantics and execution intent. Provider spend, credits,
  call counts, concurrency, retries, and runtime ceilings are internal platform policy.
- The non-commercial hackathon demo is approved to use the H&M snapshot privately in Daytona
  and process minimized traits through EDSL. Raw data and respondent-level artifacts are not
  redistributed. Commercial use requires a new permission decision.

## Testing Decisions

- The primary behavioral seam is an approved, versioned study artifact entering the shared run
  lifecycle and producing either a validated canonical result or a typed terminal failure.
- Tests assert observable contracts, state transitions, artifacts, rankings, suppression, and
  cleanup. They do not assert private helper calls or implementation-specific class structure.
- Contract tests verify schema versions, discriminators, default-study contents, round trips,
  digests, bounded values, unique attributes and levels, valid baselines, and rejection of
  unsupported study families.
- Compiler tests use a deterministic model double and cover complete requests, clarification,
  unsupported requests, unsafe generated fields, review invalidation, refusal, repair limits,
  timeout, and provider failure.
- Population tests use concrete H&M-shaped synthetic tables and expected trait values. They
  cover cutoff leakage, missing values, insufficient reference-price history, sampling
  determinism, quantile boundaries, and all markdown-proxy windows.
- Design tests use fixed seeds and expected profiles. They verify no-choice presence, control
  construction, option-order independence, attribute applicability, balanced assignment, and
  task-count bounds.
- Estimator tests use concrete choices with known expected rankings and coefficients. They
  cover weights, clustered uncertainty, baselines, suppression, missing cells, and degenerate
  designs.
- Validation tests cover every pass, fail, stale, and not-applicable outcome, including the rule
  that a hard failure cannot produce a recommendation.
- Temporal holdout tests keep truth in an evaluator-owned fixture and prove it cannot enter
  model-visible input construction.
- Orchestration tests cover approval enforcement, admission rejection, restart recovery,
  checkpoints, replay, timeout, cancellation, artifact tampering, partial results, and cleanup.
- Secret-boundary tests prove that compiler credentials, raw H&M rows, identifiers, prompts,
  and respondent outputs are absent from logs and public results.
- Deterministic CI uses contract-faithful adapters for Daytona, EDSL, compilation, dataset
  access, and artifact storage. These adapters never produce results identified as observed.
- Credentialed integration tests exercise each real external boundary outside default CI.
- Completion requires two real end-to-end smoke runs: the reviewed H&M promotion default and
  one custom natural-language discrete-choice study.
- Repository verification uses the supported Make interface. Contract snapshots are exported
  and checked, and the milestone ends with `make check-all`.

## Out of Scope

- Customer segmentation, discovered cohorts, and segment-specific treatment recommendations.
- Non-H&M datasets, user uploads, arbitrary database connections, and census-derived personas.
- Simulation families other than discrete choice, including open-ended interviews, free-form
  surveys, allocation, policy learning, and simulated forecasting.
- Causal-effect claims, uplift, incrementality, price elasticity, revenue forecasts, expected
  commercial percentages, and claims about an SME's actual customers.
- RT-J inference inside the simulation path. RT-J remains a separate prediction worker.
- User-selected respondent models, mixed-model runs, or cross-model comparison products.
- Arbitrary user-supplied code, SQL, prompts, estimators, or validation routines.
- Customer-segment AMCEs, automated targeting, treatment personalization, and multiple-testing
  workflows.
- Production authentication, multi-tenant isolation, cloud object storage, billing UI,
  deployment, and commercial licensing approval.
- HTML report generation; the frontend renders canonical JSON.

## Further Notes

- Work must not create a second RelBench ingestion path. Real integration builds on the
  backend roadmap's approved H&M materialization boundary.
- The first simulation slice establishes contracts and the reviewed default alongside the
  existing API, materializer, and frontend without advertising an executable simulation.
- Test doubles are required for deterministic CI but are not the product implementation. The
  milestone is not complete until real H&M, Daytona, EDSL, respondent-model, compiler, and
  persistence paths pass credentialed end-to-end smoke runs.
- Exact respondent model, EDSL version, certification thresholds, and private-artifact
  retention period are selected from live feasibility evidence and then pinned in provenance.
- If certification fails, a successful product outcome is a typed explanation with no
  recommendation. The system must never weaken a gate because a ranking looks plausible.
