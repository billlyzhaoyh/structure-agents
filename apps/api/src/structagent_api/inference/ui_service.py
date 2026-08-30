"""Disabled-by-default HTTP service for a bounded observed Modal run."""

from __future__ import annotations

from uuid import uuid4

from structagent_api.contracts import ModalInferenceRequest, ModalInferenceResponse
from structagent_api.inference.live import run_user_churn_modal
from structagent_api.settings import Settings


class ModalInferenceServiceError(RuntimeError):
    """Sanitized local configuration failure before paid execution starts."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def run_modal_inference_for_ui(
    request: ModalInferenceRequest,
    settings: Settings,
) -> ModalInferenceResponse:
    """Run one approved cohort without exposing private artifacts to the browser."""

    del request  # The strict contract already fixes the only reviewed UI task.
    if not (settings.enable_modal_ui and settings.allow_real_hm and settings.allow_rtj_modal):
        raise ModalInferenceServiceError(
            "modal_ui_disabled",
            "Observed Modal inference is disabled in the local API configuration.",
        )
    if (
        settings.rtj_dataset_root is None
        or settings.rtj_materialization_root is None
        or not settings.rtj_dataset_root.is_dir()
        or not settings.rtj_materialization_root.is_dir()
    ):
        raise ModalInferenceServiceError(
            "modal_input_unavailable",
            "The approved private H&M inputs are unavailable to the local API.",
        )

    run_id = f"rtj-{uuid4().hex[:16]}"
    settings.rtj_output_root.mkdir(parents=True, exist_ok=True)
    outcome = run_user_churn_modal(
        dataset_root=settings.rtj_dataset_root,
        materialization_root=settings.rtj_materialization_root,
        output_root=settings.rtj_output_root / run_id,
        sample_size=32,
        gpu=settings.rtj_modal_gpu,
    )
    if not outcome.cleanup_confirmed:
        raise ModalInferenceServiceError(
            "modal_cleanup",
            "Modal did not confirm ephemeral resource cleanup.",
        )
    return ModalInferenceResponse(
        contract_version="v1",
        fixture=False,
        implementation_status="observed",
        run_id=run_id,
        cleanup_confirmed=True,
        evaluation=outcome.evaluation,
    )
