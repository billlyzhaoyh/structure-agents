"""Provider-neutral contracts for the live H&M task compiler."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from structagent_api.contracts.models import (
    ClarificationQuestion,
    ContractVersion,
    CustomTaskSqlArtifact,
    StrictModel,
    TaskContract,
)


class FreeTextClarificationAnswer(StrictModel):
    question_id: str = Field(min_length=1)
    answer_kind: Literal["free_text"]
    value: str = Field(min_length=1)


class SingleChoiceClarificationAnswer(StrictModel):
    question_id: str = Field(min_length=1)
    answer_kind: Literal["single_choice"]
    value: str = Field(min_length=1)


ClarificationAnswer = Annotated[
    FreeTextClarificationAnswer | SingleChoiceClarificationAnswer,
    Field(discriminator="answer_kind"),
]


class TaskClarificationRequest(StrictModel):
    """Stateless continuation of one task-compilation conversation."""

    contract_version: ContractVersion
    dataset_id: Literal["rel-hm"]
    original_prompt: str = Field(min_length=1)
    prior_questions: list[ClarificationQuestion] = Field(min_length=1)
    answers: list[ClarificationAnswer] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_answered_questions(self) -> TaskClarificationRequest:
        question_ids = [question.question_id for question in self.prior_questions]
        answer_ids = [answer.question_id for answer in self.answers]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("clarification questions must have unique IDs")
        if len(answer_ids) != len(set(answer_ids)):
            raise ValueError("clarification answers must have unique IDs")
        if set(question_ids) != set(answer_ids):
            raise ValueError("clarification answers must match the prior questions")

        questions = {question.question_id: question for question in self.prior_questions}
        for answer in self.answers:
            question = questions[answer.question_id]
            if answer.answer_kind != question.answer_kind:
                raise ValueError("clarification answer kind does not match its question")
            if answer.answer_kind == "single_choice" and answer.value not in question.choices:
                raise ValueError("single-choice answer is not one of the declared choices")
        return self


class BinaryValidationEvidence(StrictModel):
    task_type: Literal["binary_classification"]
    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    columns: list[str] = Field(min_length=3, max_length=3)
    row_count: int = Field(gt=0)
    null_rate: float = Field(ge=0, le=1)
    positive_rate: float = Field(ge=0, le=1)


class RegressionValidationEvidence(StrictModel):
    task_type: Literal["regression"]
    query_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    columns: list[str] = Field(min_length=3, max_length=3)
    row_count: int = Field(gt=0)
    null_rate: float = Field(ge=0, le=1)
    target_min: float
    target_max: float

    @model_validator(mode="after")
    def validate_target_range(self) -> RegressionValidationEvidence:
        if self.target_min > self.target_max:
            raise ValueError("regression target range is inverted")
        return self


TaskValidationEvidence = Annotated[
    BinaryValidationEvidence | RegressionValidationEvidence,
    Field(discriminator="task_type"),
]


class LiveNeedsClarification(StrictModel):
    contract_version: ContractVersion
    outcome: Literal["needs_clarification"]
    draft_id: str = Field(pattern=r"^draft_[0-9a-f]{64}$")
    questions: list[ClarificationQuestion] = Field(min_length=1)


class UnsupportedTaskDraft(StrictModel):
    contract_version: ContractVersion
    outcome: Literal["unsupported"]
    draft_id: str = Field(pattern=r"^draft_[0-9a-f]{64}$")
    reason_code: Literal[
        "unsupported_dataset",
        "unsupported_entity",
        "unsupported_target",
        "unsupported_horizon",
        "unsafe_request",
    ]
    explanation: str = Field(min_length=1)


class LiveDraftReady(StrictModel):
    contract_version: ContractVersion
    outcome: Literal["draft_ready"]
    draft_id: str = Field(pattern=r"^draft_[0-9a-f]{64}$")
    contract: TaskContract
    sql_artifact: CustomTaskSqlArtifact
    validation_evidence: TaskValidationEvidence
    review_required: Literal[True]

    @model_validator(mode="after")
    def validate_compiled_artifacts(self) -> LiveDraftReady:
        if self.contract.draft_id != self.draft_id:
            raise ValueError("compiled contract draft ID does not match the response")
        if self.contract.dataset_id != self.sql_artifact.dataset_id:
            raise ValueError("compiled contract dataset does not match its SQL artifact")
        if self.contract.task_type != self.sql_artifact.task_type:
            raise ValueError("compiled contract task type does not match its SQL artifact")
        if self.contract.entity.table != self.sql_artifact.entity_table:
            raise ValueError("compiled contract entity table does not match its SQL artifact")
        if self.contract.entity.key_column != self.sql_artifact.entity_column:
            raise ValueError("compiled contract entity key does not match its SQL artifact")
        if self.contract.horizon.value != self.sql_artifact.horizon_days:
            raise ValueError("compiled contract horizon does not match its SQL artifact")
        if self.validation_evidence.query_sha256 != self.sql_artifact.query_sha256:
            raise ValueError("validation evidence does not match its SQL artifact")
        if self.validation_evidence.task_type != self.sql_artifact.task_type:
            raise ValueError("validation evidence task type does not match its SQL artifact")
        expected_columns = [
            "timestamp",
            self.sql_artifact.entity_column,
            self.sql_artifact.target_column,
        ]
        if self.validation_evidence.columns != expected_columns:
            raise ValueError("validation evidence columns do not match its SQL artifact")
        return self


LiveTaskDraftOutcome = Annotated[
    LiveNeedsClarification | UnsupportedTaskDraft | LiveDraftReady,
    Field(discriminator="outcome"),
]
