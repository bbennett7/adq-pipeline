from enum import StrEnum

from pydantic import BaseModel, Field


class Agent(StrEnum):
    CLAUDE = "claude"
    GPT4 = "gpt4"
    GEMINI = "gemini"


class Category(StrEnum):
    CURRENT = "current"
    CULTURAL = "cultural"
    FOUNDATIONAL = "foundational"


class GeneratedCandidate(BaseModel):
    """Raw output from a generation model, before review scoring."""

    agent: Agent
    category: Category = Category.CULTURAL
    question_md: str = Field(min_length=25, max_length=250)
    answer_md: str = Field(min_length=25, max_length=1000)


class ReviewedCandidate(BaseModel):
    """A candidate after the review pass adds a score and reason."""

    agent: Agent
    question_md: str = Field(min_length=25, max_length=250)
    answer_md: str = Field(min_length=25, max_length=1000)
    score: int = Field(ge=1, le=10)
    review_reason: str
