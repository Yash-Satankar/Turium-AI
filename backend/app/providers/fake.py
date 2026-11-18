"""Deterministic offline providers for tests and for trying the app without an API key.

Embeddings are hashed bag-of-words vectors, so texts sharing words score higher;
good enough to exercise retrieval end to end, not a real semantic model.
"""

import hashlib
import math
import re

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be by do does for from has have how i in is it its me my of on or "
    "that the this to was what when where which who why with you your".split()
)


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


class FakeEmbeddings:
    def __init__(self, dim: int = 256):
        self.dim = dim
        self.model_id = f"fake:hash-bow:{dim}"

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _tokens(text):
            h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big")
            vec[h % self.dim] += 1.0 if (h >> 32) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class FakeLLM:
    """Echoes the first sentence of the top passage with a citation."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        match = re.search(r"<passage index=\"1\"[^>]*>\n(.*?)\n</passage>", prompt, re.S)
        if not match:
            return "I couldn't find that in your saved content."
        first = re.split(r"(?<=[.!?])\s", match.group(1).strip(), maxsplit=1)[0]
        return f"{first} [1]"
