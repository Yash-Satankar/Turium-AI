"""Raw SQL access. Functions take an open connection so callers control transactions."""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

_ITEM_COLUMNS = """
    i.id, i.source_type, i.title, i.url, i.raw_content, i.status, i.error, i.created_at, i.updated_at,
    (SELECT COUNT(*) FROM chunks c WHERE c.item_id = i.id) AS chunk_count
"""


def utcnow() -> str:
    # Microsecond precision so created_at sorts items inserted in the same second.
    return datetime.now(UTC).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class ItemRow:
    id: str
    source_type: str
    title: str | None
    url: str | None
    raw_content: str | None
    status: str
    error: str | None
    created_at: str
    updated_at: str
    chunk_count: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ItemRow":
        return cls(**dict(row))


@dataclass(frozen=True)
class ChunkRow:
    item_id: str
    source_type: str
    title: str | None
    url: str | None
    text: str
    embedding: bytes


def insert_item(
    conn: sqlite3.Connection, *, item_id: str, source_type: str, title: str | None, url: str | None, raw_content: str | None
) -> None:
    now = utcnow()
    conn.execute(
        "INSERT INTO items (id, source_type, title, url, raw_content, status, error, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 'pending', NULL, ?, ?)",
        (item_id, source_type, title, url, raw_content, now, now),
    )


def get_item(conn: sqlite3.Connection, item_id: str) -> ItemRow | None:
    row = conn.execute(f"SELECT {_ITEM_COLUMNS} FROM items i WHERE i.id = ?", (item_id,)).fetchone()
    return ItemRow.from_row(row) if row else None


def list_items(conn: sqlite3.Connection, limit: int) -> list[ItemRow]:
    rows = conn.execute(
        f"SELECT {_ITEM_COLUMNS} FROM items i ORDER BY i.created_at DESC, i.rowid DESC LIMIT ?", (limit,)
    ).fetchall()
    return [ItemRow.from_row(r) for r in rows]


def claim_item(conn: sqlite3.Connection, item_id: str) -> bool:
    """pending -> processing. False if the item is gone or already claimed."""
    cur = conn.execute(
        "UPDATE items SET status = 'processing', updated_at = ? WHERE id = ? AND status = 'pending'",
        (utcnow(), item_id),
    )
    return cur.rowcount == 1


def mark_failed(conn: sqlite3.Connection, item_id: str, error: str) -> None:
    conn.execute(
        "UPDATE items SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
        (error, utcnow(), item_id),
    )


def complete_item(
    conn: sqlite3.Connection,
    *,
    item_id: str,
    title: str | None,
    raw_content: str,
    chunks: list[tuple[str, bytes]],
    embedding_model: str,
) -> None:
    """Writes all chunks and flips the item to ready. Call inside one transaction."""
    now = utcnow()
    conn.execute("DELETE FROM chunks WHERE item_id = ?", (item_id,))
    conn.executemany(
        "INSERT INTO chunks (item_id, chunk_index, text, embedding, embedding_model, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        [(item_id, i, text, blob, embedding_model, now) for i, (text, blob) in enumerate(chunks)],
    )
    conn.execute(
        "UPDATE items SET status = 'ready', error = NULL, title = ?, raw_content = ?, updated_at = ? WHERE id = ?",
        (title, raw_content, now, item_id),
    )


def fail_interrupted(conn: sqlite3.Connection, message: str) -> int:
    cur = conn.execute(
        "UPDATE items SET status = 'failed', error = ?, updated_at = ? WHERE status IN ('pending', 'processing')",
        (message, utcnow()),
    )
    return cur.rowcount


def load_searchable_chunks(conn: sqlite3.Connection, embedding_model: str) -> list[ChunkRow]:
    rows = conn.execute(
        "SELECT c.item_id, i.source_type, i.title, i.url, c.text, c.embedding "
        "FROM chunks c JOIN items i ON i.id = c.item_id "
        "WHERE i.status = 'ready' AND c.embedding_model = ?",
        (embedding_model,),
    ).fetchall()
    return [ChunkRow(**dict(r)) for r in rows]
