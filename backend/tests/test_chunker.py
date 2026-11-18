from app.services.chunker import chunk_text


def test_empty_and_whitespace():
    assert chunk_text("") == []
    assert chunk_text("  \n\n  ") == []


def test_short_text_is_one_chunk():
    text = "A short note.\n\nWith two paragraphs."
    assert chunk_text(text) == [text]


def test_long_text_respects_size_and_covers_everything():
    paragraphs = [" ".join(f"Sentence {p}-{s} talks about topic {p}." for s in range(12)) for p in range(6)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, size=800, overlap=120)
    assert len(chunks) > 1
    assert all(len(c) <= 800 for c in chunks)
    for p in range(6):
        for s in range(12):
            assert any(f"Sentence {p}-{s} " in c for c in chunks), f"lost sentence {p}-{s}"


def test_consecutive_chunks_overlap():
    text = " ".join(f"Fact number {i} is here." for i in range(200))
    chunks = chunk_text(text, size=300, overlap=60)
    for prev, nxt in zip(chunks, chunks[1:]):
        head = nxt.split(" ")[0:3]
        assert " ".join(head) in prev, "next chunk should start with the tail of the previous one"


def test_overlong_sentence_is_hard_split():
    text = "word " * 500  # one 2500-char "sentence"
    chunks = chunk_text(text, size=800, overlap=0)
    assert len(chunks) >= 3
    assert all(len(c) <= 800 for c in chunks)


def test_giant_single_token():
    chunks = chunk_text("x" * 2000, size=800, overlap=0)
    assert [len(c) for c in chunks] == [800, 800, 400]
