# Provider + Daytona smoke tests

These isolated feasibility checks exercise three progressively stronger boundaries:

```text
Deterministic ScriptedModel ─┐
OpenAI Agents SDK + API ─────┼─> trusted controller ─> Daytona CPU canary
Local Codex SDK + ChatGPT ───┘
```

The deterministic path proves orchestration and Daytona lifecycle wiring without a model
API call. The OpenAI API path requires the live model to invoke the fixed Daytona function
tool exactly once. The Codex path requires a structured directive from a read-only,
ephemeral local Codex thread before the trusted controller invokes Daytona.

The Codex smoke removes `OPENAI_API_KEY`, `DAYTONA_API_KEY`, and `CODEX_ACCESS_TOKEN` from
the Codex child environment and verifies through the SDK that the cached account type is
`chatgpt`. It therefore fails rather than silently falling back to API-key billing.

Neither provider credential is injected into the Daytona sandbox. The sandbox is private,
blocks outbound network access, has a ten-minute wall-clock TTL, auto-deletes if stopped,
and is synchronously deleted after the fixed Python canary.

## Run

Install the separately locked dependencies and run all deterministic checks:

```bash
make daytona-spike-sync
make daytona-spike-check
```

Put credentials only in the ignored `.env`. The Make targets load it automatically.
`OPENAI_SMOKE_MODEL` and `CODEX_SMOKE_MODEL` default to `gpt-5.6-luna` and can be
overridden there.

```bash
make daytona-spike-run  # DAYTONA_API_KEY; no live model
make smoke-openai-api   # DAYTONA_API_KEY + OPENAI_API_KEY
make smoke-codex-sdk    # DAYTONA_API_KEY + cached ChatGPT Codex login
make smoke-providers    # both live model paths, sequentially
```

Each command exits non-zero on authentication, model, sandbox creation, execution,
validation, or deletion failure. Success prints redacted JSON evidence containing the
provider, model, validated sandbox Python version, and cleanup confirmation.

These smokes do not implement the StructAgent task compiler. They intentionally exclude
RT-J, checkpoints, GPUs, datasets, database access, persistence, and the product API.
