import httpx
import pytest

from app.db import repositories as repo
from app.db.connection import connect, init_db
from app.providers import ProviderRateLimited, ProviderTimeout
from app.providers.fake import FakeEmbeddings
from app.services.rag import NOT_FOUND_ANSWER

from .test_fetcher import ARTICLE


def assert_error(resp, status, code):
    assert resp.status_code == status, resp.text
    body = resp.json()["error"]
    assert body["code"] == code
    assert body["message"]
    assert body["request_id"] == resp.headers["X-Request-ID"]
    return body


def ingest_note(client, content):
    resp = client.post("/ingest", json={"source_type": "note", "content": content})
    assert resp.status_code == 202, resp.text
    return resp.json()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert resp.headers["X-Request-ID"]


def test_request_id_is_propagated(client):
    assert client.get("/health", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"] == "abc-123"


def test_note_ingest_becomes_ready(client):
    item = ingest_note(client, "Groceries\nBuy oat milk and coffee beans on Friday.")
    assert item["status"] == "pending"
    assert item["title"] == "Groceries"
    assert item["chunk_count"] == 0

    # TestClient runs background tasks before returning, so the job has finished.
    items = client.get("/items").json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "ready"
    assert items[0]["chunk_count"] == 1
    assert items[0]["preview"].startswith("Groceries Buy oat milk")


def test_long_note_title_is_truncated(client):
    item = ingest_note(client, "x" * 200)
    assert len(item["title"]) == 80


@pytest.mark.parametrize(
    "payload",
    [
        {"source_type": "note", "content": "   \n "},
        {"source_type": "note", "content": "a" * 20_001},
        {"source_type": "note"},
        {"source_type": "url", "url": "file:///etc/passwd"},
        {"source_type": "url", "url": "http://127.0.0.1:8000/admin"},
        {"source_type": "url", "url": "http://localhost/"},
        {"source_type": "url", "url": "nonsense"},
        {"source_type": "video", "url": "https://example.com"},
        {"source_type": "note", "content": "hi", "url": "https://example.com"},
        {"content": "missing type"},
    ],
)
def test_ingest_validation(client, payload):
    body = assert_error(client.post("/ingest", json=payload), 422, "VALIDATION_ERROR")
    assert body["details"]
    assert client.get("/items").json()["items"] == []


def test_validation_message_is_readable(client):
    body = assert_error(client.post("/ingest", json={"source_type": "note", "content": " "}), 422, "VALIDATION_ERROR")
    assert body["message"] == "content: Note cannot be empty"


def test_url_ingest_success(make_client):
    client = make_client(lambda r: httpx.Response(200, html=ARTICLE))
    resp = client.post("/ingest", json={"source_type": "url", "url": "https://example.com/bread"})
    assert resp.status_code == 202
    assert resp.json()["title"] is None

    item = client.get("/items").json()["items"][0]
    assert item["status"] == "ready", item
    assert item["title"] == "Sourdough Guide"
    assert item["url"] == "https://example.com/bread"
    assert "starter" in item["preview"]

    answer = client.post("/query", json={"question": "How often should I feed the sourdough starter?"}).json()
    assert answer["found"] is True
    assert answer["sources"][0]["url"] == "https://example.com/bread"


def test_url_ingest_failure_is_reported_on_item(make_client):
    client = make_client(lambda r: httpx.Response(503, text="down"))
    client.post("/ingest", json={"source_type": "url", "url": "https://example.com/x"})
    item = client.get("/items").json()["items"][0]
    assert item["status"] == "failed"
    assert item["error"] == "Page returned HTTP 503"
    assert item["chunk_count"] == 0


def test_url_resolving_to_private_ip_fails_async(make_client):
    client = make_client(lambda r: httpx.Response(200, html=ARTICLE), resolver=lambda h, p: ["192.168.0.10"])
    assert client.post("/ingest", json={"source_type": "url", "url": "https://internal.example.com/"}).status_code == 202
    item = client.get("/items").json()["items"][0]
    assert item["status"] == "failed"
    assert "private" in item["error"]


def test_embedding_failure_marks_item_failed(make_client):
    class Broken(FakeEmbeddings):
        def embed_documents(self, texts):
            raise ProviderRateLimited("Gemini rate limit reached; try again shortly")

    client = make_client(embedder=Broken())
    ingest_note(client, "some note")
    item = client.get("/items").json()["items"][0]
    assert item["status"] == "failed"
    assert item["error"].startswith("Embedding failed: Gemini rate limit")


def test_items_newest_first_and_limit(client):
    for i in range(3):
        ingest_note(client, f"note {i}")
    items = client.get("/items?limit=2").json()["items"]
    assert [i["title"] for i in items] == ["note 2", "note 1"]


@pytest.mark.parametrize("limit", ["0", "201", "abc"])
def test_items_limit_validation(client, limit):
    assert_error(client.get(f"/items?limit={limit}"), 422, "VALIDATION_ERROR")


def test_query_found_with_citations(client):
    ingest_note(client, "The office wifi password is maple-syrup-42. Guests use the separate network.")
    ingest_note(client, "Dentist appointment is on March 3rd at 4pm with Dr. Patel.")
    resp = client.post("/query", json={"question": "What is the office wifi password?", "top_k": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True
    assert "maple-syrup-42" in body["answer"] and "[1]" in body["answer"]
    assert [s["index"] for s in body["sources"]] == [1, 2]
    top = body["sources"][0]
    assert top["source_type"] == "note"
    assert "wifi password" in top["snippet"]
    assert top["score"] >= body["sources"][1]["score"]


def test_query_not_found_skips_llm(make_client):
    from app.providers.fake import FakeLLM

    llm = FakeLLM()
    client = make_client(llm=llm)
    ingest_note(client, "Dentist appointment is on March 3rd at 4pm.")
    body = client.post("/query", json={"question": "quantum chromodynamics lattice gauge"}).json()
    assert body == {"answer": NOT_FOUND_ANSWER, "found": False, "sources": []}
    assert llm.calls == []


def test_query_with_empty_inbox(client):
    body = client.post("/query", json={"question": "anything?"}).json()
    assert body["found"] is False


def test_failed_items_are_not_searched(make_client):
    client = make_client(lambda r: httpx.Response(500))
    client.post("/ingest", json={"source_type": "url", "url": "https://example.com/x"})
    assert client.post("/query", json={"question": "example"}).json()["found"] is False


def test_other_embedding_model_is_not_searched(client, settings):
    ingest_note(client, "The office wifi password is maple-syrup-42.")
    with connect(settings.database_path) as conn:
        conn.execute("UPDATE chunks SET embedding_model = 'old-model'")
    assert client.post("/query", json={"question": "office wifi password"}).json()["found"] is False


@pytest.mark.parametrize(
    "payload", [{"question": ""}, {"question": "  "}, {"question": "q", "top_k": 0}, {"question": "q", "top_k": 11}, {}]
)
def test_query_validation(client, payload):
    assert_error(client.post("/query", json=payload), 422, "VALIDATION_ERROR")


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (ProviderRateLimited("slow down"), 503, "PROVIDER_RATE_LIMITED"),
        (ProviderTimeout("timed out"), 504, "PROVIDER_TIMEOUT"),
    ],
)
def test_query_provider_errors(make_client, exc, status, code):
    class Failing(FakeEmbeddings):
        def embed_query(self, text):
            raise exc

    client = make_client(embedder=Failing())
    assert_error(client.post("/query", json={"question": "hello"}), status, code)


def test_unexpected_error_is_500_without_leaking(make_client):
    class Exploding(FakeEmbeddings):
        def embed_query(self, text):
            raise RuntimeError("secret internal detail")

    client = make_client(embedder=Exploding())
    body = assert_error(client.post("/query", json={"question": "hello"}), 500, "INTERNAL_ERROR")
    assert "secret" not in body["message"]


def test_404_and_405(client):
    assert_error(client.get("/nope"), 404, "NOT_FOUND")
    assert_error(client.get("/ingest"), 405, "METHOD_NOT_ALLOWED")


def test_invalid_json(client):
    resp = client.post("/ingest", content=b"{not json", headers={"Content-Type": "application/json"})
    assert_error(resp, 422, "VALIDATION_ERROR")


def test_startup_fails_interrupted_items(make_client, settings):
    init_db(settings.database_path)
    with connect(settings.database_path) as conn:
        repo.insert_item(conn, item_id="stuck-1", source_type="note", title="t", url=None, raw_content="body")
        repo.insert_item(conn, item_id="stuck-2", source_type="url", title=None, url="https://example.com", raw_content=None)
        repo.claim_item(conn, "stuck-2")

    client = make_client()
    items = {i["id"]: i for i in client.get("/items").json()["items"]}
    for item_id in ("stuck-1", "stuck-2"):
        assert items[item_id]["status"] == "failed"
        assert items[item_id]["error"] == "Interrupted by server restart"
