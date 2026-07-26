from __future__ import annotations

import json

from sqlalchemy import create_engine, inspect, text

from app.config import Settings


def fetch_rows(settings: Settings) -> list[dict]:
    if not settings.database_url:
        raise ValueError("DATABASE_URL nao configurada.")
    if not settings.target_table:
        raise ValueError("TARGET_TABLE nao configurada.")
    if not settings.target_text_columns:
        raise ValueError("TARGET_TEXT_COLUMNS nao configurada.")

    engine = create_engine(settings.database_url)
    table_columns = {
        column["name"] for column in inspect(engine).get_columns(settings.target_table)
    }
    columns = [settings.target_id_column] + settings.target_text_columns
    for metadata_column in ("source_name", "source_type"):
        if metadata_column in table_columns and metadata_column not in columns:
            columns.append(metadata_column)
    quoted_columns = ", ".join([f'"{col}"' for col in columns])
    query = text(
        f'SELECT {quoted_columns} FROM "{settings.target_table}" LIMIT :max_rows'
    )

    with engine.connect() as connection:
        result = connection.execute(query, {"max_rows": settings.max_rows})
        return [dict(row._mapping) for row in result]


def fetch_mcn_rows(settings: Settings) -> list[dict]:
    engine = create_engine(settings.database_url)
    query = text(
        f"""
        SELECT id, source_row, cadastro, metadata_json
        FROM "{settings.target_table}"
        WHERE source_type = :source_type
        ORDER BY source_row
        LIMIT :max_rows
        """
    )
    with engine.connect() as connection:
        result = connection.execute(
            query,
            {
                "source_type": "Matriz Curricular Nacional 2026",
                "max_rows": settings.max_rows,
            },
        )
        records: list[dict] = []
        for row in result:
            metadata = json.loads(row.metadata_json)
            records.append(
                {
                    "id": row.id,
                    "source_row": row.source_row,
                    "cadastro": row.cadastro,
                    **metadata,
                }
            )
        return records
