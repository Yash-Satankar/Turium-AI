# AI Knowledge Inbox

Save notes or URLs, then ask questions answered from your saved content, with cited sources.

FastAPI + SQLite + NumPy on the backend, React + Vite + Tailwind on the frontend, Google Gemini for embeddings and answers. The design and its trade-offs are in [DESIGN.md](DESIGN.md).

## Quick start

Requires Python 3.11+ and Node 20+.

### 1. Backend (port 8000)

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # then set GEMINI_API_KEY (free at https://aistudio.google.com)
uvicorn app.main:create_app --factory --reload --port 8000
```

No key? Set `PROVIDER=fake` in `.env`. It uses deterministic bag-of-words embeddings and an echo "LLM", so you can run the whole flow offline. Its answers are not real answers.

### 2. Frontend (port 5173)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api/*` to the backend, so no CORS setup is needed in dev.

### Tests

```bash
cd backend && pytest          # 110 tests, offline (fake provider + mocked HTTP)
cd frontend && npm run build  # typecheck + production build
```

## Configuration

All settings are environment variables (or `backend/.env`):

| Variable | Default | Notes |
|---|---|---|
| `PROVIDER` | `gemini` | `gemini` or `fake` |
| `GEMINI_API_KEY` | none | Required for `gemini` |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` | |
| `GEMINI_CHAT_MODEL` | `gemini-3.8-flash` | |
| `GEMINI_CHAT_FALLBACK_MODEL` | empty (disabled) | Chat model tried once when the primary returns 429/503 after retries, e.g. a Flash-Lite model on the free tier. Never used for embeddings |
| `EMBED_BATCH_SIZE` | `20` | Texts per embedding request (1–100). Smaller batches are gentler on free-tier limits |
| `EMBEDDING_DIM` | `768` | Passed as `outputDimensionality` |
| `MIN_SCORE` | `0.6` | Chunks scoring below this are dropped before prompting and never cited; if none remain, `/query` answers "not found" without calling the LLM. Tune per model: watch `best_score` in the `query answered` log line |
| `DATABASE_PATH` | `data/inbox.db` | |
| `FETCH_TIMEOUT_S` / `FETCH_MAX_BYTES` / `FETCH_MAX_REDIRECTS` | `10` / `2000000` / `5` | |
| `FETCH_USER_AGENT` | `KnowledgeInbox/0.1 (python-httpx)` | Wikipedia and some other sites return 403 unless the UA includes a contact URL or email, e.g. `MyInbox/1.0 (+https://you.example)` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `800` / `120` | Characters |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | JSON list |
| `LOG_LEVEL` | `INFO` | |

## Layout

```
backend/app/
  main.py            app factory: lifespan (schema, restart recovery), request-ID middleware, error envelope
  config.py          settings
  text_utils.py      truncate() for titles, previews, snippets
  api/               routes (call services only, never db) + Pydantic schemas (discriminated ingest union)
  services/          ingestion (background job), items, fetcher, url_safety, extractor, chunker, retrieval, rag
  providers/         EmbeddingProvider / LLMProvider protocols, gemini (REST via httpx), fake
  db/                connection + schema, repositories (raw SQL)
backend/tests/       API, ingestion job, fetcher/SSRF, chunker, text_utils, Gemini client (mocked transport)
frontend/src/
  api/               typed client + ApiError
  hooks/             useItems (polling while pending/processing), useAsk
  components/        IngestForm, ItemList, AskPanel (clickable [n] citations)
```

## Implementation notes

Things the design doc left open, and how they were decided:

- **Embedding model ID includes the dimension** (`gemini:gemini-embedding-001:768`), so changing `EMBEDDING_DIM` also isolates old vectors instead of mixing vector spaces.
- **Redirects are followed manually** and every hop is re-checked (scheme, IP literal, DNS resolution), so a public URL can't redirect to `169.254.169.254` (but see the DNS-rebinding limitation below).
- **Sources are filtered by `MIN_SCORE`**, not just gated by the best score: weak matches never reach the prompt or the cited sources.
- **Gemini 429/503 are retried** using the server's `retryDelay` (else `Retry-After`, else 2 s/4 s/8 s backoff). Background calls (document embedding) get 3 retries with waits capped at 30 s; calls a user waits on (query embedding, answer generation) get 1 retry capped at 5 s. If `GEMINI_CHAT_FALLBACK_MODEL` is set, a rate-limited or overloaded answer call is tried once on that model; embeddings never fall back, since another model would put vectors in a different space.
- **Prompt injection.** Passages are wrapped in `<passage>` tags with their text escaped, and the system prompt says passage content is data. This reduces the risk but does not remove it.
- **Background jobs are claimed** with a conditional `UPDATE … WHERE status='pending'`, so a job never runs twice for the same item. The job never raises: every failure ends in `failed` with a readable error, or is logged if storage itself is down.
- **Chunks and the `ready` flip happen in one transaction**, so an item is either fully searchable or not at all.
- **One SQLite connection per unit of work.** Handlers and background tasks run on different threads, and pooled connections can't be shared across threads.
- **Routes only call services**; database access lives in `services/` and `db/`.
- **Sync route handlers**: FastAPI runs them in its threadpool, so blocking SQLite and provider calls don't stall the event loop.

## Known limitations

- **`found: true` can still come with a "not found" answer.** `found` means at least one chunk cleared `MIN_SCORE`; the LLM may still decide those chunks don't answer the question and say so. The UI shows the answer text as returned.
- **No delete or edit.** Items can only be added. A wrong or duplicate item stays searchable.
- **Status updates use polling, not push.** The UI polls `GET /items` every 2 s while any item is `pending` or `processing`.
- **DNS-rebinding gap in the SSRF guard.** Resolved IPs are checked, but httpx resolves the host again when it connects, so a hostile DNS server could answer differently the second time. Production should pin the connection to the vetted IP (custom transport) or route fetches through an egress proxy.
- **Single process, in-process jobs.** Ingestion runs as FastAPI background tasks in the API process. Jobs in flight when the process crashes or restarts are lost; on the next startup those items are marked `failed` ("Interrupted by server restart") and must be re-added. There are no retries.
- **Failed items can't be retried in place**; re-ingest the URL.
