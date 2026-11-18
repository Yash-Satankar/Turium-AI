import logging
import time
import uuid
from dataclasses import dataclass

import numpy as np

from app.config import Settings
from app.db import repositories as repo
from app.db.connection import connect
from app.providers import EmbeddingProvider, ProviderError
from app.services.chunker import chunk_text
from app.services.errors import IngestError
from app.services.extractor import extract_page
from app.services.fetcher import Resolver, fetch_page, system_resolver
from app.text_utils import truncate

logger = logging.getLogger(__name__)

INTERRUPTED_MESSAGE = "Interrupted by server restart"
NOTE_TITLE_MAX = 80


def note_title(content: str) -> str:
    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    return truncate(first_line, NOTE_TITLE_MAX)


def create_item(
    db_path: str, *, source_type: str, title: str | None, url: str | None, raw_content: str | None
) -> repo.ItemRow:
    """Inserts a pending item; the caller schedules process_item for it."""
    item_id = str(uuid.uuid4())
    with connect(db_path) as conn:
        repo.insert_item(
            conn, item_id=item_id, source_type=source_type, title=title, url=url, raw_content=raw_content
        )
        item = repo.get_item(conn, item_id)
    if item is None:
        raise RuntimeError(f"item {item_id} missing right after insert")
    logger.info("item created", extra={"item_id": item_id, "source_type": source_type, "status": "pending"})
    return item


@dataclass
class IngestionDeps:
    settings: Settings
    embedder: EmbeddingProvider
    resolver: Resolver = system_resolver
    transport: object | None = None  # httpx transport override, for tests


def process_item(item_id: str, deps: IngestionDeps) -> None:
    """Background job: pending -> processing -> ready | failed. Never raises."""
    settings = deps.settings
    start = time.perf_counter()

    with connect(settings.database_path) as conn:
        if not repo.claim_item(conn, item_id):
            logger.warning("item not claimable, skipping", extra={"item_id": item_id})
            return
        item = repo.get_item(conn, item_id)
    assert item is not None
    logger.info("item status", extra={"item_id": item_id, "status": "processing"})

    try:
        if item.source_type == "url":
            assert item.url
            page = fetch_page(
                item.url,
                timeout_s=settings.fetch_timeout_s,
                max_bytes=settings.fetch_max_bytes,
                max_redirects=settings.fetch_max_redirects,
                resolver=deps.resolver,
                transport=deps.transport,  # type: ignore[arg-type]
                user_agent=settings.fetch_user_agent,
            )
            extracted = extract_page(page.html, page.url)
            title, text = extracted.title, extracted.text
            logger.info("page extracted", extra={"item_id": item_id, "chars": len(text), "final_url": page.url})
        else:
            title, text = item.title, item.raw_content or ""

        chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
        if not chunks:
            raise IngestError("Nothing to index: the content is empty")

        vectors = deps.embedder.embed_documents(chunks)
        if len(vectors) != len(chunks):
            raise ProviderError("Embedding provider returned the wrong number of vectors")
        blobs = [np.asarray(v, dtype=np.float32).tobytes() for v in vectors]

        with connect(settings.database_path) as conn:
            repo.complete_item(
                conn,
                item_id=item_id,
                title=title,
                raw_content=text,
                chunks=list(zip(chunks, blobs, strict=True)),
                embedding_model=deps.embedder.model_id,
            )
        logger.info(
            "item status",
            extra={"item_id": item_id, "status": "ready", "chunks": len(chunks), "duration_ms": _ms(start)},
        )
    except IngestError as exc:
        _fail(settings.database_path, item_id, str(exc), start)
    except ProviderError as exc:
        _fail(settings.database_path, item_id, f"Embedding failed: {exc.message}", start)
    except Exception:
        logger.exception("unexpected ingestion error", extra={"item_id": item_id})
        _fail(settings.database_path, item_id, "Unexpected error while processing this item", start)


def _fail(db_path: str, item_id: str, message: str, start: float) -> None:
    with connect(db_path) as conn:
        repo.mark_failed(conn, item_id, message)
    logger.info("item status", extra={"item_id": item_id, "status": "failed", "error": message, "duration_ms": _ms(start)})


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def fail_interrupted_items(db_path: str) -> int:
    with connect(db_path) as conn:
        return repo.fail_interrupted(conn, INTERRUPTED_MESSAGE)
