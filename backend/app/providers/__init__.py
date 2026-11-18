from app.config import Settings
from app.providers.base import (
    EmbeddingProvider,
    LLMProvider,
    ProviderError,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)

__all__ = [
    "EmbeddingProvider",
    "LLMProvider",
    "ProviderError",
    "ProviderRateLimited",
    "ProviderTimeout",
    "ProviderUnavailable",
    "build_providers",
]


def build_providers(settings: Settings) -> tuple[EmbeddingProvider, LLMProvider, object | None]:
    """Returns (embedder, llm, closable resource or None)."""
    if settings.provider == "fake":
        from app.providers.fake import FakeEmbeddings, FakeLLM

        return FakeEmbeddings(), FakeLLM(), None

    from app.providers.gemini import GeminiEmbeddings, GeminiLLM, _GeminiClient

    client = _GeminiClient(settings.gemini_api_key or "", settings.provider_timeout_s)
    return (
        GeminiEmbeddings(
            client, settings.gemini_embedding_model, settings.embedding_dim, batch_size=settings.embed_batch_size
        ),
        GeminiLLM(client, settings.gemini_chat_model, fallback_model=settings.gemini_chat_fallback_model),
        client,
    )
