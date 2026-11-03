# MeetWise

**Meeting Intelligence & Action Management**

MeetWise is an AI-powered meeting intelligence application that transforms meeting transcripts into structured summaries, action items, and calendar events. It also provides a conversational assistant that can answer questions using information from individual meetings or across an organization's meeting history.

The application combines a React frontend with a FastAPI backend, using LangGraph to orchestrate meeting processing and conversational workflows.

## Features

### Meeting Intelligence
- Upload and process meeting transcripts.
- Generate meeting titles and executive summaries.
- Extract decisions, action items, and calendar events.
- Attribute tasks to individuals using user profiles, roles, and team information.
- Verify extracted information against the original transcript before presenting it.

### Conversational Assistant
- Ask questions about a specific meeting or across all processed meetings.
- Retrieve relevant information from previous meetings using RAG.
- Use meeting metadata, such as titles and dates, to support retrieval.
- Receive answers with citations linking directly to the relevant transcript sections.
- Continue conversations using chat sessions.

### Action Item Management
- View extracted tasks and their assigned owners.
- Track task deadlines and statuses.
- Identify overdue, due-today, and blocked tasks.
- Use available team information to interpret task ownership and responsibilities.

### Calendar
- View confirmed meetings, deadlines, and other events.
- Review extracted events before adding them to the calendar.
- Confirm suggested events, with the option to correct their details.
- Create, edit, and remove calendar events.

### Frontend Experience
- Dashboard, Meetings, Meeting Details, Tasks, Calendar, Team, and Chat pages.
- Assistant panel accessible from across the application.
- Search, notifications, and a command palette (`Ctrl + K`).
- Responsive navigation, including bottom navigation on mobile.
- Theme preferences with system, light, and dark modes.

## Technology Stack

| Component | Technologies |
|---|---|
| Frontend | React, Vite, JavaScript, CSS |
| Backend | Python, FastAPI |
| Workflow orchestration | LangGraph |
| LLM providers | Ollama, Groq |
| Embeddings | Ollama or configured fallback |
| Database | SQLite |
| Document processing | TXT, PDF, DOCX |
| Retrieval | Hybrid search and vector retrieval |

## Getting Started

MeetWise consists of two independently run services: the backend API and the frontend development server. Start the backend before launching the frontend.

### Prerequisites

- Python 3.10 or later
- Node.js and npm
- An LLM provider configured for the backend:
  - **Ollama** running locally, or
  - **Groq** with a valid API key.

For semantic retrieval, configure an embedding provider as described in the backend documentation. When using Groq for chat, embeddings must be provided separately because Groq does not provide an embeddings endpoint.

### 1. Backend Setup

Open a terminal and navigate to the `backend/` directory.

Create an environment file using the example configuration:

```bash
cp .env.example .env
```

Configure the required provider settings and credentials in `.env`.

Create and activate a virtual environment:

**Linux / macOS**
```bash
python -m venv .venv
source .venv/bin/activate
```

**Windows**
```powershell
python -m venv .venv
.venv\Scripts\activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

Start the backend:

```bash
uvicorn meetwise.api.main:app --reload
```

The backend API will be available at:

```text
http://localhost:8000
```

### 2. Frontend Setup

Open another terminal and navigate to the `frontend/` directory.

Install the dependencies:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

The frontend will be available at:

```text
http://localhost:5173
```

During development, requests to `/api` are proxied to the backend at `http://localhost:8000`.

### 3. Production Build

To create a production frontend build, run the following from the `frontend/` directory:

```bash
npm run build
```

The generated static files will be placed in `dist/`. Serve this directory behind the same origin as the backend API, with `/api` requests routed to the backend.

## Configuration

Backend configuration is managed through environment variables in `backend/.env`.

Important settings include:

| Variable | Purpose |
|---|---|
| `MEETWISE_LLM_PROVIDER` | Selects the chat provider (`ollama` or `groq`). |
| `MEETWISE_EMBEDDING_PROVIDER` | Selects the embedding provider. |
| `OLLAMA_BASE_URL` | Ollama server address. |
| `MEETWISE_OLLAMA_CHAT_MODEL` | Ollama chat model. |
| `MEETWISE_OLLAMA_EMBED_MODEL` | Ollama embedding model. |
| `GROQ_API_KEY` | API key when using Groq. |
| `MEETWISE_GROQ_CHAT_MODEL` | Groq chat model. |
| `MEETWISE_DB_PATH` | SQLite database location. |

Refer to `backend/.env.example` and the backend README for the complete configuration options and defaults.

## Important Notes

- **Event confirmation:** Extracted calendar events remain suggestions until explicitly confirmed. Reprocessing a meeting does not overwrite confirmed events.
- **Evidence-based answers:** Assistant responses include citations to the source meeting or task. Answers are checked against retrieved evidence, and the assistant may indicate when sufficient evidence is unavailable.
- **Task deadlines:** Task deadlines are resolved against the meeting date when possible. The frontend displays the resolved date when available, otherwise retaining the wording from the transcript.
- **Notifications:** Notifications are derived in the browser from task states and pending calendar events, and refresh periodically.
- **Calendar scope:** Calendar events are stored locally in the application's SQLite database. External calendar synchronization is not currently included.
- **Destructive actions:** Actions such as removing team members or dismissing events require confirmation.

## Project Documentation

For more detailed implementation and configuration information, refer to the individual documentation files:

- `backend/README.md` — Backend setup, API workflows, LangGraph processing, retrieval, verification, and configuration.
- `frontend/README.md` — Frontend setup, application structure, design system, and backend integration.