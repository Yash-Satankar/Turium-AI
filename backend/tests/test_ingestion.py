from app.config import Settings
from app.db import repositories as repo
from app.db.connection import connect, init_db
from app.providers.fake import FakeEmbeddings
from app.services.ingestion import IngestionDeps, process_item


def _deps(settings: Settings) -> IngestionDeps:
    return IngestionDeps(settings=settings, embedder=FakeEmbeddings())


def test_unknown_item_is_skipped(settings):
    init_db(settings.database_path)
    process_item("does-not-exist", _deps(settings))  # must not raise


def test_storage_failure_never_raises(tmp_path):
    broken = Settings(provider="fake", database_path=str(tmp_path / "missing-dir" / "x.db"), _env_file=None)  # type: ignore[call-arg]
    process_item("any-id", _deps(broken))  # connect fails on claim and on _fail; both are logged


def test_url_item_without_url_fails_cleanly(settings):
    init_db(settings.database_path)
    with connect(settings.database_path) as conn:
        repo.insert_item(conn, item_id="u1", source_type="url", title=None, url=None, raw_content=None)
    process_item("u1", _deps(settings))
    with connect(settings.database_path) as conn:
        item = repo.get_item(conn, "u1")
    assert item is not None
    assert item.status == "failed"
    assert item.error == "URL item has no URL to fetch"
