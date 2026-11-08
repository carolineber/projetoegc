from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
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
    documents: list[Document] = []
    for row in rows:
        text = _row_to_text(row, settings.target_text_columns)
        if not text:
            continue
        record_id = str(row.get(settings.target_id_column, "sem_id"))
        documents.append(
            Document(
                id=record_id,
                page_content=text,
                metadata={
                    "record_id": record_id,
                    "source_name": str(
                        row.get("source_name", settings.target_table)
                    ),
                    "source_type": str(
                        row.get("source_type", "base não identificada")
                    ),
                    "embedding_model": settings.openai_embedding_model,
                },
            )
        )

    if not documents:
        raise ValueError("Nenhum documento válido foi encontrado para indexação.")

    vector_store = InMemoryVectorStore(_embedding_client(settings))
    vector_store.add_documents(
        documents=documents,
        ids=[str(document.id) for document in documents],
    )
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = INDEX_PATH.with_name(f"{INDEX_PATH.name}.{uuid4().hex}.tmp")
    vector_store.dump(str(temporary_path))
    temporary_path.replace(INDEX_PATH)
    return len(documents)


def _load_vector_store(settings: Settings) -> InMemoryVectorStore:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(
            "Indice vetorial nao encontrado. Rode o endpoint POST /api/index primeiro."
        )

    raw_index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    if isinstance(raw_index, dict) and {"docs", "embeddings"} <= raw_index.keys():
        raise FileNotFoundError(
            "O índice usa o formato anterior e precisa ser refeito com LangChain."
        )

    vector_store = InMemoryVectorStore.load(
        str(INDEX_PATH),
        embedding=_embedding_client(settings),
    )
    indexed_models = {
        str(item.get("metadata", {}).get("embedding_model", ""))
        for item in vector_store.store.values()
    }
    if indexed_models != {settings.openai_embedding_model}:
        raise FileNotFoundError(
            "O índice foi criado com outro modelo de embeddings e precisa ser refeito."
        )
    return vector_store


def retrieve_context(
    question: str,
    settings: Settings,
    allowed_source_types: set[str] | None = None,
) -> tuple[list[dict], list[str]]:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY nao configurada.")

    vector_store = _load_vector_store(settings)
    source_types = sorted(
        {
            str(item.get("metadata", {}).get("source_type", "base não identificada"))
            for item in vector_store.store.values()
            if allowed_source_types is None
            or str(item.get("metadata", {}).get("source_type", ""))
            in allowed_source_types
        }
    )
    if not source_types:
        raise FileNotFoundError("O índice vetorial está vazio e precisa ser refeito.")

    question_vector = vector_store.embedding.embed_query(question)
    result_limit = max(settings.top_k, len(source_types))
    per_source = max(1, settings.top_k // len(source_types))
    ranked_documents: list[tuple[Document, float]] = []

    for source_type in source_types:
        ranked_documents.extend(
            vector_store.similarity_search_with_score_by_vector(
                question_vector,
                k=per_source,
                filter=lambda document, expected=source_type: str(
                    document.metadata.get("source_type", "base não identificada")
                )
                == expected,
            )
        )

    selected_ids = {str(document.id) for document, _ in ranked_documents}
    if len(ranked_documents) < result_limit:
        overall_results = vector_store.similarity_search_with_score_by_vector(
            question_vector,
            k=result_limit,
        )
        for document, score in overall_results:
            if str(document.id) not in selected_ids:
                ranked_documents.append((document, score))
                selected_ids.add(str(document.id))
            if len(ranked_documents) >= result_limit:
                break

    ranked_documents.sort(key=lambda item: item[1], reverse=True)
    ranked_documents = ranked_documents[:result_limit]
    selected_docs = [
        {
            "id": str(document.metadata.get("record_id", document.id or "sem_id")),
            "text": document.page_content,
            "source_name": str(
                document.metadata.get("source_name", settings.target_table)
            ),
            "source_type": str(
                document.metadata.get("source_type", "base não identificada")
            ),
            "score": score,
        }
        for document, score in ranked_documents
    ]
    selected_sources = list(
        dict.fromkeys(
            [
                f"{doc['source_name']} · registro {doc['id']}"
                for doc in selected_docs
            ]
        )
    )
    return selected_docs, selected_sources
