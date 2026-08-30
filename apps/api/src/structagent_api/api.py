"""FastAPI application factory for the StructAgent API shell."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, TypeAdapter

from structagent_api import __version__
from structagent_api.catalog import ACTIVE_DATASET_ID, REL_HM_DATASET, REL_HM_DEFAULT_TASKS
from structagent_api.compiler import TaskCompiler, TaskCompilerError
from structagent_api.compiler.agent import compiler_from_environment
from structagent_api.compiler.service import draft_id_for
from structagent_api.contracts import (
    DatasetDescriptor,
    DaytonaMaterializationRequest,
    DaytonaMaterializationResponse,
    DefaultTaskCatalog,
    EvaluationResult,
    LiveTaskDraftOutcome,
    ModalInferenceRequest,
    ModalInferenceResponse,
    RunRecord,
    SimulatedInferenceRequest,
    SimulatedInferenceResponse,
    TaskClarificationRequest,
    TaskDraftRequest,
    UnsupportedTaskDraft,
)
from structagent_api.inference.evaluator import InferenceEvaluationError
from structagent_api.inference.modal_runner import ModalRunnerError
from structagent_api.inference.simulated import simulate_inference
from structagent_api.inference.ui_service import (
    ModalInferenceServiceError,
    run_modal_inference_for_ui,
)
from structagent_api.materialization.daytona_executor import DaytonaExecutionError
from structagent_api.materialization.daytona_service import materialize_synthetic_in_daytona
from structagent_api.materialization.task_sql import TaskId
from structagent_api.settings import Settings

FIXTURE_DIR = Path(__file__).resolve().parents[4] / "contracts" / "v1" / "examples" / "rel-hm"
EVALUATION_ADAPTER: TypeAdapter[EvaluationResult] = TypeAdapter(EvaluationResult)
DaytonaMaterializer = Callable[[Sequence[TaskId]], DaytonaMaterializationResponse]
ModalInferenceRunner = Callable[[ModalInferenceRequest], ModalInferenceResponse]


class HealthResponse(BaseModel):
    """Public liveness response."""

    status: str
    service: str
    environment: str
    version: str


def create_app(
    settings: Settings | None = None,
    task_compiler: TaskCompiler | None = None,
    daytona_materializer: DaytonaMaterializer | None = None,
    modal_inference_runner: ModalInferenceRunner | None = None,
) -> FastAPI:
    """Create an API instance without performing external work at import time."""

    resolved = settings or Settings()
    compiler = task_compiler or compiler_from_environment()
    resolved_daytona_materializer = daytona_materializer or materialize_synthetic_in_daytona

    def default_modal_inference_runner(
        request: ModalInferenceRequest,
    ) -> ModalInferenceResponse:
        return run_modal_inference_for_ui(request, resolved)

    resolved_modal_inference_runner = modal_inference_runner or default_modal_inference_runner
    app = FastAPI(
        title="StructAgent API",
        description="Control-plane shell for the provisional StructAgent research demo.",
        version=__version__,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:4173",
            "http://127.0.0.1:4174",
            "http://localhost:4173",
            "http://localhost:4174",
        ],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/healthz", response_model=HealthResponse, tags=["operations"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=resolved.service_name,
            environment=resolved.environment,
            version=__version__,
        )

    @app.get(
        "/v1/datasets/rel-hm",
        response_model=DatasetDescriptor,
        tags=["catalog"],
    )
    def get_rel_hm_dataset() -> DatasetDescriptor:
        return REL_HM_DATASET

    @app.get(
        "/v1/tasks/defaults",
        response_model=DefaultTaskCatalog,
        tags=["catalog"],
    )
    def get_default_tasks(
        dataset_id: Annotated[str, Query(min_length=1)],
    ) -> DefaultTaskCatalog:
        if dataset_id != ACTIVE_DATASET_ID:
            raise HTTPException(
                status_code=404,
                detail=f"Dataset {dataset_id!r} is not available in the V1 default catalog.",
            )
        return REL_HM_DEFAULT_TASKS

    @app.post(
        "/v1/materializations/daytona",
        response_model=DaytonaMaterializationResponse,
        tags=["materialization"],
    )
    def create_daytona_materialization(
        request: DaytonaMaterializationRequest,
    ) -> DaytonaMaterializationResponse:
        try:
            return resolved_daytona_materializer(request.task_ids)
        except DaytonaExecutionError as error:
            status_code = 503 if error.code == "missing_credential" else 502
            raise HTTPException(
                status_code=status_code,
                detail={"code": error.code, "message": error.detail},
            ) from error
        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "materialization_failure",
                    "message": "Synthetic Daytona materialization failed",
                },
            ) from error

    @app.post(
        "/v1/inferences/simulated",
        response_model=SimulatedInferenceResponse,
        tags=["demo-contracts"],
    )
    def create_simulated_inference(
        request: SimulatedInferenceRequest,
    ) -> SimulatedInferenceResponse:
        return simulate_inference(request)

    @app.post(
        "/v1/inferences/modal",
        response_model=ModalInferenceResponse,
        tags=["inference"],
    )
    def create_modal_inference(request: ModalInferenceRequest) -> ModalInferenceResponse:
        try:
            return resolved_modal_inference_runner(request)
        except ModalInferenceServiceError as error:
            raise HTTPException(
                status_code=503,
                detail={"code": error.code, "message": error.detail},
            ) from error
        except (ModalRunnerError, InferenceEvaluationError) as error:
            raise HTTPException(
                status_code=502,
                detail={"code": error.code, "message": error.detail},
            ) from error
        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "modal_inference_failure",
                    "message": "Observed Modal inference failed.",
                },
            ) from error

    @app.post("/v1/task-drafts", response_model=LiveTaskDraftOutcome, tags=["task-compiler"])
    async def create_task_draft(request: TaskDraftRequest) -> LiveTaskDraftOutcome:
        if request.dataset_id != "rel-hm":
            return UnsupportedTaskDraft(
                contract_version="v1",
                outcome="unsupported",
                draft_id=draft_id_for(request.dataset_id, request.prompt),
                reason_code="unsupported_dataset",
                explanation="V1 supports only RelBench H&M.",
            )
        try:
            return await compiler.compile(request)
        except TaskCompilerError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, "message": error.detail},
            ) from error

    @app.post(
        "/v1/task-drafts/{draft_id}/clarifications",
        response_model=LiveTaskDraftOutcome,
        tags=["task-compiler"],
    )
    async def clarify_task_draft(
        draft_id: str,
        request: TaskClarificationRequest,
    ) -> LiveTaskDraftOutcome:
        try:
            return await compiler.clarify(draft_id, request)
        except TaskCompilerError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, "message": error.detail},
            ) from error

    @app.get("/v1/runs/{run_id}", response_model=RunRecord, tags=["demo-contracts"])
    def get_run(run_id: str) -> RunRecord:
        run = RunRecord.model_validate_json(_fixture_text("run-record.json"))
        if run.run_id != run_id:
            raise HTTPException(status_code=404, detail="Run not found")
        return run

    @app.get(
        "/v1/runs/{run_id}/evaluation",
        response_model=EvaluationResult,
        tags=["demo-contracts"],
    )
    def get_evaluation(run_id: str) -> EvaluationResult:
        evaluation = EVALUATION_ADAPTER.validate_json(_fixture_text("evaluation-result.json"))
        if evaluation.run_id != run_id:
            raise HTTPException(status_code=404, detail="Evaluation not found")
        return evaluation

    return app


def _fixture_text(filename: str) -> str:
    """Read reviewed synthetic contract fixtures without accepting arbitrary paths."""
    return (FIXTURE_DIR / filename).read_text(encoding="utf-8")
