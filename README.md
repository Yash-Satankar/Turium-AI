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
cd backend && pytest          # 81 tests, offline (fake provider + mocked HTTP)
cd frontend && npm run build  # typecheck + production build
```

## Configuration

All settings are environment variables (or `backend/.env`):

| Variable | Default | Notes |
|---|---|---|
| `PROVIDER` | `gemini` | `gemini` or `fake` |
| `GEMINI_API_KEY` | none | Required for `gemini` |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` | |
| `GEMINI_CHAT_MODEL` | `gemini-2.5-flash` | |
| `EMBEDDING_DIM` | `768` | Passed as `outputDimensionality` |
| `MIN_SCORE` | `0.6` | Below this, `/query` answers "not found" without calling the LLM. Tune per model: watch `best_score` in the `query answered` log line |
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
  api/               routes (thin) + Pydantic schemas (discriminated ingest union)
  services/          ingestion (background job), fetcher, url_safety, extractor, chunker, retrieval, rag
  providers/         EmbeddingProvider / LLMProvider protocols, gemini (REST via httpx), fake
  db/                connection + schema, repositories (raw SQL)
backend/tests/       API, fetcher/SSRF, chunker, Gemini client (mocked transport)
frontend/src/
  api/               typed client + ApiError
  hooks/             useItems (polling while pending/processing), useAsk
  components/        IngestForm, ItemList, AskPanel (clickable [n] citations)
```

## Implementation notes

Things the design doc left open, and how they were decided:

- **Embedding model ID includes the dimension** (`gemini:gemini-embedding-001:768`), so changing `EMBEDDING_DIM` also isolates old vectors instead of mixing vector spaces.
- **Redirects are followed manually** and every hop is re-checked (scheme, IP literal, DNS resolution), so a public URL can't redirect to `169.254.169.254`.
- **Known gap: DNS rebinding.** The resolved IPs are checked, but httpx resolves the host again when it connects. Production should pin the connection to the vetted IP (custom transport) or send fetches through an egress proxy.
- **Prompt injection.** Passages are wrapped in `<passage>` tags with their text escaped, and the system prompt says passage content is data. This reduces the risk but does not remove it.
- **Background jobs are claimed** with a conditional `UPDATE … WHERE status='pending'`, so a job never runs twice for the same item.
- **Chunks and the `ready` flip happen in one transaction**, so an item is either fully searchable or not at all.
- **One SQLite connection per unit of work.** Handlers and background tasks run on different threads, and pooled connections can't be shared across threads.
- **Sync route handlers**: FastAPI runs them in its threadpool, so blocking SQLite and provider calls don't stall the event loop.
