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
from structagent_api.contracts import (
    DatasetDescriptor,
    DaytonaMaterializationRequest,
    DaytonaMaterializationResponse,
    DefaultTaskCatalog,
    EvaluationResult,
    RunRecord,
    SimulationStudyArtifact,
    TaskDraftOutcome,
    TaskDraftRequest,
)
from structagent_api.materialization.daytona_executor import DaytonaExecutionError
from structagent_api.materialization.daytona_service import materialize_synthetic_in_daytona
from structagent_api.materialization.task_sql import TaskId
from structagent_api.settings import Settings
from structagent_api.simulation_catalog import hm_promo_conjoint_v1

FIXTURE_DIR = Path(__file__).resolve().parents[4] / "contracts" / "v1" / "examples" / "rel-hm"
TASK_DRAFT_ADAPTER: TypeAdapter[TaskDraftOutcome] = TypeAdapter(TaskDraftOutcome)
EVALUATION_ADAPTER: TypeAdapter[EvaluationResult] = TypeAdapter(EvaluationResult)
DaytonaMaterializer = Callable[[Sequence[TaskId]], DaytonaMaterializationResponse]


class HealthResponse(BaseModel):
    """Public liveness response."""

    status: str
    service: str
    environment: str
    version: str


def create_app(
    settings: Settings | None = None,
    daytona_materializer: DaytonaMaterializer | None = None,
) -> FastAPI:
    """Create an API instance without performing external work at import time."""

    resolved = settings or Settings()
    resolved_daytona_materializer = daytona_materializer or materialize_synthetic_in_daytona
    app = FastAPI(
        title="StructAgent API",
        description="Control-plane shell for the provisional StructAgent research demo.",
        version=__version__,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:4173", "http://127.0.0.1:4174"],
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

    @app.get(
        "/v1/simulation-studies/defaults",
        response_model=list[SimulationStudyArtifact],
        tags=["catalog"],
    )
    def get_default_simulation_studies(
        dataset_id: Annotated[str, Query(min_length=1)],
    ) -> list[SimulationStudyArtifact]:
        """List reviewed, metadata-only simulation studies for the active dataset."""

        if dataset_id != ACTIVE_DATASET_ID:
            raise HTTPException(
                status_code=404,
                detail=f"Dataset {dataset_id!r} is not available in the V1 simulation catalog.",
            )
        return [hm_promo_conjoint_v1()]

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

    @app.post("/v1/task-drafts", response_model=TaskDraftOutcome, tags=["demo-contracts"])
    def create_task_draft(request: TaskDraftRequest) -> TaskDraftOutcome:
        if request.dataset_id != "rel-hm":
            raise HTTPException(status_code=404, detail="Dataset is not available in this demo")
        return TASK_DRAFT_ADAPTER.validate_json(_fixture_text("task-contract.json"))

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
