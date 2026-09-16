from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from app.analytics import (
    get_explanation,
    get_teaching_plan,
    record_interaction,
    update_feedback,
)


class FeedbackTest(unittest.TestCase):
    def test_interaction_and_feedback_are_saved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "analytics.db"
            database_url = f"sqlite:///{database_path}"
            session_id = str(uuid4())
            response_id = str(uuid4())

            record_interaction(
                database_url,
                session_id=session_id,
                response_id=response_id,
                user_message="Pergunta",
                assistant_response="Resposta",
                input_tokens=120,
                output_tokens=30,
                model="gpt-4o-mini",
                explanation={
                    "summary": "A prática aproxima a formação do trabalho.",
                    "confirmed_inputs": ["Público: policiais penais"],
                    "evidence": ["MCN 2026", "espens_clean.xlsx"],
                    "pedagogical_criteria": ["Aprendizagem situada"],
                    "tradeoffs": ["Exige ambiente de simulação"],
                    "limitations": ["Carga horária pendente"],
                },
                teaching_plan={"title": "Direitos humanos"},
            )
            update_feedback(
                database_url,
                session_id=session_id,
                response_id=response_id,
                rating="up",
            )

            with sqlite3.connect(database_path) as connection:
                sessions = connection.execute(
                    "SELECT id FROM chat_sessions"
                ).fetchall()
                interactions = connection.execute(
                    """
                    SELECT id, session_id, user_message, assistant_response,
                           feedback, input_tokens, output_tokens, total_tokens
                    FROM chat_interactions
                    """
                ).fetchall()

            self.assertEqual(sessions, [(session_id,)])
            self.assertEqual(
                interactions,
                [
                    (
                        response_id,
                        session_id,
                        "Pergunta",
                        "Resposta",
                        "👍",
                        120,
                        30,
                        150,
                    )
                ],
            )
            self.assertEqual(
                get_teaching_plan(
                    database_url,
                    session_id=session_id,
                    response_id=response_id,
                ),
                {"title": "Direitos humanos"},
            )
            self.assertEqual(
                get_explanation(
                    database_url,
                    session_id=session_id,
                    response_id=response_id,
                )["evidence"],
                [
                    "Matriz Curricular Nacional - 2026",
                    "Ações Educativas ESPEN",
                ],
            )

    def test_feedback_rejects_an_unknown_response(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'analytics.db'}"
            with self.assertRaisesRegex(ValueError, "não encontrada"):
                update_feedback(
                    database_url,
                    session_id=str(uuid4()),
                    response_id=str(uuid4()),
                    rating="down",
                )

    def test_explanation_is_scoped_to_its_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'analytics.db'}"
            session_id = str(uuid4())
            response_id = str(uuid4())
            record_interaction(
                database_url,
                session_id=session_id,
                response_id=response_id,
                user_message="Pergunta",
                assistant_response="Resposta",
                input_tokens=1,
                output_tokens=1,
                model="test",
                explanation={"summary": "Justificativa"},
            )

            with self.assertRaisesRegex(ValueError, "não encontrada"):
                get_explanation(
                    database_url,
                    session_id=str(uuid4()),
                    response_id=response_id,
                )


if __name__ == "__main__":
    unittest.main()
