"""Exact (brute-force) cosine similarity over every searchable chunk.

Fine for thousands of chunks; see README for the ANN index this would become at scale.
"""

from dataclasses import dataclass

import numpy as np

from app.db import repositories as repo
from app.db.connection import connect


@dataclass(frozen=True)
class RetrievedChunk:
    item_id: str
    source_type: str
    title: str | None
    url: str | None
    text: str
    score: float


def retrieve(db_path: str, query_vector: list[float], embedding_model: str, top_k: int) -> list[RetrievedChunk]:
    with connect(db_path) as conn:
        rows = repo.load_searchable_chunks(conn, embedding_model)

    q = np.asarray(query_vector, dtype=np.float32)
    rows = [r for r in rows if len(r.embedding) == q.size * 4]  # guard against a changed dimension
    if not rows or not np.any(q):
        return []

    matrix = np.frombuffer(b"".join(r.embedding for r in rows), dtype=np.float32).reshape(len(rows), q.size)
    denom = np.linalg.norm(matrix, axis=1) * np.linalg.norm(q)
    scores = (matrix @ q) / np.maximum(denom, 1e-12)

    k = min(top_k, len(rows))
    top = np.argpartition(-scores, k - 1)[:k]
    top = top[np.argsort(-scores[top])]
    return [
        RetrievedChunk(
            item_id=rows[i].item_id,
            source_type=rows[i].source_type,
            title=rows[i].title,
            url=rows[i].url,
            text=rows[i].text,
            score=float(scores[i]),
        )
        for i in top
    ]
