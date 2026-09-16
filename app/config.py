from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

NEOPROFESSOR_MODEL = "gpt-4o-mini"


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    openai_embedding_model: str
    database_url: str
    target_table: str
    target_id_column: str
    target_text_columns: list[str]
    max_rows: int
    top_k: int
    analytics_database_url: str = "sqlite:///./data/chat_analytics.db"
    openai_max_completion_tokens: int = 8000


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def get_settings() -> Settings:
    default_analytics_url = (
        "sqlite:////tmp/chat_analytics.db"
        if os.getenv("VERCEL") == "1"
        else "sqlite:///./data/chat_analytics.db"
    )
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=NEOPROFESSOR_MODEL,
        openai_embedding_model=os.getenv(
            "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
        ),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/local.db"),
        analytics_database_url=os.getenv(
            "ANALYTICS_DATABASE_URL", default_analytics_url
        ),
        openai_max_completion_tokens=int(
            os.getenv("OPENAI_MAX_COMPLETION_TOKENS", "8000")
        ),
        target_table=os.getenv("TARGET_TABLE", "rag_docs"),
        target_id_column=os.getenv("TARGET_ID_COLUMN", "id"),
        target_text_columns=_split_csv(
            os.getenv("TARGET_TEXT_COLUMNS", "titulo,cadastro,conteudo")
        ),
        max_rows=int(os.getenv("MAX_ROWS", "2000")),
        top_k=int(os.getenv("TOP_K", "6")),
    )
