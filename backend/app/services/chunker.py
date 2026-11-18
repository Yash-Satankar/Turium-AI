"""Character-based chunking: paragraphs, then sentences, packed greedily with overlap.

~800 chars (~150-200 tokens) keeps each chunk about one idea, which keeps similarity
scores focused and makes chunks short enough to show as citation snippets.
"""

import re

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _hard_split(text: str, size: int) -> list[str]:
    """Split an over-long sentence at word boundaries; slice words longer than `size`."""
    pieces: list[str] = []
    current = ""
    for word in text.split():
        while len(word) > size:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(word[:size])
            word = word[size:]
        candidate = f"{current} {word}" if current else word
        if len(candidate) <= size:
            current = candidate
        else:
            pieces.append(current)
            current = word
    if current:
        pieces.append(current)
    return pieces


def _units(text: str, size: int) -> list[tuple[str, str]]:
    """(separator_before, text) pieces, each no longer than `size`."""
    units: list[tuple[str, str]] = []
    for para in _PARAGRAPH_BREAK.split(text):
        para = para.strip()
        if not para:
            continue
        pieces = [para] if len(para) <= size else [
            piece
            for sentence in _SENTENCE_END.split(para)
            for piece in ([sentence] if len(sentence) <= size else _hard_split(sentence, size))
        ]
        for i, piece in enumerate(pieces):
            units.append(("\n\n" if i == 0 else " ", piece))
    return units


def _tail(text: str, overlap: int) -> str:
    """The last ~`overlap` chars of text, starting at a word boundary."""
    if overlap <= 0 or len(text) <= overlap:
        return ""
    tail = text[-overlap:]
    space = tail.find(" ")
    return tail[space + 1 :].strip() if space != -1 else ""


def chunk_text(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    text = normalize(text)
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    current = ""
    for sep, unit in _units(text, size):
        if not current:
            current = unit
        elif len(current) + len(sep) + len(unit) <= size:
            current = f"{current}{sep}{unit}"
        else:
            chunks.append(current)
            tail = _tail(current, overlap)
            current = f"{tail} {unit}" if tail and len(tail) + 1 + len(unit) <= size else unit
    if current:
        chunks.append(current)
    return chunks
