from __future__ import annotations

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
