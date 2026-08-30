from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Callable, Sequence
from typing import Literal, cast

from agents import Agent, ModelSettings, Runner, function_tool, set_tracing_disabled
from agents.models.interface import Model
from openai_codex import ApprovalMode, Codex, CodexConfig, Sandbox
from openai_codex.models import JsonObject
from pydantic import BaseModel

from spikes.daytona_agents_sdk.smoke import (
    CANARY_TOOL_NAME,
    SandboxEvidence,
    execute_daytona_canary,
    redact_error_message,
)

DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"
DEFAULT_CODEX_MODEL = "gpt-5.6-luna"
CODEX_ACTION = "run_daytona_canary"

_CODEX_DIRECTIVE_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": [CODEX_ACTION]},
    },
    "required": ["action"],
    "additionalProperties": False,
}


class OpenAIConclusion(BaseModel):
    completed: Literal[True]


class CodexDirective(BaseModel):
    action: Literal["run_daytona_canary"]


class OpenAIAPIReport(BaseModel):
    provider: Literal["openai-api"] = "openai-api"
    model: str
    openai_api_used: Literal[True] = True
    conclusion: OpenAIConclusion
    sandbox: SandboxEvidence


class CodexSDKReport(BaseModel):
    provider: Literal["codex-sdk"] = "codex-sdk"
    model: str
    authentication: Literal["chatgpt"] = "chatgpt"
    openai_api_key_exposed_to_codex: Literal[False] = False
    daytona_api_key_exposed_to_codex: Literal[False] = False
    directive: CodexDirective
    sandbox: SandboxEvidence


def run_openai_api_smoke(
    executor: Callable[[], SandboxEvidence] = execute_daytona_canary,
    model: str | Model | None = None,
) -> OpenAIAPIReport:
    """Use a live OpenAI model to invoke the fixed Daytona canary exactly once."""
    set_tracing_disabled(True)
    selected_model = model or os.environ.get("OPENAI_SMOKE_MODEL", DEFAULT_OPENAI_MODEL)
    observed: list[SandboxEvidence] = []

    @function_tool(name_override=CANARY_TOOL_NAME, failure_error_function=None)
    def run_daytona_canary() -> str:
        """Run the fixed Daytona sandbox canary and return validated evidence."""
        evidence = executor()
        observed.append(evidence)
        return evidence.model_dump_json()

    agent = Agent(
        name="OpenAI API Daytona smoke coordinator",
        instructions=(
            f"Call {CANARY_TOOL_NAME} exactly once. After it succeeds, return completed=true. "
            "Do not call any other tool and do not claim success before receiving tool evidence."
        ),
        model=selected_model,
        model_settings=ModelSettings(
            max_tokens=300,
            parallel_tool_calls=False,
            store=False,
            timeout=30,
        ),
        tools=[run_daytona_canary],
        output_type=OpenAIConclusion,
    )
    result = Runner.run_sync(
        agent,
        "Run the bounded Daytona smoke test now.",
        max_turns=3,
    )

    if len(observed) != 1:
        raise RuntimeError(f"Expected one Daytona tool call, observed {len(observed)}")
    if not isinstance(result.final_output, OpenAIConclusion):
        raise RuntimeError("The OpenAI agent returned an invalid conclusion")

    model_name = (
        selected_model if isinstance(selected_model, str) else type(selected_model).__name__
    )
    return OpenAIAPIReport(
        model=model_name,
        conclusion=result.final_output,
        sandbox=observed[0],
    )


def _codex_child_environment() -> dict[str, str]:
    child_environment = dict(os.environ)
    for variable_name in ("OPENAI_API_KEY", "DAYTONA_API_KEY", "CODEX_ACCESS_TOKEN"):
        child_environment.pop(variable_name, None)
    return child_environment


def request_codex_directive(model: str | None = None) -> CodexDirective:
    """Ask a locally authenticated, read-only Codex thread for one fixed directive."""
    selected_model = model or os.environ.get("CODEX_SMOKE_MODEL") or DEFAULT_CODEX_MODEL
    with tempfile.TemporaryDirectory(prefix="structagent-codex-smoke-") as workspace:
        config = CodexConfig(env=_codex_child_environment())
        with Codex(config) as codex:
            account = codex.account().account
            if account is None or account.root.type != "chatgpt":
                raise RuntimeError(
                    "The Codex SDK smoke requires an existing ChatGPT-authenticated Codex login"
                )
            thread = codex.thread_start(
                approval_mode=ApprovalMode.deny_all,
                cwd=workspace,
                ephemeral=True,
                model=selected_model,
                sandbox=Sandbox.read_only,
            )
            result = thread.run(
                (
                    "This is a bounded connectivity smoke test. Do not inspect files, "
                    "run commands, or call tools. Return only the requested "
                    f"{CODEX_ACTION} directive."
                ),
                output_schema=_CODEX_DIRECTIVE_SCHEMA,
            )

    if result.final_response is None:
        raise RuntimeError("The Codex SDK returned no final response")
    return CodexDirective.model_validate_json(result.final_response)


def run_codex_sdk_smoke(
    executor: Callable[[], SandboxEvidence] = execute_daytona_canary,
    model: str | None = None,
) -> CodexSDKReport:
    """Validate the local Codex SDK path, then run the fixed Daytona canary."""
    selected_model = model or os.environ.get("CODEX_SMOKE_MODEL") or DEFAULT_CODEX_MODEL
    directive = request_codex_directive(selected_model)
    evidence = executor()
    return CodexSDKReport(
        model=selected_model,
        directive=directive,
        sandbox=evidence,
    )


def _require_environment(*variable_names: str) -> None:
    missing = [name for name in variable_names if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


ProviderChoice = Literal["openai-api", "codex-sdk", "all"]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run bounded provider-to-Daytona smoke tests.")
    parser.add_argument("provider", choices=("openai-api", "codex-sdk", "all"))
    arguments = parser.parse_args(argv)
    provider = cast(ProviderChoice, arguments.provider)

    try:
        _require_environment("DAYTONA_API_KEY")
        reports: list[OpenAIAPIReport | CodexSDKReport] = []
        if provider in ("openai-api", "all"):
            _require_environment("OPENAI_API_KEY")
            reports.append(run_openai_api_smoke())
        if provider in ("codex-sdk", "all"):
            reports.append(run_codex_sdk_smoke())
    except Exception as error:
        print(
            f"Live smoke failed ({type(error).__name__}): {redact_error_message(error)}",
            file=sys.stderr,
        )
        return 1

    print(json.dumps([report.model_dump(mode="json") for report in reports], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
