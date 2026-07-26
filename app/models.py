from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    session_id: str | None = Field(default=None, max_length=64)


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    session_id: str
    stage: str
    checkpoint: str
    requires_human_validation: bool


class IndexResponse(BaseModel):
    indexed_rows: int
    message: str
