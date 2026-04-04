from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.models import ChatRequest, ChatResponse, IndexResponse
from app.rag import answer_question, build_index

app = FastAPI(title="Chatbot RAG com OpenAI + Banco")
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
        answer, sources = answer_question(body.question, settings)
    except FileNotFoundError as exc:
        try:
            build_index(settings)
            answer, sources = answer_question(body.question, settings)
        except Exception as index_exc:
            raise HTTPException(status_code=400, detail=str(index_exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ChatResponse(answer=answer, sources=sources)
