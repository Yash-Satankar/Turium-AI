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
from app.services import ingestion, items
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
        item = ingestion.create_item(
            db_path, source_type="note", title=ingestion.note_title(body.content), url=None, raw_content=body.content
        )
    else:
        item = ingestion.create_item(db_path, source_type="url", title=None, url=body.url, raw_content=None)
    background.add_task(ingestion.process_item, item.id, state.ingestion_deps)
    return ItemOut.from_row(item)


@router.get("/items", response_model=ItemList)
def list_items(request: Request, limit: Annotated[int, Query(ge=1, le=200)] = 50) -> ItemList:
    rows = items.list_items(request.app.state.settings.database_path, limit)
    return ItemList(items=[ItemOut.from_row(r) for r in rows])


@router.post("/query", response_model=QueryResponse)
def query(body: QueryRequest, request: Request) -> QueryResponse:
    state = request.app.state
    result = answer_question(body.question, body.top_k, settings=state.settings, embedder=state.embedder, llm=state.llm)
    return QueryResponse(
        answer=result.answer,
        found=result.found,
        sources=[SourceOut.model_validate(s, from_attributes=True) for s in result.sources],
    )
