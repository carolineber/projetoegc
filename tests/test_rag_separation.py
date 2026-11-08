from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore

from app.config import Settings
from app.rag import retrieve_context


class FakeEmbeddings:
    query_calls = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [
            [1.0 - (index * 0.1), index * 0.1]
            for index, _text in enumerate(texts)
        ]

    def embed_query(self, _question: str) -> list[float]:
        self.query_calls += 1
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
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "index.json"
            embeddings = FakeEmbeddings()
            vector_store = InMemoryVectorStore(embeddings)
            vector_store.add_documents(
                [
                    Document(
                        id="1",
                        page_content="Ação A",
                        metadata={
                            "record_id": "1",
                            "source_name": "espens_clean.xlsx",
                            "source_type": "ações educativas ESPEN",
                            "embedding_model": "text-embedding-3-small",
                        },
                    ),
                    Document(
                        id="2",
                        page_content="Ação B",
                        metadata={
                            "record_id": "2",
                            "source_name": "espens_clean.xlsx",
                            "source_type": "ações educativas ESPEN",
                            "embedding_model": "text-embedding-3-small",
                        },
                    ),
                    Document(
                        id="38",
                        page_content="Competência A",
                        metadata={
                            "record_id": "38",
                            "source_name": "MCN.docx",
                            "source_type": "Matriz Curricular Nacional 2026",
                            "embedding_model": "text-embedding-3-small",
                        },
                    ),
                    Document(
                        id="39",
                        page_content="Competência B",
                        metadata={
                            "record_id": "39",
                            "source_name": "MCN.docx",
                            "source_type": "Matriz Curricular Nacional 2026",
                            "embedding_model": "text-embedding-3-small",
                        },
                    ),
                ]
            )
            vector_store.dump(str(index_path))
            with (
                patch("app.rag.INDEX_PATH", index_path),
                patch("app.rag._embedding_client", return_value=embeddings),
            ):
                docs, _sources = retrieve_context("consulta", settings)
                mcn_docs, _mcn_sources = retrieve_context(
                    "competências da MCN",
                    settings,
                    allowed_source_types={"Matriz Curricular Nacional 2026"},
                )

        source_types = {doc["source_type"] for doc in docs}
        self.assertEqual(
            source_types,
            {
                "ações educativas ESPEN",
                "Matriz Curricular Nacional 2026",
            },
        )
        self.assertEqual(
            {doc["source_type"] for doc in mcn_docs},
            {"Matriz Curricular Nacional 2026"},
        )
        self.assertEqual(embeddings.query_calls, 2)


if __name__ == "__main__":
    unittest.main()
