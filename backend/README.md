# MeetWise Backend (Stage 1)

Meeting intelligence pipeline built on **LangGraph**, with cross-meeting **RAG** retrieval.
Provider-agnostic: chat via Ollama or Groq, embeddings via Ollama (or an offline hashing fallback).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `MEETWISE_LLM_PROVIDER` | `ollama` | `ollama` or `groq` (chat) |
| `MEETWISE_EMBEDDING_PROVIDER` | `ollama` | `ollama` or `hash` (offline fallback) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `MEETWISE_OLLAMA_CHAT_MODEL` | `llama3.1:8b` | Any chat model you have pulled |
| `MEETWISE_OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `GROQ_API_KEY` | — | Required when provider is `groq` |
| `MEETWISE_GROQ_CHAT_MODEL` | `llama-3.3-70b-versatile` | Groq model |
| `GEMINI_API_KEY` | - | Required when embeding provider is `gemini` |
| `MEETWISE_GEMINI_EMBED_MODEL` | `gemini-embedding-2` | Embedding model |
| `MEETWISE_DB_PATH` | `meetwise.db` | SQLite file (meetings, tasks, chunks) |
| `MEETWISE_WINDOW_CHARS` | `12000` | Per-call budget; long transcripts are windowed |
| `MEETWISE_MAX_EXTRACTION_ATTEMPTS` | `2` | Verification retry cap |

Groq has no embeddings endpoint, so use Ollama for embeddings whenever Groq handles chat.

## Run

```bash
uvicorn meetwise.api.main:app --reload
python tests/run_local.py     # unit tests; works without pytest
pytest                        # same tests under pytest
```

## Layout

```
meetwise/
  config.py                 settings from env
  llm/                      provider interfaces + Ollama/Groq factories, offline hashing embedder
  ingest/                   TXT/PDF/DOCX extraction, utterance parsing, windowing
  domain/                   records (ActionItem, Decision, Event...), org context, attribution, verification
  graph/                    LangGraph state, prompts, nodes, workflow wiring
  rag/                      topic-aware chunker, hybrid vector store, reusable retriever
  storage/                  SQLite schema and repository
  services/                 pipeline runner (status/errors), commitment reconciliation
  api/main.py               FastAPI routes
tests/                      domain, ingest, node, RAG, and graph tests
```

## Pipeline

preprocess → metadata → summarize → segment → decisions → events → extract_actions → attribute → verify,
with a conditional edge from `verify` back to `extract_actions` while unsupported items remain
(capped by `MEETWISE_MAX_EXTRACTION_ATTEMPTS`), then persist (store, reconcile commitments, index chunks).

Verification is two-layered: deterministic grounding (cited evidence exists, explicit owners are named,
deadlines appear in the text) followed by an LLM check. If the LLM check is unavailable, results are capped
at `inferred`, so unverified items are never presented as confirmed.

## Notes

- Hashing embeddings match words, not meaning. Use Ollama embeddings for real semantic retrieval.
- Vector search is an exact scan, which suits organisational meeting volumes. Swap in an ANN index behind
  `VectorStore` if the corpus grows large.

## Chat and retrieval

`POST /api/chat` answers questions over processed meetings. Each request names a scope:
`"meeting"` (requires `meeting_id`; the open meeting only) or `"all"` (every processed meeting).
Pass `session_id` to continue a conversation.

Chat is a LangGraph workflow: plan → retrieve → grade → answer → verify → finalize.

- **Plan** rewrites the question into a search query, resolves relative dates against today, and decides whether task records should be included.
- **Retrieve** runs hybrid search, plus task records with their history for commitment questions. Across meetings, hits are capped per meeting.
- **Grade** stops early when nothing relevant is found. The model is not called and the user is told so.
- **Answer** must cite sources as `[S1]`, `[S2]`, and so on. It must mark conclusions as inferred and may say that evidence is insufficient.
- **Verify** rejects citations to sources that were not provided, and rejects numbers that do not appear in the cited sources. It retries a bounded number of times, then refuses rather than presenting an unchecked answer.

Each assistant message returns `citations` with a `link` back to the meeting transcript section (`/meetings/{id}#U002`) or the task.

Other endpoints: `GET /api/chat/sessions`, `GET /api/chat/sessions/{id}`.

## Local calendar

Calendar data is stored in the app's SQLite database only. Nothing syncs to an external calendar.

Events extracted from transcripts are stored as `pending_review` and are hidden from the calendar until
confirmed. Reprocessing a meeting replaces its pending suggestions but never touches confirmed events.
Undated suggestions are kept for review without a calendar slot.

- `GET /api/events?start=YYYY-MM-DD&end=YYYY-MM-DD` lists confirmed events (monthly and weekly views).
- `GET /api/events/pending` lists suggestions awaiting review.
- `POST /api/events/{id}/confirm` accepts optional corrected `starts_at`, `ends_at`, and `title`.
- `POST`, `PATCH`, and `DELETE` on `/api/events` create, edit, and remove events.

Email is out of scope.
