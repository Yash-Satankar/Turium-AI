"""Thin handlers: parse -> call a service -> shape the response.

Handlers are sync `def`, so FastAPI runs them in its threadpool and blocking
SQLite/provider calls never stall the event loop.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, Request

from app.api.schemas import (
    Health,
    IngestRequest,
    ItemList,
    ItemOut,
    NoteIngest,
    QueryRequest,
    QueryResponse,
    SourceOut,
)
from app.db import repositories as repo
from app.db.connection import connect
from app.services import ingestion
from app.services.rag import answer_question

router = APIRouter()


@router.get("/health", response_model=Health)
def health() -> Health:
    return Health()


@router.post("/ingest", status_code=202, response_model=ItemOut)
def ingest(body: IngestRequest, request: Request, background: BackgroundTasks) -> ItemOut:
    state = request.app.state
    db_path = state.settings.database_path
    if isinstance(body, NoteIngest):
        item = ingestion.create_note(db_path, body.content)
    else:
        item = ingestion.create_url(db_path, body.url)
    background.add_task(ingestion.process_item, item.id, state.ingestion_deps)
    return ItemOut.from_row(item)


@router.get("/items", response_model=ItemList)
def list_items(request: Request, limit: Annotated[int, Query(ge=1, le=200)] = 50) -> ItemList:
    with connect(request.app.state.settings.database_path) as conn:
        rows = repo.list_items(conn, limit)
    return ItemList(items=[ItemOut.from_row(r) for r in rows])


@router.post("/query", response_model=QueryResponse)
def query(body: QueryRequest, request: Request) -> QueryResponse:
    state = request.app.state
    result = answer_question(body.question, body.top_k, settings=state.settings, embedder=state.embedder, llm=state.llm)
    limit = state.settings.snippet_chars
    return QueryResponse(
        answer=result.answer,
        found=result.found,
        sources=[
            SourceOut(
                index=i,
                item_id=c.item_id,
                source_type=c.source_type,  # type: ignore[arg-type]
                title=c.title,
                url=c.url,
                snippet=c.text if len(c.text) <= limit else c.text[: limit - 1].rstrip() + "…",
                score=round(c.score, 4),
            )
            for i, c in enumerate(result.sources, start=1)
        ],
    )
