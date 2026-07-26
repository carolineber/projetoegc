from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.config import NEOPROFESSOR_MODEL, Settings
from app.consultation_state import (
    append_message,
    checkpoint_summary,
    get_recent_messages,
    load_or_create_session,
    save_state,
)
from app.rag import retrieve_context

SYSTEM_PROMPT = """
Você é o Neoprofessor ESPEN, consultor pedagógico especializado no planejamento
de ações educativas. Atue como interlocutor cognitivo, coconstrutor e
organizador do processo. Você não é uma autoridade curricular autônoma.

IDENTIDADE E TOM
Seja profissional, acolhedor, analítico, didático, prudente, sintético e
objetivo. Trabalhe com o usuário, nunca no lugar dele. Não seja autoritário,
excessivamente entusiasmado, professoral, burocrático ou interrogatório.

PRINCÍPIOS PERMANENTES
1. Recupere e organize o que já foi informado antes de perguntar.
2. Pergunte apenas sobre lacunas ausentes, ambíguas ou contraditórias que
   afetem a próxima decisão. Agrupe poucas perguntas por decisão pedagógica.
3. Quando houver muitos registros, apresente síntese global e destaque somente
   exceções, contradições, especializações e itens críticos.
4. Não proponha ação educativa antes de compreender suficientemente problema,
   público, desempenho esperado, evidências e restrições.
5. Quando não houver solução única, apresente duas ou três alternativas com
   benefícios, limitações, riscos, condições e consequências práticas.
6. Não defina unilateralmente obrigatoriedade, certificação, carga horária,
   prioridade institucional ou aprovação.
7. Não invente evidências, normas, fatos, fontes, citações ou dados ausentes.
   Ausência de evidência não significa inexistência da prática.
8. Não transforme automaticamente cada competência em curso ou disciplina.
9. Diferencie informação do usuário, evidência documental, interpretação,
   recomendação, decisão humana validada e pendência.
10. Sinalize risco, sigilo, contradição material, fonte não autorizada ou falta
    de entrada indispensável.
11. Registre decisões, responsáveis, evidências, alternativas, pendências e
    próximo passo. Nunca declare uma ação educativa aprovada.

FLUXO
COMPREENDER → ORGANIZAR → IDENTIFICAR LACUNAS → PERGUNTAR EM BLOCOS CURTOS →
SINTETIZAR → APRESENTAR ALTERNATIVAS → EXPLICAR IMPACTOS E RISCOS →
SOLICITAR VALIDAÇÃO → PLANEJAR → REGISTRAR DECISÕES E PENDÊNCIAS.

BASES AUTORIZADAS
- Ações Educativas ESPEN: registros de ações já existentes.
- Matriz Curricular Nacional 2026: competências que podem precisar estar
  contempladas nas ações.
As bases são diferentes. Nunca trate uma competência como se fosse uma ação
educativa. Relacione-as somente quando pedagogicamente pertinente.

CONDUTA EM CADA INTERAÇÃO
Identifique objetivo, etapa, dados já confirmados, lacunas e contradições.
Decida se deve perguntar, sintetizar, recomendar ou aguardar validação.
Se precisar perguntar, explique brevemente por quê e faça poucas perguntas.
Se houver informação suficiente, produza recomendação preliminar rastreável e
indique explicitamente o que depende de validação humana.

FORMATO DA RESPOSTA
Use apenas as seções necessárias, preservando esta ordem:
1. Síntese do entendimento
2. Lacunas ou tensões relevantes
3. Alternativas ou recomendação preliminar
4. Consequências e riscos
5. Decisão necessária do usuário
6. Próximo passo
Use “proposta preliminar”, “recomendação para validação” ou “alternativa
coconstruída”; jamais apresente recomendação como decisão institucional.

REGISTRO INTERNO
Mantenha decisões, evidências, pendências, etapa e próximo passo exclusivamente
em state_updates. Nunca inclua “Registro de controle”, fontes, identificadores
de registros, estado interno ou metadados de rastreabilidade no texto visível
de answer.
""".strip()

REQUIRED_DIAGNOSTIC_FIELDS = {
    "problema_ou_oportunidade",
    "publico",
    "desempenho_esperado",
}
HUMAN_CONFIRMATION_MARKERS = (
    "confirmo",
    "confirmado",
    "valido",
    "validado",
    "aprovo",
    "aprovado",
    "escolho",
    "decido",
    "pode seguir",
    "vamos com",
    "opção",
    "alternativa",
)
HIGH_IMPACT_TERMS = (
    "obrigatoriedade",
    "certificação",
    "carga horária",
    "prioridade institucional",
    "aprovação",
)


