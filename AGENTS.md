# StructAgent Project Instructions

These instructions apply throughout the repository. `CLAUDE.md` is a symlink to this
file and must remain so.

## Working method

1. State assumptions and measurable success criteria before editing.
2. Inspect the implementation, contracts, documentation, and tests first.
3. Stop and ask when ambiguity would change product behavior, architecture, licensing,
   public claims, security, or external infrastructure.
4. Choose the smallest implementation that satisfies the request.
5. Make surgical changes and preserve unrelated worktree edits.
6. Add behavioral tests with behavior changes and review the final diff for generated
   noise, unrelated edits, and leaked secrets.

Do not add speculative abstractions, providers, services, or deployment machinery.
Remove only code made obsolete by the current change.

## Current product boundary

- The current repository is a contract scaffold, not a functioning ML product.
- The API exposes only explicitly implemented routes. Do not advertise fixture-only
  workflows as live endpoints.
- Committed evaluation examples are synthetic interface fixtures, never research
  findings or model results.
- Keep OpenAI, Daytona, RT-J, database, and frontend integrations absent until their
  milestones are explicitly approved.

## Verification

Use Make as the supported interface. Run focused tests while developing and
`make check-all` before handoff or push. Explain any check that could not run; never
claim an unexecuted check passed.

Tests must use concrete inputs and expected outputs. Default tests must be deterministic
and make no network or live-provider calls. A successful import alone is not behavioral
verification.

## Contracts, data, and security

- Pydantic models are the source of truth for versioned contract schemas.
- Regenerate schema snapshots with `make contracts-export`; reject drift with
  `make contracts-check`.
- Every fixture must identify itself as synthetic or metadata-only and as a placeholder.
- Never commit credentials, raw datasets, model/checkpoint files, contexts, predictions,
  caches, local databases, or personal data.
- Secrets belong in ignored environment files or an approved secret manager. Browser
  code must never receive OpenAI or Daytona credentials.
- Redact prompts, credentials, personal data, and sensitive database values from logs.

## Git workflow

The sole direct push to `main` is the one-time bootstrap of the empty remote. After that:

1. update local `main` with `git pull --ff-only origin main`;
2. create a focused `feat/`, `fix/`, `docs/`, `test/`, or `chore/` branch;
3. keep commits limited to one logical change and valid at every commit;
4. install hooks with `make hooks` and run `make check-all` before pushing;
5. open a draft pull request for review.

Never push directly to `main` after bootstrap, force-push, rewrite published history,
bypass hooks, or merge a pull request without explicit approval from Tony Kwok. Do not
commit, push, open pull requests, change repository settings, deploy, or publish unless
the user explicitly authorizes that external action.

## Legal and public claims

- Original repository code is MIT-licensed; external assets retain their own terms.
- Do not vendor or redistribute RT-J source, weights, or datasets without an approved
  licensing decision.
- StructureML is an independent research initiative and is not currently incorporated.
- Do not claim trademark registration, publications, model results, customers,
  commercial readiness, employer affiliation, or endorsement unless verified and
  explicitly approved.
