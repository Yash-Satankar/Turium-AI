from app.db import repositories as repo
from app.db.connection import connect


def list_items(db_path: str, limit: int) -> list[repo.ItemRow]:
    """Newest first."""
    with connect(db_path) as conn:
        return repo.list_items(conn, limit)
