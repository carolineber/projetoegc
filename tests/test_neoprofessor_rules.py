from __future__ import annotations

import unittest
from copy import deepcopy

from app.consultation_state import DEFAULT_STATE
from app.neoprofessor import (
    _merge_state,
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
