from __future__ import annotations

import sqlite3
from pathlib import Path

from openpyxl import load_workbook

XLSX_PATH = Path("espens_clean.xlsx")
SQLITE_PATH = Path("data/local.db")
TABLE_NAME = "rag_docs"


def _read_rows(xlsx_path: Path) -> list[dict[str, str]]:
    workbook = load_workbook(xlsx_path, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        all_rows = list(sheet.iter_rows(values_only=True))
        if not all_rows:
            return []

        header_row = all_rows[0]
        headers = [
            str(value).strip() if value is not None else "" for value in header_row
        ]
        headers = [
            header if header else f"coluna_{idx + 1}"
            for idx, header in enumerate(headers)
        ]

        parsed_rows: list[dict[str, str]] = []
        for row in all_rows[1:]:
            row_dict: dict[str, str] = {}
            for idx, cell_value in enumerate(row):
                column_name = headers[idx]
                if not column_name:
                    continue
                row_dict[column_name] = (
                    "" if cell_value is None else str(cell_value).strip()
                )
            if any(row_dict.values()):
                parsed_rows.append(row_dict)
        return parsed_rows
    finally:
        workbook.close()


def _pick_column(columns: list[str], candidates: list[str], default: str) -> str:
    lowered = {col.lower(): col for col in columns}
    for cand in candidates:
        if cand in lowered:
            return lowered[cand]
    for col in columns:
        col_low = col.lower()
        if any(cand in col_low for cand in candidates):
            return col
    return default


def main() -> None:
    if not XLSX_PATH.exists():
        raise FileNotFoundError(f"Arquivo XLSX nao encontrado: {XLSX_PATH}")

    rows = _read_rows(XLSX_PATH)
    if not rows:
        raise ValueError("XLSX sem linhas de dados.")

    columns = list(rows[0].keys())
    title_col = _pick_column(columns, ["tipo", "titulo"], columns[0])
    cadastro_col = _pick_column(columns, ["cadastro", "codigo"], columns[1])

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(SQLITE_PATH)

    try:
        cursor = connection.cursor()
        cursor.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
        cursor.execute(
            f"""
            CREATE TABLE {TABLE_NAME} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_row INTEGER NOT NULL,
                titulo TEXT,
                cadastro TEXT,
                conteudo TEXT NOT NULL
            )
            """
        )

        for idx, row in enumerate(rows, start=1):
            titulo = row.get(title_col, "")
            cadastro = row.get(cadastro_col, "")
            conteudo = "\n".join(
                [f"{col}: {value}" for col, value in row.items() if value]
            )
            cursor.execute(
                f"""
                INSERT INTO {TABLE_NAME} (source_row, titulo, cadastro, conteudo)
                VALUES (?, ?, ?, ?)
                """,
                (idx, titulo, cadastro, conteudo),
            )

        connection.commit()
        print(
            f"SQLite criado em {SQLITE_PATH} com {len(rows)} linhas a partir de {XLSX_PATH}."
        )
    finally:
        connection.close()


if __name__ == "__main__":
    main()
