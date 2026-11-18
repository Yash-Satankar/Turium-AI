from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from app.db.repositories import ItemRow
from app.services.url_safety import UnsafeUrlError, check_url
from app.text_utils import truncate

NOTE_MAX_CHARS = 20_000
PREVIEW_CHARS = 200


class NoteIngest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["note"]
    content: str = Field(max_length=NOTE_MAX_CHARS)

    @field_validator("content")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise PydanticCustomError("empty_note", "Note cannot be empty")
        return v


class UrlIngest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["url"]
    url: str = Field(max_length=2048)

    @field_validator("url")
    @classmethod
    def _safe_url(cls, v: str) -> str:
        try:
            return check_url(v)
        except UnsafeUrlError as exc:
            raise PydanticCustomError("url_not_allowed", str(exc)) from exc


IngestRequest = Annotated[NoteIngest | UrlIngest, Field(discriminator="source_type")]


class ItemOut(BaseModel):
    id: str
    source_type: Literal["note", "url"]
    title: str | None
    url: str | None
    preview: str | None
    status: Literal["pending", "processing", "ready", "failed"]
    error: str | None
    chunk_count: int
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: ItemRow) -> "ItemOut":
        preview = truncate(" ".join(row.raw_content.split()), PREVIEW_CHARS) if row.raw_content else None
        return cls(
            id=row.id,
            source_type=row.source_type,  # type: ignore[arg-type]
            title=row.title,
            url=row.url,
            preview=preview,
            status=row.status,  # type: ignore[arg-type]
            error=row.error,
            chunk_count=row.chunk_count,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class ItemList(BaseModel):
    items: list[ItemOut]


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)

    @field_validator("question")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise PydanticCustomError("empty_question", "Question cannot be empty")
        return v


class SourceOut(BaseModel):
    index: int
    item_id: str
    source_type: Literal["note", "url"]
    title: str | None
    url: str | None
    snippet: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    found: bool
    sources: list[SourceOut]


class Health(BaseModel):
    status: Literal["ok"] = "ok"