class ConfirmedField(BaseModel):
    key: str = Field(description="Nome canônico do campo pedagógico.")
    value: str = Field(description="Valor confirmado pelo usuário.")
    evidence_quote: str = Field(
        description="Citação literal curta da mensagem atual que sustenta o valor."
    )


class HumanDecision(BaseModel):
    decision: str = Field(description="Decisão explicitamente validada pelo usuário.")
    evidence_quote: str = Field(
        description="Citação literal curta da mensagem atual que confirma a decisão."
    )


class StateUpdates(BaseModel):
    objetivo: str
    confirmed_fields: list[ConfirmedField]
    document_evidence: list[str]
    interpretations: list[str]
    recommendations: list[str]
    human_decisions: list[HumanDecision]
    gaps: list[str]
    contradictions: list[str]
    risks: list[str]
    validation_items: list[str]
    next_step: str


class AgentOutput(BaseModel):
    answer: str
    proposed_stage: str = Field(
        pattern="^(DIAGNOSTICO|DELIMITACAO|ALTERNATIVAS|VALIDACAO|PLANEJAMENTO)$"
    )
    requires_human_validation: bool
    state_updates: StateUpdates


CONSULTATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        (
            "system",
            """
ESTADO ESTRUTURADO ATUAL:
{state_json}

HISTÓRICO RECENTE:
{recent_messages_json}

EVIDÊNCIAS RAG AUTORIZADAS E SEPARADAS POR BASE:
{rag_context}

Atualize o estado somente com dados sustentados pela mensagem atual ou pelas
fontes listadas. Em confirmed_fields e human_decisions, evidence_quote deve ser
uma citação literal curta da mensagem atual. Em document_evidence, use
exatamente um dos rótulos de fonte recebidos.
""".strip(),
        ),
        ("human", "{question}"),
    ]
)


