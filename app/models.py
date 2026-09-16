from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    session_id: str | None = Field(default=None, max_length=64)


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    session_id: str
    response_id: str
    stage: str
    checkpoint: str
    requires_human_validation: bool
    has_explanation: bool
    has_teaching_plan: bool


class ExplanationResponse(BaseModel):
    summary: str
    confirmed_inputs: list[str]
    evidence: list[str]
    pedagogical_criteria: list[str]
    tradeoffs: list[str]
    limitations: list[str]


class FeedbackRequest(BaseModel):
    session_id: str = Field(min_length=36, max_length=36)
    response_id: str = Field(min_length=36, max_length=36)
    rating: Literal["up", "down"]


class FeedbackResponse(BaseModel):
    saved: bool
    rating: Literal["up", "down"]


class IndexResponse(BaseModel):
    indexed_rows: int
    message: str
