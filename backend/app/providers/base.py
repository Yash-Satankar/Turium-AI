from typing import Protocol

from app.errors import AppError


class ProviderError(AppError):
    status_code = 502
    code = "PROVIDER_ERROR"

    def __init__(self, message: str, *, upstream_status: int | None = None):
        super().__init__(message)
        self.upstream_status = upstream_status  # HTTP status the provider returned, if any


class ProviderRateLimited(ProviderError):
    status_code = 503
    code = "PROVIDER_RATE_LIMITED"


class ProviderUnavailable(ProviderError):
    """The provider returned 503 (model overloaded)."""

    status_code = 503
    code = "PROVIDER_UNAVAILABLE"


class ProviderTimeout(ProviderError):
    status_code = 504
    code = "PROVIDER_TIMEOUT"


class EmbeddingProvider(Protocol):
    # Identifies the vector space. Stored with each chunk; only chunks with the
    # current model_id are searched, so switching models never mixes spaces.
    model_id: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class LLMProvider(Protocol):
    def generate(self, system: str, prompt: str) -> str: ...
