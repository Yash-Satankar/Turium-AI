"""Google Gemini (AI Studio) over its REST API.

Plain httpx instead of an SDK so timeouts, retries and error mapping are explicit:
429 -> ProviderRateLimited, 503 -> ProviderUnavailable (both retried first),
timeouts -> ProviderTimeout, anything else -> ProviderError.
"""

import logging
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.providers.base import ProviderError, ProviderRateLimited, ProviderTimeout, ProviderUnavailable

logger = logging.getLogger(__name__)

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
RETRYABLE_STATUSES = (429, 503)
UNAVAILABLE_MESSAGE = "The AI model is overloaded right now; try again in a moment"

# Retry budgets. Background ingestion can afford to wait; a user waiting on /query can't.
BACKGROUND_RETRIES, BACKGROUND_MAX_WAIT_S = 3, 30.0
INTERACTIVE_RETRIES, INTERACTIVE_MAX_WAIT_S = 1, 5.0

# Worst-case /query latency with defaults (GEMINI_GENERATE_TIMEOUT_S=20):
#   query embed: one short text; timeout capped at QUERY_EMBED_TIMEOUT_S (10s),
#                plus at most one 429/503 retry after <=5s           -> <= 15s
#   generate:    primary attempt(s) and the one fallback attempt share a single
#                deadline of generate_timeout + GENERATE_EXTRA_BUDGET_S -> <= 35s
#   total                                                             -> ~50s
QUERY_EMBED_TIMEOUT_S = 10.0
GENERATE_EXTRA_BUDGET_S = 15.0
MIN_ATTEMPT_S = 1.0  # never start a request with less time than this left

_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)s\s*$")  # protobuf Duration JSON, e.g. "17s", "0.5s"


