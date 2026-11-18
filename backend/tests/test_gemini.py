import json

import httpx
import pytest

from app.providers import ProviderError, ProviderRateLimited, ProviderTimeout
from app.providers.gemini import GeminiEmbeddings, GeminiLLM, _GeminiClient


def make(handler):
    client = _GeminiClient("test-key", 5, transport=httpx.MockTransport(handler))
    return GeminiEmbeddings(client, "gemini-embedding-001", 8), GeminiLLM(client, "gemini-2.5-flash")


def test_embed_request_shape_and_batching():
    seen = []

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        seen.append((request.url.path, request.headers["x-goog-api-key"], body))
        return httpx.Response(200, json={"embeddings": [{"values": [0.1] * 8} for _ in body["requests"]]})

    emb, _ = make(handler)
    vectors = emb.embed_documents([f"t{i}" for i in range(150)])
    assert len(vectors) == 150
    assert [len(b["requests"]) for _, _, b in seen] == [100, 50]
    path, key, body = seen[0]
    assert path == "/v1beta/models/gemini-embedding-001:batchEmbedContents"
    assert key == "test-key"
    assert body["requests"][0]["taskType"] == "RETRIEVAL_DOCUMENT"
    assert body["requests"][0]["outputDimensionality"] == 8

    emb.embed_query("q")
    assert seen[-1][2]["requests"][0]["taskType"] == "RETRIEVAL_QUERY"
    assert emb.model_id == "gemini:gemini-embedding-001:8"


def test_generate_parses_text_and_skips_thoughts():
    def handler(request):
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "hmm", "thought": True}, {"text": "Answer [1]"}]}}]},
        )

    _, llm = make(handler)
    assert llm.generate("sys", "prompt") == "Answer [1]"


def test_generate_blocked():
    _, llm = make(lambda r: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(ProviderError, match="SAFETY"):
        llm.generate("sys", "prompt")


@pytest.mark.parametrize(
    ("response", "exc"),
    [
        (httpx.Response(429, json={"error": {"message": "quota"}}), ProviderRateLimited),
        (httpx.Response(400, json={"error": {"message": "API key not valid"}}), ProviderError),
        (httpx.Response(500, text="boom"), ProviderError),
    ],
)
def test_http_errors(response, exc):
    emb, _ = make(lambda r: response)
    with pytest.raises(exc):
        emb.embed_query("q")


def test_error_message_is_surfaced():
    emb, _ = make(lambda r: httpx.Response(400, json={"error": {"message": "API key not valid"}}))
    with pytest.raises(ProviderError, match="API key not valid"):
        emb.embed_query("q")


def test_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    emb, _ = make(handler)
    with pytest.raises(ProviderTimeout):
        emb.embed_query("q")
