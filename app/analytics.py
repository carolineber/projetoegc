from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    select,
    update,
)
from sqlalchemy.engine import Engine

metadata = MetaData()
MCN_SOURCE_LABEL = "Matriz Curricular Nacional - 2026"
ACTIONS_SOURCE_LABEL = "Ações Educativas ESPEN"

chat_sessions = Table(
    "chat_sessions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
)

chat_interactions = Table(
    "chat_interactions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "session_id",
        String(36),
        ForeignKey("chat_sessions.id"),
        nullable=False,
        index=True,
    ),
    Column("user_message", Text, nullable=False),
    Column("assistant_response", Text, nullable=False),
    Column("feedback", String(4), nullable=True),
    Column("input_tokens", Integer, nullable=False, default=0),
    Column("output_tokens", Integer, nullable=False, default=0),
    Column("total_tokens", Integer, nullable=False, default=0),
    Column("model", String(120), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("feedback_at", DateTime(timezone=True), nullable=True),
)

chat_explanations = Table(
    "chat_explanations",
    metadata,
    Column(
        "response_id",
        String(36),
        ForeignKey("chat_interactions.id"),
        primary_key=True,
    ),
    Column("session_id", String(36), nullable=False, index=True),
    Column("explanation_json", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

chat_teaching_plans = Table(
    "chat_teaching_plans",
    metadata,
    Column(
        "response_id",
        String(36),
        ForeignKey("chat_interactions.id"),
        primary_key=True,
    ),
    Column("session_id", String(36), nullable=False, index=True),
    Column("plan_json", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


@lru_cache(maxsize=4)
def _engine(database_url: str) -> Engine:
    engine = create_engine(
        _normalize_database_url(database_url),
        pool_pre_ping=True,
    )
    metadata.create_all(engine)
    return engine


def record_interaction(
    database_url: str,
    *,
    session_id: str,
    response_id: str,
    user_message: str,
    assistant_response: str,
    input_tokens: int,
    output_tokens: int,
    model: str,
    explanation: dict | None = None,
    teaching_plan: dict | None = None,
) -> None:
    engine = _engine(database_url)
    timestamp = _now()
    with engine.begin() as connection:
        session_exists = connection.execute(
            select(chat_sessions.c.id).where(chat_sessions.c.id == session_id)
        ).first()
        if not session_exists:
            connection.execute(
                chat_sessions.insert().values(id=session_id, started_at=timestamp)
            )

        connection.execute(
            chat_interactions.insert().values(
                id=response_id,
                session_id=session_id,
                user_message=user_message,
                assistant_response=assistant_response,
                feedback=None,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                model=model,
                created_at=timestamp,
                feedback_at=None,
            )
        )
        if explanation:
            connection.execute(
                chat_explanations.insert().values(
                    response_id=response_id,
                    session_id=session_id,
                    explanation_json=json.dumps(explanation, ensure_ascii=False),
                    created_at=timestamp,
                )
            )
        if teaching_plan:
            connection.execute(
                chat_teaching_plans.insert().values(
                    response_id=response_id,
                    session_id=session_id,
                    plan_json=json.dumps(teaching_plan, ensure_ascii=False),
                    created_at=timestamp,
                )
            )


def get_teaching_plan(
    database_url: str,
    *,
    session_id: str,
    response_id: str,
) -> dict:
    engine = _engine(database_url)
    with engine.connect() as connection:
        stored = connection.execute(
            select(chat_teaching_plans.c.plan_json).where(
                chat_teaching_plans.c.response_id == response_id,
                chat_teaching_plans.c.session_id == session_id,
            )
        ).scalar_one_or_none()

    if stored is None:
        raise ValueError("Plano de ensino não encontrado para esta resposta.")
    return json.loads(stored)


def get_explanation(
    database_url: str,
    *,
    session_id: str,
    response_id: str,
) -> dict:
    engine = _engine(database_url)
    with engine.connect() as connection:
        stored = connection.execute(
            select(chat_explanations.c.explanation_json).where(
                chat_explanations.c.response_id == response_id,
                chat_explanations.c.session_id == session_id,
            )
        ).scalar_one_or_none()

    if stored is None:
        raise ValueError("Justificativa não encontrada para esta resposta.")
    explanation = json.loads(stored)
    normalized_evidence: list[str] = []
    for item in explanation.get("evidence", []):
        item_text = str(item)
        normalized_item = item_text.casefold()
        if "mcn" in normalized_item or "matriz curricular nacional" in normalized_item:
            item_text = MCN_SOURCE_LABEL
        elif "espens_clean.xlsx" in normalized_item:
            item_text = ACTIONS_SOURCE_LABEL
        normalized_evidence.append(item_text)
    explanation["evidence"] = list(dict.fromkeys(normalized_evidence))
    return explanation


def update_feedback(
    database_url: str,
    *,
    session_id: str,
    response_id: str,
    rating: str,
) -> None:
    feedback = {"up": "👍", "down": "👎"}.get(rating)
    if feedback is None:
        raise ValueError("Avaliação inválida.")

    engine = _engine(database_url)
    with engine.begin() as connection:
        result = connection.execute(
            update(chat_interactions)
            .where(
                chat_interactions.c.id == response_id,
                chat_interactions.c.session_id == session_id,
            )
            .values(feedback=feedback, feedback_at=_now())
        )
        if result.rowcount != 1:
            raise ValueError("Resposta do assistente não encontrada nesta sessão.")
