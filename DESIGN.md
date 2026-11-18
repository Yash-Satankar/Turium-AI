# AI Knowledge Inbox — Design

A small single-user app: save notes or URLs, then ask questions answered by a RAG pipeline with cited sources.

## Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI + Pydantic v2 (Python 3.11+) | Typed request validation, discriminated unions for the ingest contract, built-in background tasks |
| Storage | SQLite (stdlib `sqlite3`, WAL mode) | Zero setup; items, chunks and vectors in one file; easy for a reviewer to run |
| Vector search | Brute-force cosine similarity in NumPy | Exact results, no extra service; fast enough for thousands of chunks |
| Text extraction | `httpx` + `trafilatura` | Timeouts and size caps on fetch; trafilatura strips nav/boilerplate so chunks are cleaner |
| Embeddings + LLM | Google Gemini API (free AI Studio key) behind a provider interface | No paid key needed; OpenAI or a local model is a drop-in implementation |
| Frontend | React + Vite + TypeScript + Tailwind | Hooks for state (`useItems`, `useAsk`), no global store needed |

## Architecture

```
React (Vite)  ──HTTP/JSON──►  FastAPI
                               ├─ api/routes      thin: parse → call service → shape response
                               ├─ services        ingestion, fetcher, extractor, chunker, retrieval, rag
                               ├─ providers       EmbeddingProvider / LLMProvider (gemini, fake)
                               └─ db              connection + repositories (raw SQL)
                                     │
                                  SQLite (items, chunks + float32 vectors)
```

## Ingestion flow (async)

1. `POST /ingest` validates input synchronously, inserts the item with `status=pending`, schedules a background task, returns **202** with the item.
2. The background task sets `processing` → (URL only) fetch + extract text and title → chunk → embed → store chunks → `ready`.
3. Any failure sets `failed` with a human-readable `error`. Nothing is half-written: chunks are inserted in one transaction.
4. On startup, items left in `pending`/`processing` (server died mid-job) are marked `failed: "interrupted by restart"`.
5. The UI polls `GET /items` every 2 s while any item is `pending` or `processing`.

**Validation split (deliberate):**
- Synchronous → 422: empty/whitespace note, note > 20,000 chars, malformed URL, non-http(s) scheme, `localhost` or private/loopback/link-local IP literal (SSRF guard).
- Asynchronous → `failed` status: DNS resolves to a private IP, unreachable host, timeout (10 s), non-2xx, non-HTML content type, body > 2 MB, no extractable text.

Rationale: the client gets fast feedback on things it can fix; network outcomes are only known after fetching, which is exactly the slow work we moved off the request path.

## Data model

```sql
items(
  id TEXT PRIMARY KEY,                 -- uuid4
  source_type TEXT CHECK (source_type IN ('note','url')),
  title TEXT,                          -- note: first line (≤80 chars); url: page title once fetched
  url TEXT,                            -- null for notes
  raw_content TEXT,                    -- note text, or extracted page text
  status TEXT CHECK (status IN ('pending','processing','ready','failed')),
  error TEXT,
  created_at TEXT, updated_at TEXT     -- ISO 8601 UTC
)
chunks(
  id INTEGER PRIMARY KEY,
  item_id TEXT REFERENCES items(id) ON DELETE CASCADE,
  chunk_index INTEGER,
  text TEXT,
  embedding BLOB,                      -- float32 bytes
  embedding_model TEXT,                -- only chunks matching the current model are searched
  created_at TEXT
)
```

## Chunking

- Target ~800 characters, ~120 characters overlap.
- Split on paragraphs first, then sentences; pack greedily up to the target. A single over-long sentence is hard-split.
- Text ≤ 800 chars stays one chunk (most notes).
- Why: ~150–200 tokens holds one idea, so similarity scores stay focused; snippets are short enough to show as citations; overlap avoids losing an answer that straddles a boundary. Character-based is simpler than token-based and close enough for retrieval.

## Retrieval + answer

- Embed the question (query task type), load vectors for `ready` items with the current `embedding_model`, cosine similarity, take `top_k` (default 5, max 10).
- If the best score < `MIN_SCORE` (configurable), return `found: false` with a fixed "not found in your saved content" answer and **skip the LLM**.
- Otherwise build a prompt with chunks labelled `[1]…[k]`, instruct the model to answer only from them, cite as `[n]`, and say so if the context doesn't contain the answer. Return the answer plus `sources` in the same order.

## API

All errors share one shape:

```json
{"error": {"code": "VALIDATION_ERROR", "message": "...", "details": [], "request_id": "..."}}
```

| Status | Code | When |
|---|---|---|
| 422 | `VALIDATION_ERROR` | Body/query fails validation |
| 404 | `NOT_FOUND` | Unknown route |
| 405 | `METHOD_NOT_ALLOWED` | Wrong method |
| 502 | `PROVIDER_ERROR` | Embedding/LLM provider returned an error |
| 503 | `PROVIDER_RATE_LIMITED` | Provider returned 429 (after retries) |
| 503 | `PROVIDER_UNAVAILABLE` | Provider returned 503, model overloaded (after retries) |
| 504 | `PROVIDER_TIMEOUT` | Provider call timed out |
| 500 | `INTERNAL_ERROR` | Anything unexpected (details logged, not leaked) |

`POST /ingest`
```json
{"source_type": "note", "content": "..."}
{"source_type": "url",  "url": "https://example.com/post"}
→ 202 {"id", "source_type", "title", "url", "preview", "status": "pending", "error": null, "chunk_count": 0, "created_at", "updated_at"}
```

`GET /items?limit=50` (1–200, newest first)
```json
→ 200 {"items": [ { same item shape } ]}
```

`POST /query`
```json
{"question": "...", "top_k": 5}
→ 200 {"answer": "... [1] ...", "found": true,
       "sources": [{"index": 1, "item_id", "source_type", "title", "url", "snippet", "score"}]}
```

`GET /health` → 200 `{"status": "ok"}`

## Observability

- JSON logs (stdlib `logging` + custom formatter): `ts`, `level`, `logger`, `msg`, `request_id`, plus event fields.
- Middleware assigns/propagates `X-Request-ID`, logs method, path, status, duration.
- Background jobs log `item_id` and each status transition with timing.

## What breaks at scale → production changes

| Breaks | Change |
|---|---|
| Brute-force search loads every vector per query | pgvector (HNSW) or a vector DB (Qdrant) with ANN indexes |
| In-process background tasks are lost on restart, no retries | Durable queue (Redis/RQ, Celery, SQS) + worker, retries with backoff, idempotency keys |
| SQLite single-writer | Postgres |
| Same URL ingested twice duplicates chunks | Content hash + dedupe |
| Polling | SSE/WebSocket status updates |
| Single user, no auth | Auth + per-user scoping of items and retrieval |
| Fixed-size chunking | Structure-aware chunking, hybrid search (BM25 + vectors), reranking |
| Changing embedding model orphans old vectors | Re-embedding job keyed on `embedding_model` |

## Out of scope (intentionally)

Auth, delete/edit endpoints, retries, dedup, streaming answers, Docker, frontend tests.
