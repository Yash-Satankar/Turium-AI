"""Google Gemini (AI Studio) over its REST API.

Plain httpx instead of an SDK so timeouts and error mapping are explicit:
429 -> ProviderRateLimited, timeouts -> ProviderTimeout, anything else -> ProviderError.
"""

import logging
import time
from typing import Any

import httpx

from app.providers.base import ProviderError, ProviderRateLimited, ProviderTimeout

logger = logging.getLogger(__name__)

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
EMBED_BATCH_LIMIT = 100  # batchEmbedContents accepts at most 100 requests


class _GeminiClient:
    def __init__(self, api_key: str, timeout_s: float, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(
            base_url=BASE_URL,
            timeout=timeout_s,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            transport=transport,
        )

    def post(self, path: str, body: dict[str, Any], op: str) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            resp = self._http.post(path, json=body)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"Gemini {op} timed out") from exc
        except httpx.RequestError as exc:
            raise ProviderError(f"Could not reach Gemini ({type(exc).__name__})") from exc
        duration_ms = round((time.perf_counter() - start) * 1000)
        logger.info("provider call", extra={"provider": "gemini", "op": op, "status": resp.status_code, "duration_ms": duration_ms})

        if resp.status_code == 429:
            raise ProviderRateLimited("Gemini rate limit reached; try again shortly")
        if resp.status_code >= 400:
            raise ProviderError(f"Gemini {op} failed (HTTP {resp.status_code}): {_error_message(resp)}")
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError(f"Gemini {op} returned invalid JSON") from exc

    def close(self) -> None:
        self._http.close()


def _error_message(resp: httpx.Response) -> str:
    try:
        msg = resp.json().get("error", {}).get("message")
    except ValueError:
        msg = None
    return (msg or resp.reason_phrase or "unknown error")[:300]


class GeminiEmbeddings:
    def __init__(self, client: _GeminiClient, model: str, dim: int):
        self._client = client
        self._model = model
        self._dim = dim
        self.model_id = f"gemini:{model}:{dim}"

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH_LIMIT):
            batch = texts[i : i + EMBED_BATCH_LIMIT]
            body = {
                "requests": [
                    {
                        "model": f"models/{self._model}",
                        "content": {"parts": [{"text": t}]},
                        "taskType": task_type,
                        "outputDimensionality": self._dim,
                    }
                    for t in batch
                ]
            }
            data = self._client.post(f"/models/{self._model}:batchEmbedContents", body, op="embed")
            embeddings = data.get("embeddings") or []
            if len(embeddings) != len(batch):
                raise ProviderError("Gemini returned an unexpected number of embeddings")
            vectors.extend(e["values"] for e in embeddings)
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "RETRIEVAL_QUERY")[0]


class GeminiLLM:
    def __init__(self, client: _GeminiClient, model: str):
        self._client = client
        self._model = model

    def generate(self, system: str, prompt: str) -> str:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }
        data = self._client.post(f"/models/{self._model}:generateContent", body, op="generate")
        candidates = data.get("candidates") or []
        parts = (candidates[0].get("content") or {}).get("parts", []) if candidates else []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
        if not text:
            reason = candidates[0].get("finishReason") if candidates else (data.get("promptFeedback") or {}).get("blockReason")
            raise ProviderError(f"Gemini returned no answer (reason: {reason or 'unknown'})")
        return text
