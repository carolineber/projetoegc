from __future__ import annotations

import json
import math
from pathlib import Path

from openai import OpenAI

from app.config import Settings
from app.db import fetch_rows

INDEX_PATH = Path("data/vector_index.json")


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


def _embed_texts(client: OpenAI, model: str, texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]


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
            }
        )

    client = OpenAI(api_key=settings.openai_api_key)
    embeddings = _embed_texts(
        client, settings.openai_embedding_model, [doc["text"] for doc in docs]
    )

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(
        json.dumps({"docs": docs, "embeddings": embeddings}, ensure_ascii=True),
        encoding="utf-8",
    )
    return len(docs)


def _load_index() -> dict:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(
            "Indice vetorial nao encontrado. Rode o endpoint POST /api/index primeiro."
        )
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


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

    index_data = _load_index()
    docs = index_data["docs"]
    embeddings: list[list[float]] = index_data["embeddings"]

    client = OpenAI(api_key=settings.openai_api_key)
    question_embedding = (
        client.embeddings.create(model=settings.openai_embedding_model, input=question)
        .data[0]
        .embedding
    )
    question_vector = list(question_embedding)

    scored: list[tuple[float, int]] = []
    for idx, emb in enumerate(embeddings):
        scored.append((_cosine_similarity(question_vector, emb), idx))

    scored.sort(key=lambda item: item[0], reverse=True)
    top_items = scored[: settings.top_k]

    selected_docs = [docs[idx] for _, idx in top_items]
    selected_sources = [f"{settings.target_table}:{doc['id']}" for doc in selected_docs]
    return selected_docs, selected_sources


def answer_question(question: str, settings: Settings) -> tuple[str, list[str]]:
    selected_docs, sources = retrieve_context(question, settings)
    context_text = "\n\n---\n\n".join([doc["text"] for doc in selected_docs])

    system_prompt = (
        "Você é um assistente que responde usando apenas o contexto fornecido. "
        "Se o contexto não tiver dados suficientes, diga claramente que não encontrou no banco."
    )

    user_prompt = (
        f"Pergunta do usuario:\n{question}\n\n"
        f"Contexto recuperado do banco:\n{context_text}\n\n"
        "Responda em portugues e de forma objetiva."
    )

    client = OpenAI(api_key=settings.openai_api_key)
    completion = client.chat.completions.create(
        model=settings.openai_model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    answer = completion.choices[0].message.content or "Nao consegui gerar resposta."
    return answer, sources
