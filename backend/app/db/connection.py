import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id          TEXT PRIMARY KEY,
    source_type TEXT NOT NULL CHECK (source_type IN ('note', 'url')),
    title       TEXT,
    url         TEXT,
    raw_content TEXT,
    status      TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'ready', 'failed')),
    error       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_created_at ON items (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_status ON items (status);

CREATE TABLE IF NOT EXISTS chunks (
    id              INTEGER PRIMARY KEY,
    item_id         TEXT NOT NULL REFERENCES items (id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    text            TEXT NOT NULL,
    embedding       BLOB NOT NULL,
    embedding_model TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    UNIQUE (item_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_chunks_model ON chunks (embedding_model);
"""


def init_db(path: str) -> None:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")  # persistent; readers don't block the writer
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def connect(path: str) -> Iterator[sqlite3.Connection]:
    """One short-lived connection per unit of work; commits on success, rolls back on error.

    Request handlers and background jobs run on different threads, and sqlite3
    connections must not be shared across threads, so we never pool them.
    """
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
