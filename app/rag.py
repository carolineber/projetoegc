from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path

from langchain_openai import OpenAIEmbeddings

from app.config import Settings
from app.db import fetch_rows

# In Vercel serverless, code directory is read-only; use /tmp for runtime artifacts.
INDEX_PATH = (
    Path("/tmp/vector_index.json")
    if os.getenv("VERCEL") == "1"
    else Path("data/vector_index.json")
)


def _row_to_text(row: dict, text_columns: list[str]) -> str:
    parts: list[str] = []
    for col in text_columns:
        value = row.get(col)
        if value is None:
            continue
        text_value = str(value).strip()
        if text_value:
            parts.append(f"{col}: {text_value}")
    return "\n".join(parts)


def _embedding_client(settings: Settings) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
        chunk_size=64,
        max_retries=2,
    )


def build_index(settings: Settings) -> int:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY nao configurada.")

    rows = fetch_rows(settings)
    docs: list[dict] = []
    for row in rows:
        text = _row_to_text(row, settings.target_text_columns)
        if not text:
            continue
        docs.append(
            {
                "id": str(row.get(settings.target_id_column, "sem_id")),
                "text": text,
                "source_name": str(row.get("source_name", settings.target_table)),
                "source_type": str(row.get("source_type", "base não identificada")),
            }
        )

    embedding_model = _embedding_client(settings)
    embeddings = embedding_model.embed_documents([doc["text"] for doc in docs])

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(
        json.dumps(
            {
                "embedding_model": settings.openai_embedding_model,
                "built_at": datetime.now(UTC).isoformat(),
                "docs": docs,
                "embeddings": embeddings,
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    return len(docs)


def _load_index(settings: Settings) -> dict:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(
            "Indice vetorial nao encontrado. Rode o endpoint POST /api/index primeiro."
        )
    index_data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    if index_data.get("embedding_model") != settings.openai_embedding_model:
        raise FileNotFoundError(
            "O índice foi criado com outro modelo de embeddings e precisa ser refeito."
        )
    return index_data


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    denominator = norm_a * norm_b
    if denominator == 0:
        return 0.0
    return dot_product / denominator


def retrieve_context(question: str, settings: Settings) -> tuple[list[dict], list[str]]:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY nao configurada.")

    index_data = _load_index(settings)
    docs = index_data["docs"]
    embeddings: list[list[float]] = index_data["embeddings"]

    embedding_model = _embedding_client(settings)
    question_vector = embedding_model.embed_query(question)

    scored: list[tuple[float, int]] = []
    for idx, emb in enumerate(embeddings):
        scored.append((_cosine_similarity(question_vector, emb), idx))

    scored.sort(key=lambda item: item[0], reverse=True)

    source_groups: dict[str, list[tuple[float, int]]] = {}
    for score, index in scored:
        source_type = str(docs[index].get("source_type", "base não identificada"))
        source_groups.setdefault(source_type, []).append((score, index))

    top_items: list[tuple[float, int]] = []
    if len(source_groups) >= 2:
        per_source = max(1, settings.top_k // len(source_groups))
        for group_items in source_groups.values():
            top_items.extend(group_items[:per_source])
        selected_indexes = {index for _, index in top_items}
        for item in scored:
            if len(top_items) >= settings.top_k:
                break
            if item[1] not in selected_indexes:
                top_items.append(item)
                selected_indexes.add(item[1])
        top_items.sort(key=lambda item: item[0], reverse=True)
    else:
        top_items = scored[: settings.top_k]

    selected_docs = [docs[idx] for _, idx in top_items]
    selected_sources = list(dict.fromkeys([
        f"{doc.get('source_name', settings.target_table)} · registro {doc['id']}"
        for doc in selected_docs
    ]))
    return selected_docs, selected_sources
