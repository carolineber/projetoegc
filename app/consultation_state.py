from __future__ import annotations

import json
import os
import re
import sqlite3
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

SESSION_ID_PATTERN = re.compile(r"^[a-f0-9-]{36}$")
STATE_DB_PATH = (
    Path("/tmp/neoprofessor_state.db")
    if os.getenv("VERCEL") == "1"
    else Path("data/neoprofessor_state.db")
)

DEFAULT_STATE: dict = {
    "estado_atual": "DIAGNOSTICO",
    "objetivo": "",
    "campos_confirmados": {},
    "informacoes_confirmadas": [],
    "evidencias_documentais": [],
    "interpretacoes_do_agente": [],
    "recomendacoes_do_agente": [],
    "decisoes_humanas": [],
    "lacunas": [],
    "contradicoes": [],
    "riscos": [],
    "itens_que_exigem_validacao": [],
    "proximo_passo": "",
    "ultima_confirmacao_humana": None,
    "plano_ensino": {},
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _connect() -> sqlite3.Connection:
    STATE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(STATE_DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS consultation_sessions (
            id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS consultation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES consultation_sessions(id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_consultation_messages_session
        ON consultation_messages(session_id, id)
        """
    )
    connection.commit()
    return connection


def _normalize_state(raw_state: dict | None) -> dict:
    state = deepcopy(DEFAULT_STATE)
    if not isinstance(raw_state, dict):
        return state
    for key, default_value in DEFAULT_STATE.items():
        value = raw_state.get(key)
        if isinstance(default_value, list) and isinstance(value, list):
            state[key] = value
        elif isinstance(default_value, dict) and isinstance(value, dict):
            state[key] = value
        elif value is not None or default_value is None:
            state[key] = value
    return state


def load_or_create_session(requested_session_id: str | None) -> tuple[str, dict]:
    session_id = (
        requested_session_id
        if requested_session_id and SESSION_ID_PATTERN.fullmatch(requested_session_id)
        else str(uuid4())
    )
    with _connect() as connection:
        row = connection.execute(
            "SELECT state_json FROM consultation_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row:
            return session_id, _normalize_state(json.loads(row["state_json"]))

        timestamp = _now()
        state = deepcopy(DEFAULT_STATE)
        connection.execute(
            """
            INSERT INTO consultation_sessions (id, state_json, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, json.dumps(state, ensure_ascii=False), timestamp, timestamp),
        )
        connection.commit()
        return session_id, state


def save_state(session_id: str, state: dict) -> None:
    normalized_state = _normalize_state(state)
    with _connect() as connection:
        connection.execute(
            """
            UPDATE consultation_sessions
            SET state_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (json.dumps(normalized_state, ensure_ascii=False), _now(), session_id),
        )
        connection.commit()


def append_message(
    session_id: str,
    role: str,
    content: str,
    metadata: dict | None = None,
) -> None:
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO consultation_messages
                (session_id, role, content, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                role,
                content,
                json.dumps(metadata or {}, ensure_ascii=False),
                _now(),
            ),
        )
        connection.commit()


def get_recent_messages(session_id: str, limit: int = 10) -> list[dict[str, str]]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT role, content
            FROM consultation_messages
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    return [
        {"role": row["role"], "content": row["content"]}
        for row in reversed(rows)
    ]


def checkpoint_summary(state: dict) -> str:
    confirmed_count = len(state.get("informacoes_confirmadas", []))
    pending_count = len(state.get("lacunas", [])) + len(
        state.get("itens_que_exigem_validacao", [])
    )
    return (
        f"{confirmed_count} informação(ões) confirmada(s) · "
        f"{pending_count} pendência(s)"
    )
