from __future__ import annotations

import unittest
from io import BytesIO

from docx import Document
from docx.oxml.ns import qn

from app.exports import build_teaching_plan_docx, build_teaching_plan_pdf


SAMPLE_PLAN = {
    "title": "Direitos humanos no sistema penitenciário",
    "rationale": "Fortalecer a atuação profissional orientada por direitos humanos.",
    "target_audience": "Policiais penais",
    "expected_performance": "Aplicar os princípios em situações de trabalho.",
    "general_objective": "Desenvolver uma atuação segura e fundamentada.",
    "specific_objectives": [
        "Reconhecer princípios de direitos humanos.",
        "Analisar situações críticas do contexto penitenciário.",
    ],
    "modality": "Presencial",
    "total_workload": "8 horas",
    "learning_path": [
        {
            "sequence": 1,
            "title": "Fundamentos",
            "learning_objective": "Reconhecer princípios aplicáveis.",
            "contents": ["Direitos humanos", "Dignidade da pessoa humana"],
            "methodology": ["Estudo dialogado", "Análise de caso"],
            "workload": "4 horas",
            "assessment": ["Análise fundamentada de caso"],
            "mcn_alignment": ["Matriz Curricular Nacional - 2026"],
        },
        {
            "sequence": 2,
            "title": "Aplicação prática",
            "learning_objective": "Tomar decisões em situações simuladas.",
            "contents": ["Uso proporcional da força", "Mediação de conflitos"],
            "methodology": ["Simulação prática"],
            "workload": "4 horas",
            "assessment": ["Rubrica de desempenho"],
            "mcn_alignment": ["Matriz Curricular Nacional - 2026"],
        },
    ],
    "teaching_methods": ["Aprendizagem baseada em problemas"],
    "resources": ["Sala de aula", "Cenário de simulação"],
    "learning_assessment": ["Estudo de caso", "Simulação avaliada"],
    "transfer_impact_assessment": ["Observação orientada no trabalho"],
    "certification_criteria": ["A definir mediante validação"],
    "references": ["MCN 2026", "espens_clean.xlsx"],
    "pending_validations": ["Validar critérios de certificação"],
}


class TeachingPlanExportsTest(unittest.TestCase):
    def test_docx_contains_the_complete_plan_with_letter_page_size(self) -> None:
        content = build_teaching_plan_docx(SAMPLE_PLAN)
        document = Document(BytesIO(content))
        full_text = "\n".join(
            paragraph.text for paragraph in document.paragraphs
        )

        self.assertTrue(content.startswith(b"PK"))
        self.assertIn("Plano de Ensino Direitos humanos", full_text)
        self.assertIn("Trilha de aprendizagem", full_text)
        self.assertIn("Etapa 2 Aplicação prática", full_text)
        self.assertIn("Pendências para validação humana", full_text)
        self.assertIn("Matriz Curricular Nacional - 2026", full_text)
        self.assertIn("Ações Educativas ESPEN", full_text)
        self.assertNotIn("espens_clean.xlsx", full_text)
        self.assertAlmostEqual(document.sections[0].page_width.inches, 8.5, places=1)
        self.assertAlmostEqual(document.sections[0].page_height.inches, 11, places=1)
        self.assertIsNone(
            document.styles["Title"]._element.pPr.find(qn("w:pBdr"))
        )

    def test_pdf_is_generated_as_a_valid_pdf_document(self) -> None:
        content = build_teaching_plan_pdf(SAMPLE_PLAN)

        self.assertTrue(content.startswith(b"%PDF-"))
        self.assertGreater(len(content), 3000)
        self.assertIn(b"%%EOF", content[-1024:])


if __name__ == "__main__":
    unittest.main()
