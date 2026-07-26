from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Settings
from app.rag import retrieve_context


class FakeEmbeddings:
    def embed_query(self, _question: str) -> list[float]:
        return [1.0, 0.0]


class RagSeparationTest(unittest.TestCase):
    def test_retrieval_keeps_both_authorized_bases(self) -> None:
        settings = Settings(
            openai_api_key="sk-test",
            openai_model="gpt-4o-mini",
            openai_embedding_model="text-embedding-3-small",
            database_url="sqlite:///./data/local.db",
            target_table="rag_docs",
            target_id_column="id",
            target_text_columns=["titulo", "cadastro", "conteudo"],
            max_rows=2000,
            top_k=2,
        )
        index_data = {
            "embedding_model": "text-embedding-3-small",
            "docs": [
                {
                    "id": "1",
                    "text": "Ação A",
                    "source_name": "espens_clean.xlsx",
                    "source_type": "ações educativas ESPEN",
                },
                {
                    "id": "2",
                    "text": "Ação B",
                    "source_name": "espens_clean.xlsx",
                    "source_type": "ações educativas ESPEN",
                },
                {
                    "id": "38",
                    "text": "Competência A",
                    "source_name": "MCN.docx",
                    "source_type": "Matriz Curricular Nacional 2026",
                },
                {
                    "id": "39",
                    "text": "Competência B",
                    "source_name": "MCN.docx",
                    "source_type": "Matriz Curricular Nacional 2026",
                },
            ],
            "embeddings": [
                [1.0, 0.0],
                [0.9, 0.1],
                [0.8, 0.2],
                [0.7, 0.3],
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "index.json"
            index_path.write_text(json.dumps(index_data), encoding="utf-8")
            with (
                patch("app.rag.INDEX_PATH", index_path),
                patch("app.rag._embedding_client", return_value=FakeEmbeddings()),
            ):
                docs, _sources = retrieve_context("consulta", settings)

        source_types = {doc["source_type"] for doc in docs}
        self.assertEqual(
            source_types,
            {
                "ações educativas ESPEN",
                "Matriz Curricular Nacional 2026",
            },
        )


if __name__ == "__main__":
    unittest.main()