def _server_retry_delay(resp: httpx.Response) -> float | None:
    """Delay the server asked for: error.details[].retryDelay, else Retry-After."""
    try:
        details = resp.json().get("error", {}).get("details") or []
    except (ValueError, AttributeError):
        details = []
    for detail in details:
        if isinstance(detail, dict) and isinstance(detail.get("retryDelay"), str):
            if m := _DURATION.match(detail["retryDelay"]):
                return float(m.group(1))

    header = resp.headers.get("retry-after")
    if header:
        header = header.strip()
        if header.isdigit():
            return float(header)
        try:
            return max(0.0, (parsedate_to_datetime(header) - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError):
            pass
    return None


def _error_message(resp: httpx.Response) -> str:
    try:
        msg = resp.json().get("error", {}).get("message")
    except (ValueError, AttributeError):
        msg = None
    return (msg or resp.reason_phrase or "unknown error")[:300]


class _GeminiClient:
    def __init__(
        self,
        api_key: str,
        timeout_s: float,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=BASE_URL,
            timeout=timeout_s,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            transport=transport,
        )

    def post(
        self,
        path: str,
        body: dict[str, Any],
        op: str,
        *,
        max_retries: int,
        max_wait_s: float,
        timeout_s: float,
        deadline: float | None = None,
    ) -> dict[str, Any]:
        """POST with retries on 429/503. `deadline` (time.monotonic()) bounds every attempt and wait."""
        attempt = 0
        while True:
            resp = self._send(path, body, op, _attempt_timeout(timeout_s, deadline, op))
            if resp.status_code not in RETRYABLE_STATUSES or attempt >= max_retries:
                break
            server_delay = _server_retry_delay(resp)
            delay = min(server_delay if server_delay is not None else 2.0 ** (attempt + 1), max_wait_s)
            if deadline is not None and time.monotonic() + delay + MIN_ATTEMPT_S > deadline:
                break  # no time left for another attempt
            attempt += 1
            logger.info(
                "provider retry",
                extra={"provider": "gemini", "op": op, "status": resp.status_code, "attempt": attempt, "delay_s": delay},
            )
            self._sleep(delay)

        if resp.status_code == 429:
            raise ProviderRateLimited("Gemini rate limit reached; try again shortly", upstream_status=429)
        if resp.status_code == 503:
            raise ProviderUnavailable(UNAVAILABLE_MESSAGE, upstream_status=503)
        if resp.status_code >= 400:
            raise ProviderError(
                f"Gemini {op} failed (HTTP {resp.status_code}): {_error_message(resp)}",
                upstream_status=resp.status_code,
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError(f"Gemini {op} returned invalid JSON") from exc

    def _send(self, path: str, body: dict[str, Any], op: str, timeout_s: float) -> httpx.Response:
        start = time.perf_counter()
        try:
            resp = self._http.post(path, json=body, timeout=timeout_s)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"Gemini {op} timed out") from exc
        except httpx.RequestError as exc:
            raise ProviderError(f"Could not reach Gemini ({type(exc).__name__})") from exc
        duration_ms = round((time.perf_counter() - start) * 1000)
        logger.info("provider call", extra={"provider": "gemini", "op": op, "status": resp.status_code, "duration_ms": duration_ms})
        return resp

    def close(self) -> None:
        self._http.close()


def _attempt_timeout(timeout_s: float, deadline: float | None, op: str) -> float:
    if deadline is None:
        return timeout_s
    remaining = deadline - time.monotonic()
    if remaining < MIN_ATTEMPT_S:
        raise ProviderTimeout(f"Gemini {op} timed out")
    return min(timeout_s, remaining)


class GeminiEmbeddings:
    def __init__(self, client: _GeminiClient, model: str, dim: int, batch_size: int = 20, timeout_s: float = 30.0):
        if not 1 <= batch_size <= 100:  # batchEmbedContents accepts at most 100 requests
            raise ValueError("batch_size must be between 1 and 100")
        self._client = client
        self._model = model
        self._dim = dim
        self._batch_size = batch_size
        self._timeout_s = timeout_s
        self.model_id = f"gemini:{model}:{dim}"

    def _embed(
        self, texts: list[str], task_type: str, *, max_retries: int, max_wait_s: float, timeout_s: float
    ) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
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
            data = self._client.post(
                f"/models/{self._model}:batchEmbedContents",
                body,
                op="embed",
                max_retries=max_retries,
                max_wait_s=max_wait_s,
                timeout_s=timeout_s,
            )
            embeddings = data.get("embeddings") or []
            if len(embeddings) != len(batch):
                raise ProviderError("Gemini returned an unexpected number of embeddings")
            vectors.extend(e["values"] for e in embeddings)
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # Background ingestion job: patient retries, full PROVIDER_TIMEOUT_S.
        return self._embed(
            texts,
            "RETRIEVAL_DOCUMENT",
            max_retries=BACKGROUND_RETRIES,
            max_wait_s=BACKGROUND_MAX_WAIT_S,
            timeout_s=self._timeout_s,
        )

    def embed_query(self, text: str) -> list[float]:
        # /query, user waiting: a single short text, so a short timeout is plenty.
        return self._embed(
            [text],
            "RETRIEVAL_QUERY",
            max_retries=INTERACTIVE_RETRIES,
            max_wait_s=INTERACTIVE_MAX_WAIT_S,
            timeout_s=min(self._timeout_s, QUERY_EMBED_TIMEOUT_S),
        )[0]


_FALLBACK_REASONS: dict[type[ProviderError], str] = {
    ProviderRateLimited: "rate_limited",
    ProviderUnavailable: "unavailable",
    ProviderTimeout: "timeout",
}


def _rejects_thinking_config(exc: ProviderError) -> bool:
    return exc.upstream_status == 400 and "thinking" in exc.message.lower()


class GeminiLLM:
    def __init__(self, client: _GeminiClient, model: str, fallback_model: str | None = None, timeout_s: float = 20.0):
        self._client = client
        self._model = model
        # Chat only: an embedding fallback would mix vector spaces.
        self._fallback_model = fallback_model or None
        self._timeout_s = timeout_s
        # Models that rejected thinkingConfig, remembered for the process lifetime.
        self._no_thinking: set[str] = set()

    def generate(self, system: str, prompt: str) -> str:
        deadline = time.monotonic() + self._timeout_s + GENERATE_EXTRA_BUDGET_S
        try:
            return self._generate(self._model, system, prompt, INTERACTIVE_RETRIES, deadline)
        except (ProviderRateLimited, ProviderUnavailable, ProviderTimeout) as exc:
            if not self._fallback_model:
                raise
            logger.warning(
                "llm fallback",
                extra={"from_model": self._model, "to_model": self._fallback_model, "reason": _FALLBACK_REASONS[type(exc)]},
            )
            return self._generate(self._fallback_model, system, prompt, 0, deadline)  # one try

    def _generate(self, model: str, system: str, prompt: str, max_retries: int, deadline: float) -> str:
        config: dict[str, Any] = {"temperature": 0.2}
        thinking = model.startswith("gemini-3") and model not in self._no_thinking
        if thinking:
            config["thinkingConfig"] = {"thinkingLevel": "low"}  # lower latency; answers are extractive
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": config,
        }
        try:
            data = self._post(model, body, max_retries, deadline)
        except ProviderError as exc:
            if not (thinking and _rejects_thinking_config(exc)):
                raise
            logger.warning("thinkingConfig rejected; retrying without it", extra={"model": model, "error": exc.message})
            self._no_thinking.add(model)
            del config["thinkingConfig"]
            data = self._post(model, body, max_retries, deadline)

        candidates = data.get("candidates") or []
        parts = (candidates[0].get("content") or {}).get("parts", []) if candidates else []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
        if not text:
            reason = candidates[0].get("finishReason") if candidates else (data.get("promptFeedback") or {}).get("blockReason")
            raise ProviderError(f"Gemini returned no answer (reason: {reason or 'unknown'})")
        return text

    def _post(self, model: str, body: dict[str, Any], max_retries: int, deadline: float) -> dict[str, Any]:
        return self._client.post(
            f"/models/{model}:generateContent",
            body,
            op="generate",
            max_retries=max_retries,
            max_wait_s=INTERACTIVE_MAX_WAIT_S,
            timeout_s=self._timeout_s,
            deadline=deadline,
        )
