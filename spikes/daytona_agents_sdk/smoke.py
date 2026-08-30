from __future__ import annotations

import os
import sys
from collections.abc import Callable
from typing import Literal

from agents import Agent, Runner, function_tool, set_tracing_disabled
from agents.testing import ScriptedModel, assistant_message, function_call
from daytona import CreateSandboxFromSnapshotParams, Daytona
from pydantic import BaseModel

CANARY_MARKER: Literal["structagent-daytona-canary"] = "structagent-daytona-canary"
CANARY_TOOL_NAME = "run_daytona_canary"
FINAL_OUTPUT = "The keyless Daytona canary completed."
SANDBOX_TTL_MINUTES = 10

_CANARY_CODE = f"""
import json
import platform

print(json.dumps({{
    "marker": "{CANARY_MARKER}",
    "python_version": platform.python_version(),
}}, sort_keys=True))
""".strip()


class SandboxPayload(BaseModel):
    marker: Literal["structagent-daytona-canary"]
    python_version: str


class SandboxEvidence(SandboxPayload):
    cleanup_confirmed: bool
    network_block_all_requested: bool
    ttl_minutes: int


class SmokeReport(BaseModel):
    mode: Literal["scripted-keyless"] = "scripted-keyless"
    openai_api_used: Literal[False] = False
    model_calls: int
    final_output: str
    sandbox: SandboxEvidence


def execute_daytona_canary() -> SandboxEvidence:
    """Run fixed Python in a short-lived CPU sandbox and confirm deletion."""
    client = Daytona()
    params = CreateSandboxFromSnapshotParams(
        language="python",
        labels={"project": "structagent", "purpose": "agents-sdk-smoke"},
        public=False,
        auto_stop_interval=5,
        auto_delete_interval=0,
        ttl_minutes=SANDBOX_TTL_MINUTES,
        network_block_all=True,
        ephemeral=True,
    )
    sandbox = client.create(params, timeout=60)
    payload: SandboxPayload | None = None

    try:
        response = sandbox.process.code_run(_CANARY_CODE, timeout=30)
        if response.exit_code != 0:
            raise RuntimeError(f"Daytona canary exited with status {response.exit_code}")

        output_lines = [line for line in response.result.splitlines() if line.strip()]
        if not output_lines:
            raise RuntimeError("Daytona canary returned no output")
        payload = SandboxPayload.model_validate_json(output_lines[-1])
    finally:
        client.delete(sandbox, timeout=60, wait=True)

    if payload is None:  # pragma: no cover - guarded by the exceptions above
        raise RuntimeError("Daytona canary produced no validated payload")

    return SandboxEvidence(
        **payload.model_dump(),
        cleanup_confirmed=True,
        network_block_all_requested=True,
        ttl_minutes=SANDBOX_TTL_MINUTES,
    )


def run_keyless_agent(
    executor: Callable[[], SandboxEvidence] = execute_daytona_canary,
) -> SmokeReport:
    """Use a scripted model to exercise one Agents SDK tool loop without an API call."""
    set_tracing_disabled(True)
    observed: list[SandboxEvidence] = []

    @function_tool(name_override=CANARY_TOOL_NAME, failure_error_function=None)
    def run_daytona_canary() -> str:
        """Run the fixed Daytona sandbox canary and return its evidence."""
        evidence = executor()
        observed.append(evidence)
        return evidence.model_dump_json()

    model = ScriptedModel(
        [
            [function_call(CANARY_TOOL_NAME, {}, call_id="daytona-canary-call")],
            [assistant_message(FINAL_OUTPUT)],
        ]
    )
    agent = Agent(
        name="Daytona canary coordinator",
        instructions="Run the single canary tool, then report completion.",
        model=model,
        tools=[run_daytona_canary],
    )
    result = Runner.run_sync(agent, "Verify the Daytona execution boundary.")
    model.assert_complete()

    if len(observed) != 1:
        raise RuntimeError(f"Expected one Daytona tool call, observed {len(observed)}")
    if result.final_output != FINAL_OUTPUT:
        raise RuntimeError("The scripted Agents SDK run returned an unexpected final output")

    return SmokeReport(
        model_calls=len(model.calls),
        final_output=FINAL_OUTPUT,
        sandbox=observed[0],
    )


def redact_error_message(error: Exception) -> str:
    """Remove known local credential values from a provider error message."""
    message = str(error)
    for variable_name in ("DAYTONA_API_KEY", "OPENAI_API_KEY", "CODEX_ACCESS_TOKEN"):
        secret = os.environ.get(variable_name)
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return message


def main() -> int:
    if not os.environ.get("DAYTONA_API_KEY"):
        print(
            "DAYTONA_API_KEY is required for the live smoke test; OPENAI_API_KEY is not.",
            file=sys.stderr,
        )
        return 2

    try:
        report = run_keyless_agent()
    except Exception as error:
        print(
            f"Smoke test failed ({type(error).__name__}): {redact_error_message(error)}",
            file=sys.stderr,
        )
        return 1

    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
