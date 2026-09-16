from __future__ import annotations

import unittest
from copy import deepcopy
from unittest.mock import patch

from app.config import get_settings
from app.consultation_state import DEFAULT_STATE
from app.neoprofessor import (
    LearningPathStep,
    REQUIRED_DIAGNOSTIC_FIELDS,
    TeachingPlan,
    _merge_state,
    _normalize_rationale_sources,
    _planning_requested,
    _public_sources,
    _render_teaching_plan,
    _sanitize_public_text,
    _usage_totals,
    _validate_answer,
    determine_stage,
)


def agent_output(**overrides) -> dict:
    state_updates = {
        "objetivo": "",
        "confirmed_fields": [],
        "document_evidence": [],
        "interpretations": [],
        "recommendations": [],
        "human_decisions": [],
        "gaps": [],
        "contradictions": [],
        "risks": [],
        "validation_items": [],
        "next_step": "",
    }
    state_updates.update(overrides)
    return {
        "answer": "Resposta preliminar.",
        "proposed_stage": "DIAGNOSTICO",
        "requires_human_validation": False,
        "state_updates": state_updates,
    }


class NeoprofessorRulesTest(unittest.TestCase):
    def test_completion_limit_defaults_to_eight_thousand_tokens(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = get_settings()

        self.assertEqual(settings.openai_max_completion_tokens, 8000)

    def test_completion_limit_can_be_configured(self) -> None:
        with patch.dict(
            "os.environ", {"OPENAI_MAX_COMPLETION_TOKENS": "10000"}, clear=True
        ):
            settings = get_settings()

        self.assertEqual(settings.openai_max_completion_tokens, 10000)

    def test_rationale_uses_canonical_mcn_source_name(self) -> None:
        rationale = {
            "summary": "Recomendação.",
            "confirmed_inputs": [],
            "evidence": ["MCN 2026", "Informação do usuário"],
            "pedagogical_criteria": [],
            "tradeoffs": [],
            "limitations": [],
        }

        normalized = _normalize_rationale_sources(
            rationale,
            [{"source_type": "Matriz Curricular Nacional 2026"}],
        )

        self.assertEqual(
            normalized["evidence"],
            ["Matriz Curricular Nacional - 2026", "Informação do usuário"],
        )

    def test_internal_spreadsheet_name_never_reaches_public_content(self) -> None:
        rationale = {
            "summary": "Recomendação.",
            "confirmed_inputs": [],
            "evidence": ["espens_clean.xlsx"],
            "pedagogical_criteria": [],
            "tradeoffs": [],
            "limitations": [],
        }

        normalized = _normalize_rationale_sources(rationale, [])

        self.assertEqual(normalized["evidence"], ["Ações Educativas ESPEN"])
        self.assertEqual(
            _sanitize_public_text("Fonte: espens_clean.xlsx"),
            "Fonte: Ações Educativas ESPEN",
        )
        self.assertEqual(
            _public_sources(["espens_clean.xlsx · registro 12"]),
            ["Ações Educativas ESPEN"],
        )

    def test_explicit_plan_request_always_selects_planning_output(self) -> None:
        state = deepcopy(DEFAULT_STATE)

        self.assertTrue(
            _planning_requested("Pode gerar o plano de ensino agora?", state)
        )

    def test_confirmation_selects_plan_only_after_alternatives(self) -> None:
        state = deepcopy(DEFAULT_STATE)
        self.assertFalse(_planning_requested("Confirmo.", state))

        state["estado_atual"] = "VALIDACAO"
        state["recomendacoes_do_agente"] = ["Adotar uma trilha prática."]
        self.assertTrue(_planning_requested("Confirmo a opção escolhida.", state))

    def test_teaching_plan_renderer_includes_path_and_pending_items(self) -> None:
        plan = TeachingPlan(
            title="Ética no serviço penal",
            rationale="Necessidade confirmada pelo usuário.",
            target_audience="Policiais penais",
            expected_performance="Aplicar princípios éticos.",
            general_objective="Desenvolver atuação ética.",
            specific_objectives=["Analisar dilemas éticos."],
            modality="Presencial",
            total_workload="8 horas",
            learning_path=[
                LearningPathStep(
                    sequence=1,
                    title="Fundamentos",
                    learning_objective="Reconhecer princípios éticos.",
                    contents=["Ética e serviço público"],
                    methodology=["Estudo de caso"],
                    workload="4 horas",
                    assessment=["Análise de caso"],
                    mcn_alignment=["Competência MCN pertinente"],
                )
            ],
            teaching_methods=["Aprendizagem baseada em problemas"],
            resources=["Sala de aula"],
            learning_assessment=["Rubrica"],
            transfer_impact_assessment=["Observação no trabalho"],
            certification_criteria=["A definir mediante validação"],
            references=["MCN 2026"],
            pending_validations=["Validar carga horária"],
        )

        rendered = _render_teaching_plan(plan)

        self.assertIn("Plano de Ensino — Ética no serviço penal", rendered)
        self.assertIn("Trilha de aprendizagem", rendered)
        self.assertIn("Etapa 1 — Fundamentos", rendered)
        self.assertIn("Validar carga horária", rendered)

    def test_usage_totals_sum_model_metadata(self) -> None:
        self.assertEqual(
            _usage_totals(
                {
                    "model-a": {"input_tokens": 120, "output_tokens": 30},
                    "model-b": {"input_tokens": 10, "output_tokens": 5},
                }
            ),
            (130, 35),
        )

    def test_diagnostic_gate_blocks_premature_planning(self) -> None:
        state = deepcopy(DEFAULT_STATE)
        state["recomendacoes_do_agente"] = ["Criar uma trilha."]
        state["decisoes_humanas"] = ["Seguir com a trilha."]

        self.assertEqual(determine_stage(state, False), "DIAGNOSTICO")

    def test_planning_requires_core_fields_and_human_decision(self) -> None:
        state = deepcopy(DEFAULT_STATE)
        state["campos_confirmados"] = {
            "problema_ou_oportunidade": "Falha de procedimento",
            "publico": "Policiais penais",
            "desempenho_esperado": "Executar o procedimento com segurança",
        }
        state["recomendacoes_do_agente"] = ["Simulação prática."]
        self.assertEqual(determine_stage(state, False), "ALTERNATIVAS")

        state["decisoes_humanas"] = ["Validada a simulação prática."]
        self.assertEqual(determine_stage(state, False), "PLANEJAMENTO")

    def test_complete_stage_progression_does_not_stick_in_diagnostic(self) -> None:
        state = deepcopy(DEFAULT_STATE)
        self.assertEqual(determine_stage(state, False), "DIAGNOSTICO")

        state["campos_confirmados"] = {
            "problema_ou_oportunidade": "Decisões inconsistentes",
            "publico": "Policiais penais",
            "desempenho_esperado": "Decidir com fundamento ético",
        }
        self.assertEqual(determine_stage(state, False), "DELIMITACAO")

        state["recomendacoes_do_agente"] = ["Trilha prática com estudos de caso"]
        self.assertEqual(determine_stage(state, False), "ALTERNATIVAS")

        state["itens_que_exigem_validacao"] = ["Validar a trilha"]
        self.assertEqual(determine_stage(state, False), "VALIDACAO")

        state["itens_que_exigem_validacao"] = []
        state["decisoes_humanas"] = ["Trilha validada"]
        self.assertEqual(determine_stage(state, False), "PLANEJAMENTO")

    def test_only_literal_user_evidence_becomes_confirmed(self) -> None:
        message = "O público são policiais penais."
        output = agent_output(
            confirmed_fields=[
                {
                    "key": "publico",
                    "value": "Policiais penais",
                    "evidence_quote": "policiais penais",
                },
                {
                    "key": "carga_horaria",
                    "value": "40 horas",
                    "evidence_quote": "40 horas",
                },
            ]
        )

        state = _merge_state(deepcopy(DEFAULT_STATE), output, message, [])

        self.assertEqual(
            state["campos_confirmados"]["publico"], "Policiais penais"
        )
        self.assertNotIn("carga_horaria", state["campos_confirmados"])

    def test_legacy_labels_are_normalized_and_release_diagnostic_gate(self) -> None:
        message = (
            "O problema é decisão inconsistente. O público são policiais penais. "
            "O desempenho esperado é decidir com fundamento ético."
        )
        output = agent_output(
            confirmed_fields=[
                {
                    "key": "Natureza do problema de desempenho",
                    "value": "Decisão inconsistente",
                    "evidence_quote": "decisão inconsistente",
                },
                {
                    "key": "Público-alvo",
                    "value": "Policiais penais",
                    "evidence_quote": "policiais penais",
                },
                {
                    "key": "Desempenho esperado",
                    "value": "Decidir com fundamento ético",
                    "evidence_quote": "decidir com fundamento ético",
                },
            ]
        )

        state = _merge_state(deepcopy(DEFAULT_STATE), output, message, [])

        self.assertEqual(
            set(state["campos_confirmados"]),
            REQUIRED_DIAGNOSTIC_FIELDS,
        )
        self.assertEqual(determine_stage(state, False), "DELIMITACAO")

    def test_human_decision_requires_explicit_confirmation(self) -> None:
        output = agent_output(
            human_decisions=[
                {
                    "decision": "Adotar simulação prática.",
                    "evidence_quote": "simulação prática",
                }
            ]
        )
        state_without_confirmation = _merge_state(
            deepcopy(DEFAULT_STATE),
            output,
            "Talvez uma simulação prática.",
            [],
        )
        self.assertEqual(state_without_confirmation["decisoes_humanas"], [])

        state_with_confirmation = _merge_state(
            deepcopy(DEFAULT_STATE),
            output,
            "Confirmo a simulação prática.",
            [],
        )
        self.assertEqual(
            state_with_confirmation["decisoes_humanas"],
            ["Adotar simulação prática."],
        )

    def test_unilateral_approval_language_is_rewritten(self) -> None:
        state = deepcopy(DEFAULT_STATE)
        answer = _validate_answer("A ação foi aprovada.", state)

        self.assertNotIn("foi aprovada", answer.casefold())
        self.assertIn("proposta preliminar", answer.casefold())

    def test_control_register_is_kept_out_of_visible_answer(self) -> None:
        state = deepcopy(DEFAULT_STATE)
        answer = _validate_answer(
            "1. **Síntese do entendimento**\nConteúdo visível.\n\n"
            "7. **Registro de controle**\nEstado atual: diagnóstico.",
            state,
        )

        self.assertIn("Conteúdo visível", answer)
        self.assertNotIn("Registro de controle", answer)
        self.assertNotIn("Estado atual", answer)


if __name__ == "__main__":
    unittest.main()
