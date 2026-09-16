from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

import app.main as main_module
from app.analytics import record_interaction
from tests.test_exports import SAMPLE_PLAN


class TeachingPlanExportApiTest(unittest.TestCase):
    def test_export_routes_return_downloadable_docx_and_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir) / 'analytics.db'}"
            session_id = str(uuid4())
            response_id = str(uuid4())
            record_interaction(
                database_url,
                session_id=session_id,
                response_id=response_id,
                user_message="Gere o plano.",
                assistant_response="Plano gerado.",
                input_tokens=10,
                output_tokens=20,
                model="test",
                teaching_plan=SAMPLE_PLAN,
            )

            original_settings = main_module.settings
            main_module.settings = replace(
                original_settings,
                analytics_database_url=database_url,
            )
            try:
                client = TestClient(main_module.app)
                for export_format, media_type, signature in (
                    (
                        "docx",
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document",
                        b"PK",
                    ),
                    ("pdf", "application/pdf", b"%PDF-"),
                ):
                    response = client.get(
                        f"/api/exports/{response_id}",
                        params={
                            "session_id": session_id,
                            "format": export_format,
                        },
                    )

                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["content-type"], media_type)
                    self.assertIn(
                        f"plano-de-ensino.{export_format}",
                        response.headers["content-disposition"],
                    )
                    self.assertTrue(response.content.startswith(signature))
            finally:
                main_module.settings = original_settings

    def test_export_rejects_a_response_from_another_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_settings = main_module.settings
            main_module.settings = replace(
                original_settings,
                analytics_database_url=(
                    f"sqlite:///{Path(temp_dir) / 'analytics.db'}"
                ),
            )
            try:
                client = TestClient(main_module.app)
                response = client.get(
                    f"/api/exports/{uuid4()}",
                    params={"session_id": str(uuid4()), "format": "pdf"},
                )
                self.assertEqual(response.status_code, 404)
            finally:
                main_module.settings = original_settings


if __name__ == "__main__":
    unittest.main()
