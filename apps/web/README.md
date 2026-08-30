# Web application placeholder

This directory is reserved for the StructAgent frontend. No framework, package manager,
deployment target, or localhost port has been selected.

## Available integration artifacts

Frontend work can proceed against:

- versioned JSON Schemas in `contracts/v1/schemas`;
- Amazon and H&M example journeys in `contracts/v1/examples`; and
- the implemented API health endpoint at `http://127.0.0.1:8000/healthz`.

Every example result is synthetic. The UI must preserve a visible demo/fixture treatment
and must not present its metrics, run state, provenance, or integrity checks as observed
model behavior.

There are no live task-drafting, approval, run, or result endpoints yet. Do not infer
transport routes from the example filenames. Those routes will be designed with the
frontend when the compiler milestone begins.
