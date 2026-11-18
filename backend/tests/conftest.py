from collections.abc import Callable, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.providers.fake import FakeEmbeddings, FakeLLM
from app.services.ingestion import IngestionDeps

PUBLIC_IP = "93.184.215.14"


def public_resolver(host: str, port: int) -> list[str]:
    return [PUBLIC_IP]


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        provider="fake",
        database_path=str(tmp_path / "test.db"),
        min_score=0.2,
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def make_client(settings: Settings) -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def _make(handler: Callable[[httpx.Request], httpx.Response] | None = None, **overrides) -> TestClient:
        embedder = overrides.pop("embedder", FakeEmbeddings())
        llm = overrides.pop("llm", FakeLLM())
        deps = IngestionDeps(
            settings=settings,
            embedder=embedder,
            resolver=overrides.pop("resolver", public_resolver),
            transport=httpx.MockTransport(handler) if handler else None,
        )
        app = create_app(settings, embedder=embedder, llm=llm, ingestion_deps=deps)
        client = TestClient(app, raise_server_exceptions=False)
        client.__enter__()  # run lifespan
        clients.append(client)
        return client

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()
