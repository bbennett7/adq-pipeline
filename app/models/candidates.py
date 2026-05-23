from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Agent(StrEnum):
    CLAUDE = "claude"
    GPT4 = "gpt4"
    GEMINI = "gemini"


class RunStatus(StrEnum):
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    PUBLISHED = "published"
    FAILED = "failed"


class CandidateStatus(StrEnum):
    PENDING = "pending"
    SELECTED = "selected"
    REJECTED = "rejected"
    RESCUED = "rescued"


class CandidateCreate(BaseModel):
    agent: Agent
    question_md: str = Field(alias="questionMd")
    answer_md: str = Field(alias="answerMd")
    score: int = Field(ge=1, le=10)
    review_reason: str = Field(alias="reviewReason")


class Candidate(BaseModel):
    id: str
    run_id: str = Field(alias="runId")
    agent: Agent
    question_md: str = Field(alias="questionMd")
    answer_md: str = Field(alias="answerMd")
    score: int
    review_reason: str = Field(alias="reviewReason")
    question_id: str | None = Field(default=None, alias="questionId")
    status: CandidateStatus
    created_at: datetime = Field(alias="createdAt")
    deleted_at: datetime | None = Field(default=None, alias="deletedAt")

    model_config = {"populate_by_name": True}


class Run(BaseModel):
    id: str
    target_date: datetime = Field(alias="targetDate")
    status: RunStatus
    error_message: str | None = Field(default=None, alias="errorMessage")
    created_at: datetime = Field(alias="createdAt")
    deleted_at: datetime | None = Field(default=None, alias="deletedAt")
    candidates: list[Candidate] = []

    model_config = {"populate_by_name": True}


class GeneratedCandidate(BaseModel):
    """Raw output from a generation model, before review scoring."""

    agent: Agent
    question_md: str
    answer_md: str


class ReviewedCandidate(BaseModel):
    """A candidate after the review pass adds a score and reason."""

    agent: Agent
    question_md: str
    answer_md: str
    score: int = Field(ge=1, le=10)
    review_reason: str
