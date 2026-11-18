import json

import httpx
import pytest

from app.providers import ProviderError, ProviderRateLimited, ProviderTimeout, ProviderUnavailable
from app.providers.gemini import GeminiEmbeddings, GeminiLLM, _GeminiClient

GENERATE_OK = {"candidates": [{"content": {"parts": [{"text": "Answer [1]"}]}}]}


def embed_ok(request: httpx.Request) -> httpx.Response:
    n = len(json.loads(request.content)["requests"])
    return httpx.Response(200, json={"embeddings": [{"values": [0.1] * 8} for _ in range(n)]})


def rate_limited(retry_delay: str | None = None, headers: dict | None = None) -> httpx.Response:
    details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay}] if retry_delay else []
    return httpx.Response(
        429, json={"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED", "details": details}}, headers=headers
    )


def overloaded() -> httpx.Response:
    return httpx.Response(503, json={"error": {"code": 503, "message": "The model is overloaded.", "status": "UNAVAILABLE"}})


class Script:
    """Mock transport that replays responses in order and records request paths."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.paths: list[str] = []
        self.bodies: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        self.bodies.append(json.loads(request.content))
        if not self.responses:
            raise AssertionError(f"unexpected extra request to {request.url.path}")
        nxt = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return nxt(request) if callable(nxt) else nxt


def make(handler, *, batch_size=20, fallback=None):
    sleeps: list[float] = []
    client = _GeminiClient("test-key", 5, transport=httpx.MockTransport(handler), sleep=sleeps.append)
    emb = GeminiEmbeddings(client, "gemini-embedding-001", 8, batch_size=batch_size)
    llm = GeminiLLM(client, "primary-model", fallback_model=fallback)
    return emb, llm, sleeps


# --- request shape -----------------------------------------------------------


def test_embed_request_shape():
    script = Script(embed_ok)
    emb, _, _ = make(script)
    emb.embed_documents(["a", "b"])
    emb.embed_query("q")
    assert script.paths[0] == "/v1beta/models/gemini-embedding-001:batchEmbedContents"
    first = script.bodies[0]["requests"][0]
    assert first["taskType"] == "RETRIEVAL_DOCUMENT"
    assert first["outputDimensionality"] == 8
    assert script.bodies[1]["requests"][0]["taskType"] == "RETRIEVAL_QUERY"
    assert emb.model_id == "gemini:gemini-embedding-001:8"


def test_batches_split_at_batch_size():
    script = Script(embed_ok)
    emb, _, _ = make(script, batch_size=20)
    assert len(emb.embed_documents([f"t{i}" for i in range(45)])) == 45
    assert [len(b["requests"]) for b in script.bodies] == [20, 20, 5]


def test_batch_size_bounds():
    client = _GeminiClient("k", 5)
    for bad in (0, 101):
        with pytest.raises(ValueError):
            GeminiEmbeddings(client, "m", 8, batch_size=bad)


def test_generate_parses_text_and_skips_thoughts():
    _, llm, _ = make(
        lambda r: httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "hmm", "thought": True}, {"text": "Answer [1]"}]}}]}
        )
    )
    assert llm.generate("sys", "prompt") == "Answer [1]"


def test_generate_blocked():
    _, llm, _ = make(lambda r: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(ProviderError, match="SAFETY"):
        llm.generate("sys", "prompt")


# --- retries -----------------------------------------------------------------


def test_429_then_200_sleeps_server_retry_delay():
    script = Script(rate_limited("17s"), embed_ok)
    emb, _, sleeps = make(script)
    assert len(emb.embed_documents(["a"])) == 1
    assert sleeps == [17.0]
    assert len(script.paths) == 2


def test_retry_after_header_used_when_no_retry_delay():
    emb, _, sleeps = make(Script(rate_limited(headers={"Retry-After": "3"}), embed_ok))
    emb.embed_documents(["a"])
    assert sleeps == [3.0]


def test_503_then_200_succeeds():
    script = Script(overloaded(), httpx.Response(200, json=GENERATE_OK))
    _, llm, sleeps = make(script)
    assert llm.generate("sys", "prompt") == "Answer [1]"
    assert sleeps == [2.0]  # no server delay -> first backoff step


def test_embed_429_x4_raises_rate_limited_after_backoff():
    script = Script(rate_limited(), rate_limited(), rate_limited(), rate_limited())
    emb, _, sleeps = make(script)
    with pytest.raises(ProviderRateLimited):
        emb.embed_documents(["a"])
    assert len(script.paths) == 4  # 1 try + 3 retries
    assert sleeps == [2.0, 4.0, 8.0]


def test_generate_503_x2_raises_unavailable_after_one_retry():
    script = Script(overloaded(), overloaded())
    _, llm, sleeps = make(script)
    with pytest.raises(ProviderUnavailable) as exc_info:
        llm.generate("sys", "prompt")
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "PROVIDER_UNAVAILABLE"
    assert len(script.paths) == 2
    assert len(sleeps) == 1


def test_retry_delay_is_capped_at_max_wait():
    emb, llm, sleeps = make(Script(rate_limited("120s"), embed_ok))
    emb.embed_documents(["a"])  # background budget: cap 30s
    assert sleeps == [30.0]

    sleeps.clear()
    _, llm, sleeps = make(Script(rate_limited("120s"), httpx.Response(200, json=GENERATE_OK)))
    llm.generate("sys", "prompt")  # interactive budget: cap 5s
    assert sleeps == [5.0]


def test_query_embedding_uses_interactive_budget():
    script = Script(rate_limited(), rate_limited(), rate_limited())
    emb, _, sleeps = make(script)
    with pytest.raises(ProviderRateLimited):
        emb.embed_query("q")
    assert len(script.paths) == 2
    assert sleeps == [2.0]


def test_400_is_not_retried():
    script = Script(httpx.Response(400, json={"error": {"message": "API key not valid"}}))
    emb, _, sleeps = make(script)
    with pytest.raises(ProviderError, match="API key not valid") as exc_info:
        emb.embed_documents(["a"])
    assert exc_info.value.status_code == 502
    assert len(script.paths) == 1
    assert sleeps == []


def test_500_is_not_retried():
    script = Script(httpx.Response(500, text="boom"))
    emb, _, sleeps = make(script)
    with pytest.raises(ProviderError) as exc_info:
        emb.embed_documents(["a"])
    assert type(exc_info.value) is ProviderError
    assert len(script.paths) == 1 and sleeps == []


def test_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    emb, _, _ = make(handler)
    with pytest.raises(ProviderTimeout):
        emb.embed_query("q")


# --- fallback ------------------------------------------------------------------


def test_fallback_used_when_primary_overloaded():
    script = Script(overloaded(), overloaded(), httpx.Response(200, json=GENERATE_OK))
    _, llm, _ = make(script, fallback="fallback-model")
    assert llm.generate("sys", "prompt") == "Answer [1]"
    assert script.paths == [
        "/v1beta/models/primary-model:generateContent",
        "/v1beta/models/primary-model:generateContent",
        "/v1beta/models/fallback-model:generateContent",
    ]


def test_fallback_tried_only_once():
    script = Script(rate_limited(), rate_limited(), rate_limited(), rate_limited())
    _, llm, _ = make(script, fallback="fallback-model")
    with pytest.raises(ProviderRateLimited):
        llm.generate("sys", "prompt")
    assert script.paths.count("/v1beta/models/fallback-model:generateContent") == 1


def test_fallback_not_used_for_other_errors():
    script = Script(httpx.Response(400, json={"error": {"message": "bad"}}))
    _, llm, _ = make(script, fallback="fallback-model")
    with pytest.raises(ProviderError):
        llm.generate("sys", "prompt")
    assert len(script.paths) == 1


def test_retry_and_fallback_are_logged(caplog):
    caplog.set_level("INFO", logger="app.providers.gemini")
    _, llm, _ = make(Script(rate_limited("1s"), overloaded(), httpx.Response(200, json=GENERATE_OK)), fallback="fallback-model")
    llm.generate("sys", "prompt")

    retry = next(r for r in caplog.records if r.msg == "provider retry")
    assert (retry.op, retry.status, retry.attempt, retry.delay_s) == ("generate", 429, 1, 1.0)
    fb = next(r for r in caplog.records if r.msg == "llm fallback")
    assert (fb.from_model, fb.to_model, fb.reason) == ("primary-model", "fallback-model", "unavailable")


# --- timeouts --------------------------------------------------------------------


def _timeout(request):
    raise httpx.ReadTimeout("slow", request=request)


def test_fallback_on_primary_timeout(caplog):
    caplog.set_level("INFO", logger="app.providers.gemini")

    def handler(request):
        if "primary-model" in request.url.path:
            return _timeout(request)
        return httpx.Response(200, json=GENERATE_OK)

    _, llm, _ = make(handler, fallback="fallback-model")
    assert llm.generate("sys", "prompt") == "Answer [1]"
    fb = next(r for r in caplog.records if r.msg == "llm fallback")
    assert fb.reason == "timeout"


def test_timeout_without_fallback_raises():
    _, llm, _ = make(_timeout)
    with pytest.raises(ProviderTimeout):
        llm.generate("sys", "prompt")


def test_per_request_timeouts():
    seen: dict[str, float] = {}

    def handler(request):
        kind = "generate" if "generateContent" in request.url.path else json.loads(request.content)["requests"][0]["taskType"]
        seen[kind] = request.extensions["timeout"]["read"]
        return httpx.Response(200, json=GENERATE_OK) if kind == "generate" else embed_ok(request)

    client = _GeminiClient("k", 99, transport=httpx.MockTransport(handler), sleep=lambda s: None)
    GeminiEmbeddings(client, "m", 8, timeout_s=30).embed_documents(["a"])
    GeminiEmbeddings(client, "m", 8, timeout_s=30).embed_query("q")
    GeminiLLM(client, "primary-model", timeout_s=20).generate("sys", "prompt")
    assert seen == {"RETRIEVAL_DOCUMENT": 30, "RETRIEVAL_QUERY": 10, "generate": 20}


# --- thinkingConfig --------------------------------------------------------------


def test_thinking_level_sent_only_for_gemini_3_models():
    script = Script(httpx.Response(200, json=GENERATE_OK))
    client = _GeminiClient("k", 5, transport=httpx.MockTransport(script), sleep=lambda s: None)
    GeminiLLM(client, "gemini-3.8-flash").generate("sys", "prompt")
    GeminiLLM(client, "gemini-2.5-flash-lite").generate("sys", "prompt")
    assert script.bodies[0]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert "thinkingConfig" not in script.bodies[1]["generationConfig"]


def test_thinking_config_rejected_then_retried_without_and_remembered():
    rejected = httpx.Response(400, json={"error": {"code": 400, "message": "Unknown field thinking_level in thinking_config"}})
    script = Script(rejected, httpx.Response(200, json=GENERATE_OK))
    client = _GeminiClient("k", 5, transport=httpx.MockTransport(script), sleep=lambda s: None)
    llm = GeminiLLM(client, "gemini-3.8-flash")

    assert llm.generate("sys", "prompt") == "Answer [1]"
    assert "thinkingConfig" in script.bodies[0]["generationConfig"]
    assert "thinkingConfig" not in script.bodies[1]["generationConfig"]

    llm.generate("sys", "prompt")  # remembered: no second rejected attempt
    assert len(script.bodies) == 3
    assert "thinkingConfig" not in script.bodies[2]["generationConfig"]


def test_unrelated_400_on_gemini_3_is_not_retried():
    script = Script(httpx.Response(400, json={"error": {"message": "API key not valid"}}))
    client = _GeminiClient("k", 5, transport=httpx.MockTransport(script), sleep=lambda s: None)
    with pytest.raises(ProviderError, match="API key"):
        GeminiLLM(client, "gemini-3.8-flash").generate("sys", "prompt")
    assert len(script.bodies) == 1


def test_deadline_stops_retry_that_cannot_fit(monkeypatch):
    import app.providers.gemini as gemini

    now = [1000.0]
    monkeypatch.setattr(gemini.time, "monotonic", lambda: now[0])
    script = Script(overloaded(), httpx.Response(200, json=GENERATE_OK))
    client = _GeminiClient("k", 5, transport=httpx.MockTransport(script), sleep=lambda s: None)
    with pytest.raises(ProviderUnavailable):
        client.post("/x", {}, "generate", max_retries=1, max_wait_s=5, timeout_s=20, deadline=now[0] + 2.5)
    assert len(script.bodies) == 1  # a 2s backoff + 1s minimum attempt does not fit in 2.5s
