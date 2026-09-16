from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.analytics import get_explanation, get_teaching_plan, update_feedback
from app.config import get_settings
from app.db import fetch_mcn_rows
from app.models import (
    ChatRequest,
    ChatResponse,
    ExplanationResponse,
    FeedbackRequest,
    FeedbackResponse,
    IndexResponse,
)
from app.neoprofessor import run_consultation
from app.rag import build_index
from app.exports import build_teaching_plan_docx, build_teaching_plan_pdf

app = FastAPI(title="Assistente de Inteligência Curricular")
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path("frontend")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def home() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/matriz")
def matrix_page() -> FileResponse:
    return FileResponse(static_dir / "matriz.html")


@app.get("/api/mcn")
def matrix_records() -> list[dict]:
    try:
        return fetch_mcn_rows(settings)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Não foi possível carregar a Matriz Curricular Nacional.",
        ) from exc


@app.post("/api/index", response_model=IndexResponse)
def index_database() -> IndexResponse:
    try:
        indexed = build_index(settings)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return IndexResponse(
        indexed_rows=indexed,
        message="Indexacao concluida com sucesso.",
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    try:
        result = run_consultation(body.question, settings, body.session_id)
    except FileNotFoundError as exc:
        try:
            build_index(settings)
        except Exception as index_exc:
            raise HTTPException(status_code=400, detail=str(index_exc)) from exc
        try:
            result = run_consultation(body.question, settings, body.session_id)
        except ValueError as consultation_exc:
            raise HTTPException(
                status_code=400, detail=str(consultation_exc)
            ) from consultation_exc
        except Exception as consultation_exc:
            raise HTTPException(
                status_code=500,
                detail="Não foi possível concluir a consulta neste momento.",
            ) from consultation_exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Não foi possível concluir a consulta neste momento.",
        ) from exc

    return ChatResponse(**result)


@app.post("/api/feedback", response_model=FeedbackResponse)
def feedback(body: FeedbackRequest) -> FeedbackResponse:
    try:
        update_feedback(
            settings.analytics_database_url,
            session_id=body.session_id,
            response_id=body.response_id,
            rating=body.rating,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Não foi possível registrar a avaliação neste momento.",
        ) from exc

    return FeedbackResponse(saved=True, rating=body.rating)


@app.get(
    "/api/explanations/{response_id}",
    response_model=ExplanationResponse,
)
def explanation(response_id: str, session_id: str) -> ExplanationResponse:
    try:
        stored = get_explanation(
            settings.analytics_database_url,
            session_id=session_id,
            response_id=response_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Não foi possível carregar a justificativa neste momento.",
        ) from exc

    return ExplanationResponse(**stored)


@app.get("/api/exports/{response_id}")
def export_teaching_plan(
    response_id: str,
    session_id: str,
    format: str = Query(pattern="^(docx|pdf)$"),
) -> StreamingResponse:
    try:
        plan = get_teaching_plan(
            settings.analytics_database_url,
            session_id=session_id,
            response_id=response_id,
        )
        if format == "docx":
            content = build_teaching_plan_docx(plan)
            media_type = (
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            )
        else:
            content = build_teaching_plan_pdf(plan)
            media_type = "application/pdf"
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Não foi possível exportar o plano neste momento.",
        ) from exc

    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="plano-de-ensino.{format}"'
            )
        },
    )