def _normalized(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(
        char for char in normalized if not unicodedata.combining(char)
    ).casefold()


def _quote_is_grounded(quote: str, user_message: str) -> bool:
    quote_normalized = _normalized(quote.strip())
    message_normalized = _normalized(user_message)
    return bool(quote_normalized) and quote_normalized in message_normalized


def _deduplicate(values: list[str], limit: int = 50) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean_value = str(value).strip()
        key = _normalized(clean_value)
        if clean_value and key not in seen:
            seen.add(key)
            result.append(clean_value)
        if len(result) >= limit:
            break
    return result


def _merge_state(
    state: dict,
    output: dict,
    user_message: str,
    allowed_sources: list[str],
) -> dict:
    updates = output["state_updates"]
    confirmed_fields = state.setdefault("campos_confirmados", {})

    objective = str(updates.get("objetivo", "")).strip()
    if objective and _normalized(objective) in _normalized(user_message):
        state["objetivo"] = objective

    new_confirmations: list[str] = []
    for item in updates.get("confirmed_fields", []):
        key = str(item.get("key", "")).strip()
        value = str(item.get("value", "")).strip()
        quote = str(item.get("evidence_quote", "")).strip()
        if key and value and _quote_is_grounded(quote, user_message):
            confirmed_fields[key] = value
            new_confirmations.append(f"{key}: {value}")

    state["informacoes_confirmadas"] = _deduplicate(
        state.get("informacoes_confirmadas", []) + new_confirmations
    )

    allowed_source_keys = {_normalized(source) for source in allowed_sources}
    grounded_evidence = [
        evidence
        for evidence in updates.get("document_evidence", [])
        if _normalized(evidence) in allowed_source_keys
    ]
    state["evidencias_documentais"] = _deduplicate(
        state.get("evidencias_documentais", []) + grounded_evidence
    )
    state["interpretacoes_do_agente"] = _deduplicate(
        updates.get("interpretations", [])
    )
    state["recomendacoes_do_agente"] = _deduplicate(
        updates.get("recommendations", [])
    )
    state["lacunas"] = _deduplicate(updates.get("gaps", []))
    state["contradicoes"] = _deduplicate(updates.get("contradictions", []))
    state["riscos"] = _deduplicate(updates.get("risks", []))
    state["itens_que_exigem_validacao"] = _deduplicate(
        updates.get("validation_items", [])
    )
    state["proximo_passo"] = str(updates.get("next_step", "")).strip()

    user_normalized = _normalized(user_message)
    has_confirmation_marker = any(
        marker in user_normalized for marker in HUMAN_CONFIRMATION_MARKERS
    )
    accepted_decisions: list[str] = []
    if has_confirmation_marker:
        for item in updates.get("human_decisions", []):
            decision = str(item.get("decision", "")).strip()
            quote = str(item.get("evidence_quote", "")).strip()
            if decision and _quote_is_grounded(quote, user_message):
                accepted_decisions.append(decision)

    if accepted_decisions:
        state["decisoes_humanas"] = _deduplicate(
            state.get("decisoes_humanas", []) + accepted_decisions
        )
        state["ultima_confirmacao_humana"] = user_message

    return state


def determine_stage(state: dict, requires_human_validation: bool) -> str:
    confirmed_fields = set(state.get("campos_confirmados", {}))
    if not REQUIRED_DIAGNOSTIC_FIELDS.issubset(confirmed_fields):
        return "DIAGNOSTICO"
    if state.get("contradicoes"):
        return "DIAGNOSTICO"
    if not state.get("recomendacoes_do_agente"):
        return "DELIMITACAO"
    if requires_human_validation or state.get("itens_que_exigem_validacao"):
        return "VALIDACAO"
    if not state.get("decisoes_humanas"):
        return "ALTERNATIVAS"
    return "PLANEJAMENTO"


def _validate_answer(answer: str, state: dict) -> str:
    cleaned = answer.strip()
    control_heading = re.search(
        r"(?im)^\s*(?:7\.\s*)?(?:#{1,6}\s*)?"
        r"(?:\*\*)?registro de controle(?:\*\*)?\s*:?\s*$",
        cleaned,
    )
    if control_heading:
        cleaned = cleaned[: control_heading.start()].rstrip()
    cleaned = re.sub(
        r"\b(está|foi)\s+aprovad[ao]\b",
        "é uma proposta preliminar para validação",
        cleaned,
        flags=re.IGNORECASE,
    )
    if state["estado_atual"] != "PLANEJAMENTO":
        definitive_high_impact = any(
            _normalized(term) in _normalized(cleaned) for term in HIGH_IMPACT_TERMS
        )
        if definitive_high_impact and "valid" not in _normalized(cleaned):
            cleaned += (
                "\n\nDecisão necessária do usuário\n"
                "Qualquer definição de alto impacto permanece pendente de "
                "validação humana."
            )
    return cleaned


def _consultation_context(state: dict) -> str:
    return " ".join(
        [
            str(state.get("objetivo", "")),
            *state.get("informacoes_confirmadas", []),
            *state.get("lacunas", []),
        ]
    ).strip()


def run_consultation(
    question: str,
    settings: Settings,
    requested_session_id: str | None,
) -> dict[str, Any]:
    if not settings.openai_api_key:
        raise ValueError(
            "OPENAI_API_KEY não configurada. Adicione a chave ao arquivo .env."
        )

    session_id, state = load_or_create_session(requested_session_id)
    recent_messages = get_recent_messages(session_id)
    search_query = " ".join(
        filter(None, [_consultation_context(state), question])
    )
    selected_docs, sources = retrieve_context(search_query, settings)

    separated_context: list[str] = []
    for doc in selected_docs:
        separated_context.append(
            f"[BASE: {doc.get('source_type', 'não identificada')}]\n"
            f"[FONTE: {doc.get('source_name', 'não identificada')} · "
            f"registro {doc.get('id', 'sem id')}]\n{doc['text']}"
        )
    context_text = "\n\n---\n\n".join(separated_context)

    model = ChatOpenAI(
        model=NEOPROFESSOR_MODEL,
        api_key=settings.openai_api_key,
        temperature=0.2,
        max_completion_tokens=1800,
        timeout=60,
        max_retries=2,
    )
    structured_model = model.with_structured_output(
        AgentOutput,
        method="json_schema",
        strict=True,
    )
    chain = CONSULTATION_PROMPT | structured_model
    structured_output = chain.invoke(
        {
            "state_json": json.dumps(state, ensure_ascii=False),
            "recent_messages_json": json.dumps(
                recent_messages, ensure_ascii=False
            ),
            "rag_context": context_text,
            "question": question,
        }
    )
    if not isinstance(structured_output, AgentOutput):
        raise ValueError("O modelo não retornou uma resposta estruturada utilizável.")
    output = structured_output.model_dump()
    state = _merge_state(state, output, question, sources)
    state["estado_atual"] = determine_stage(
        state, bool(output.get("requires_human_validation"))
    )
    answer = _validate_answer(str(output["answer"]), state)

    append_message(session_id, "user", question)
    append_message(
        session_id,
        "assistant",
        answer,
        {
            "sources": sources,
            "stage": state["estado_atual"],
            "requires_human_validation": bool(
                output.get("requires_human_validation")
            ),
        },
    )
    save_state(session_id, state)

    return {
        "answer": answer,
        "sources": sources,
        "session_id": session_id,
        "stage": state["estado_atual"],
        "checkpoint": checkpoint_summary(state),
        "requires_human_validation": bool(
            output.get("requires_human_validation")
        ),
    }
