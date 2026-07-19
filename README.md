# Karnataka Crime GPT — Criminal Network & Trend Intelligence Dashboard

An AI-powered conversational platform designed for analyzing synthetic crime datasets from Karnataka. It uses a LangGraph-based multi-agent routing pipeline, PostgreSQL with pgvector for semantic search, and an interactive React frontend showcasing accomplice networks and crime trends.

---

## 🚀 Quick Start Guide

This project is organized as a monorepo containing a FastAPI backend and a Vite+React frontend.

### Prerequisites

Before setting up, ensure you have the following installed:
* **Python 3.10+**
* **Node.js 18+ & npm**
* **PostgreSQL** with the `pgvector` extension enabled

---

### 1. Backend Setup

1. **Navigate to the backend directory:**
   ```bash
   cd backend
   ```

2. **Create and activate a Python virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   Copy the example environment file and update it with your database connection details and OpenAI API key:
   ```bash
   cp .env.example .env
   ```
   Open `backend/.env` and update:
   * `DATABASE_URL`: Your PostgreSQL connection URI (e.g., `postgresql://postgres:password@localhost:5432/ksp_crime`)
   * `OPENAI_API_KEY`: Your OpenAI API key (required for LangGraph embeddings and RAG agent)

5. **Initialize and Seed the Database:**
   Ensure PostgreSQL is running and your database is created. Then, run the seed script to set up the schema and insert 500+ synthetic crime records:
   ```bash
   python -m app.data.seed
   ```

6. **Start the FastAPI server:**
   ```bash
   uvicorn app.main:app --reload
   ```
   The backend will be running on `http://127.0.0.1:8000`.

---

### 2. Frontend Setup

1. **Navigate to the frontend directory:**
   ```bash
   cd ../frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Start the React development server:**
   ```bash
   npm run dev
   ```
   The frontend application will be running on `http://localhost:5173` (or the port specified by Vite). Open this URL in your browser to interact with the dashboard.

---

## 🛠️ Main Features

* **Conversational AI Chat**: Query crime data using natural language (supports English and Kannada).
* **Multi-Agent Orchestration**: Powered by LangGraph to route queries (Structured Search, pgvector Semantic Search, Network Graphs, or Crime Trends).
* **Accomplice Network Analysis**: View interactive, force-directed graphs showing connections between criminals, locations, and cases.
* **Crime Analytics & Trends**: Visualize crime distribution and aggregates in clean, interactive charts.
* **Factual Citations**: The AI cites actual FIR numbers for every claim made. Click on citations to open detailed case cards.
* **PDF Export**: Generate and download professional PDF transcripts of chat history client-side.
* **Voice Search**: Hands-free queries using browser-native Speech-to-Text.

---

## 📋 Build Contract & Team Prompts

## 0. Repo structure (fixed — everyone follows this)

```
/backend
  /app
    main.py                 # FastAPI app entrypoint (Member 1)
    db.py                   # SQLAlchemy engine/session (Member 1)
    models.py               # ORM models matching schema below (Member 1)
    /routers
      cases.py               (Member 1)
      network.py              (Member 1)
      trends.py                (Member 1)
      chat.py                  (Member 2)
    /services
      db_service.py           (Member 1 — exposes functions Member 2 imports)
      rag_service.py           (Member 2)
      langgraph_router.py       (Member 2)
    /data
      seed.py                  (Member 1 — synthetic data generator)
  requirements.txt
  .env.example
/frontend
  (React + Vite app — Member 3, standard CRA/Vite structure)
README.md
```

Branch rule: each member works on `feature/backend-core`, `feature/ai-chat`, `feature/frontend-ui`. Merge to `main` at hour 4, 8, 12, 18, 24 (agree on these checkpoints as a team out loud — don't let integration wait until the end).

**Critical unblock step:** Member 1 must push `models.py`, `db.py`, and stub routers that return **hardcoded mock JSON matching the exact response shapes below** within the first 60–90 minutes. This lets Member 2 and Member 3 start immediately against a working contract instead of waiting for real logic.

---

## 1. Fixed PostgreSQL schema (do not deviate — all 3 modules depend on this)

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE districts (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL
);

CREATE TABLE police_stations (
  id SERIAL PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  district_id INTEGER REFERENCES districts(id)
);

CREATE TABLE locations (
  id SERIAL PRIMARY KEY,
  address TEXT,
  city VARCHAR(100),
  district_id INTEGER REFERENCES districts(id),
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION
);

CREATE TABLE accused (
  id SERIAL PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  age INTEGER,
  gender VARCHAR(20),
  phone VARCHAR(20),
  address TEXT,
  photo_url TEXT
);

CREATE TABLE victims (
  id SERIAL PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  age INTEGER,
  gender VARCHAR(20),
  phone VARCHAR(20),
  address TEXT
);

CREATE TABLE fir_cases (
  id SERIAL PRIMARY KEY,
  fir_number VARCHAR(50) UNIQUE NOT NULL,
  crime_type VARCHAR(100) NOT NULL,
  ipc_sections VARCHAR(200),
  district_id INTEGER REFERENCES districts(id),
  police_station_id INTEGER REFERENCES police_stations(id),
  location_id INTEGER REFERENCES locations(id),
  date_reported DATE NOT NULL,
  status VARCHAR(30) DEFAULT 'under_investigation',
  mo_description TEXT,
  narrative TEXT,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE case_accused (
  case_id INTEGER REFERENCES fir_cases(id),
  accused_id INTEGER REFERENCES accused(id),
  PRIMARY KEY (case_id, accused_id)
);

CREATE TABLE case_victims (
  case_id INTEGER REFERENCES fir_cases(id),
  victim_id INTEGER REFERENCES victims(id),
  PRIMARY KEY (case_id, victim_id)
);

CREATE TABLE case_embeddings (
  id SERIAL PRIMARY KEY,
  case_id INTEGER REFERENCES fir_cases(id) UNIQUE,
  content_text TEXT NOT NULL,
  embedding vector(1536)
);

CREATE TABLE chat_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE chat_messages (
  id SERIAL PRIMARY KEY,
  session_id UUID REFERENCES chat_sessions(id),
  role VARCHAR(20) NOT NULL,              -- 'user' | 'assistant'
  content TEXT NOT NULL,
  citations JSONB,
  visual_type VARCHAR(30),                -- 'network' | 'trend' | 'none'
  visual_payload JSONB,
  created_at TIMESTAMP DEFAULT now()
);
```

**Seed data note (Member 1):** generate 500–800 `fir_cases` with Faker + Karnataka district/station names, IPC/BNS sections. Deliberately embed: (a) 3–4 repeat offenders whose `accused_id` appears across multiple districts, (b) a small cluster of 5–6 accused sharing addresses/phone patterns (organized network), (c) 2 sets of cases with near-identical `narrative` text but different districts (for RAG similarity demo). This is what makes the network graph and semantic search demo look "discovered," not staged.

---

## 2. API contract (every route, every request/response shape)

### Owned by Member 1 (Backend/DB)

**GET /api/health**
→ `{ "status": "ok" }`

**GET /api/cases**
Query params: `crime_type`, `district`, `date_from`, `date_to`, `accused_name`, `limit` (default 20), `offset` (default 0)
→
```json
{
  "total": 42,
  "results": [
    {
      "id": 101,
      "fir_number": "KA-2024-1123",
      "crime_type": "Robbery",
      "ipc_sections": "392, 397",
      "district": "Mysuru",
      "police_station": "Devaraja PS",
      "date_reported": "2024-11-02",
      "status": "under_investigation",
      "mo_description": "Armed robbery, night, motorcycle escape",
      "accused": [{ "id": 55, "name": "Ravi K." }],
      "victims": [{ "id": 88, "name": "Suresh M." }],
      "location": { "address": "MG Road", "lat": 12.2958, "lng": 76.6394 }
    }
  ]
}
```

**GET /api/cases/{fir_id}**
→ same single object shape as above, plus `"narrative": "full text..."`

**GET /api/network/{entity_type}/{entity_id}**  (`entity_type` = `accused` | `location`)
→
```json
{
  "nodes": [
    { "id": "accused_55", "label": "Ravi K.", "type": "accused" },
    { "id": "case_101", "label": "KA-2024-1123", "type": "case" },
    { "id": "location_12", "label": "MG Road, Mysuru", "type": "location" }
  ],
  "edges": [
    { "source": "accused_55", "target": "case_101", "relation": "accused_in" },
    { "source": "case_101", "target": "location_12", "relation": "occurred_at" }
  ]
}
```

**GET /api/trends**
Query params: `group_by` (`district` | `crime_type` | `month`), optional `district`, `crime_type` filters
→
```json
{ "group_by": "district", "data": [{ "key": "Mysuru", "count": 42 }, { "key": "Bengaluru Urban", "count": 118 }] }
```

**Internal Python functions** in `app/services/db_service.py` — Member 2 imports these directly (same process, no HTTP hop):
- `search_cases_structured(filters: dict) -> list[dict]`
- `get_case_by_id(fir_id: str) -> dict`
- `get_network_for_entity(entity_type: str, entity_id: int) -> dict`
- `get_db_session()` — yields a SQLAlchemy session so Member 2 can query `case_embeddings` directly for pgvector similarity search

### Owned by Member 2 (AI/LangChain)

**POST /api/chat/session**
→ `{ "session_id": "uuid-string" }`

**POST /api/chat**
Request:
```json
{ "session_id": "uuid-string", "message": "Show me robbery cases in Mysuru similar to FIR KA-2024-1123", "language": "en" }
```
Response:
```json
{
  "session_id": "uuid-string",
  "answer": "I found 3 robbery cases in Mysuru matching the MO of KA-2024-1123...",
  "citations": [{ "fir_number": "KA-2024-1123", "snippet": "Armed robbery, night, motorcycle escape" }],
  "visual_type": "network",
  "visual_payload": { "nodes": [...], "edges": [...] }
}
```
`visual_type` is one of `"network" | "trend" | "none"`. `visual_payload` is `null` when `visual_type` is `"none"`, otherwise matches the exact shape of `/api/network` or `/api/trends` responses above — **this is what lets the frontend render the same graph/chart component regardless of whether data came from a direct API call or from chat.**

**GET /api/chat/history/{session_id}**
→
```json
{ "messages": [{ "role": "user", "content": "...", "created_at": "..." }, { "role": "assistant", "content": "...", "citations": [...], "visual_type": "network", "visual_payload": {...}, "created_at": "..." }] }
```

**POST /api/embeddings/reindex** (dev/admin only)
→ `{ "status": "ok", "count_indexed": 640 }`

Router logic Member 2 owns (LangGraph): classify each `message` into `structured | semantic | graph | hybrid`, call the matching path (`db_service.search_cases_structured`, pgvector similarity query, or `db_service.get_network_for_entity`), then synthesize via ChatGPT API with a system prompt that forces citation of `fir_number` for every factual claim and forbids inventing FIR numbers not present in retrieved context.

### Owned by Member 3 (Frontend) — no backend routes, consumes everything above

Client-side only, no backend call: PDF export of `chat_messages` history (jsPDF), voice input (Web Speech API → fills the chat text box).

---

## 3. Prompt for Member 1 — Backend/DB owner

```
You are building the Backend & Database module of "Karnataka Crime GPT" — a hackathon
project: a conversational AI over a synthetic Karnataka crime dataset with network
analysis. Tech stack: FastAPI, PostgreSQL + pgvector, SQLAlchemy. You are one of three
people pushing to the SAME github repo — a teammate is building the AI/LangChain chat
layer on top of your services, and another is building the React frontend against your
API. They will start building against your response shapes immediately, so get the
CONTRACT right before optimizing anything else.

YOUR SCOPE:
1. Create /backend/app/db.py — SQLAlchemy engine + session factory, reading DATABASE_URL
   from .env. Expose a get_db_session() dependency/generator.
2. Create /backend/app/models.py implementing this exact schema (do not rename fields,
   do not add/drop tables without flagging it to the team first):
   [paste the full SQL schema from section 1 of this doc]
3. Create /backend/app/data/seed.py — generate 500-800 synthetic FIR records using Faker,
   with realistic Karnataka district/police-station names and IPC/BNS sections. Deliberately
   embed: 3-4 repeat offenders appearing across multiple districts, a 5-6 person cluster
   sharing addresses/phone numbers (for network demo), and 2 pairs of cases with near-identical
   narrative text in different districts (for semantic search demo). Write narrative text
   for every case (2-4 sentences, templated is fine).
4. Implement these routes in /backend/app/routers/cases.py, network.py, trends.py:
   - GET /api/health -> {"status": "ok"}
   - GET /api/cases (params: crime_type, district, date_from, date_to, accused_name, limit, offset)
   - GET /api/cases/{fir_id}
   - GET /api/network/{entity_type}/{entity_id}   (entity_type = accused | location)
   - GET /api/trends (params: group_by = district|crime_type|month, optional filters)
   Match these EXACT response JSON shapes: [paste section 2 response examples for cases/network/trends]
5. Implement /backend/app/services/db_service.py exposing these functions as plain
   importable Python (NOT http endpoints — your teammate on the AI module imports these
   directly in the same FastAPI process):
   - search_cases_structured(filters: dict) -> list[dict]
   - get_case_by_id(fir_id: str) -> dict
   - get_network_for_entity(entity_type: str, entity_id: int) -> dict
   - get_db_session() -> yields a SQLAlchemy session
   Also add the `case_embeddings` table with a pgvector column (vector(1536)) so the AI
   module can write/query embeddings directly against it via get_db_session().
6. For network analysis: build edges from shared accused across cases, shared location,
   and shared address/phone between accused records. Use NetworkX server-side if you want
   centrality scores, but the /api/network response must always come back as flat
   {nodes: [...], edges: [...]} JSON regardless of what you compute internally.

GIT WORKFLOW:
- Work on branch feature/backend-core, push to shared repo.
- Within the FIRST 60-90 minutes, push models.py, db.py, and STUB routers that return
  hardcoded mock JSON matching the exact shapes above (even before real DB logic works) —
  your teammates are blocked on this and will build against it immediately.
- Merge to main at hour 4, 8, 12, 18, 24.
- Do not touch /frontend or app/routers/chat.py or app/services/rag_service.py —
  those belong to teammates.

DEFINITION OF DONE for hour 24: all 4 routes return real data from Postgres, seed script
runs cleanly from scratch, db_service functions are importable and tested standalone.
```

---

## 4. Prompt for Member 2 — AI/LangChain owner

```
You are building the Conversational AI module of "Karnataka Crime GPT" — a hackathon
project: a chatbot over a synthetic Karnataka crime dataset, using LangChain/LangGraph
and the ChatGPT API, grounded in real Postgres records with citations. You are one of
three people pushing to the SAME github repo. A teammate owns the Postgres schema and
exposes Python service functions you will import directly (same FastAPI process, no
HTTP hop needed). Another teammate builds the React frontend against your /api/chat
response shape — get that shape exactly right.

DEPENDENCY: you import from app/services/db_service.py (owned by your backend teammate):
   - search_cases_structured(filters: dict) -> list[dict]
   - get_case_by_id(fir_id: str) -> dict
   - get_network_for_entity(entity_type: str, entity_id: int) -> dict
   - get_db_session() -> SQLAlchemy session (use this to query the case_embeddings table
     directly for pgvector similarity search — schema: case_embeddings(id, case_id,
     content_text, embedding vector(1536)))
If these functions don't exist yet when you start, stub them yourself matching the exact
signatures above so you're not blocked, then swap to the real import once your teammate
pushes.

YOUR SCOPE:
1. Build a LangGraph router in app/services/langgraph_router.py that classifies each
   incoming chat message into one of: structured | semantic | graph | hybrid, using
   keyword/entity heuristics first (dates, "similar to", "connected to", district/crime-type
   names) — an LLM classification fallback is fine if heuristics are ambiguous.
   - structured -> call search_cases_structured(filters) with filters extracted from the message
   - semantic -> embed the query (OpenAI embeddings), pgvector cosine similarity search
     against case_embeddings, return top-k case_ids, then get_case_by_id for each
   - graph -> extract the entity name/id from the message, resolve it to an accused_id
     or location_id, call get_network_for_entity(entity_type, entity_id)
   - hybrid -> combine structured + semantic results before synthesis
2. Build app/services/rag_service.py: synthesize retrieved records into a natural-language
   answer via the ChatGPT API. System prompt MUST require every factual claim to cite a
   real fir_number from the retrieved context, and MUST forbid inventing FIR numbers not
   present in that context. If no relevant records are found, say so plainly instead of
   guessing.
3. Add conversation memory: store the last-mentioned fir_number/accused_id per session_id
   (in-memory dict is fine for a hackathon) so follow-up questions like "what about his
   other cases?" resolve without the user repeating context.
4. Implement these routes in app/routers/chat.py:
   - POST /api/chat/session -> {"session_id": "uuid-string"}
   - POST /api/chat  — request: {"session_id": str, "message": str, "language": "en"|"kn"}
     response: {"session_id": str, "answer": str, "citations": [{"fir_number": str,
     "snippet": str}], "visual_type": "network"|"trend"|"none", "visual_payload": <matches
     /api/network or /api/trends shape, or null>}
   - GET /api/chat/history/{session_id} -> {"messages": [...]} (persist to chat_sessions/
     chat_messages tables via db_service's session)
   - POST /api/embeddings/reindex -> {"status": "ok", "count_indexed": int} (loops all
     fir_cases, embeds narrative text, upserts into case_embeddings)
5. `visual_type` logic: if the answer involved a graph query -> "network", if it involved
   trend/aggregation -> "trend", otherwise -> "none". `visual_payload` must be null when
   visual_type is "none" — the frontend renders conditionally on this field.
6. Handle Groq/OpenAI rate limits gracefully — wrap LLM calls in try/except with a clear
   fallback message, never let a 429 crash the endpoint.

GIT WORKFLOW:
- Work on branch feature/ai-chat, push to shared repo.
- Pull your backend teammate's db_service.py stub/real version frequently — don't let your
  local copy drift from what's actually in main.
- Merge to main at hour 4, 8, 12, 18, 24.
- Do not touch app/routers/cases.py, network.py, trends.py, or /frontend.

DEFINITION OF DONE for hour 24: a multi-turn conversation works end-to-end, every answer
cites real fir_numbers pulled from Postgres, follow-up questions resolve using session
memory, and at least one query type reliably returns visual_type: "network" with a real
graph payload for the demo.
```

---

## 5. Prompt for Member 3 — Frontend owner

```
You are building the Frontend of "Karnataka Crime GPT" — a hackathon project: a chat
interface over a Karnataka crime database that also renders network graphs and trend
charts inline based on what was asked. Tech stack: React.js + Tailwind CSS. You are one
of three people pushing to the SAME github repo. Two teammates are building a FastAPI
backend — build against the exact contracts below; you can start immediately using mock
JSON matching these shapes even before their real endpoints are live, then swap the mock
for real fetch calls once they push.

BACKEND CONTRACT YOU CONSUME (base URL from VITE_API_BASE_URL env var):

POST /api/chat/session -> {"session_id": "uuid-string"}
  Call this once when the chat UI mounts (or on "new conversation").

POST /api/chat
  Request: {"session_id": string, "message": string, "language": "en"|"kn"}
  Response: {"session_id": string, "answer": string,
    "citations": [{"fir_number": string, "snippet": string}],
    "visual_type": "network"|"trend"|"none",
    "visual_payload": object|null}
  Render `answer` as the assistant chat bubble. Render `citations` as small clickable
  chips under the bubble (clicking one calls GET /api/cases/{fir_number} and opens a
  detail panel). If visual_type is "network", pass visual_payload into your NetworkGraph
  component. If "trend", pass it into your TrendChart component. If "none", show nothing
  extra.

GET /api/chat/history/{session_id} -> {"messages": [{"role": "user"|"assistant",
  "content": string, "citations": [...], "visual_type": string, "visual_payload": object|null,
  "created_at": string}]}
  Use this to rehydrate the chat panel on reload.

GET /api/cases/{fir_id} -> single case object:
  {"id": int, "fir_number": string, "crime_type": string, "ipc_sections": string,
   "district": string, "police_station": string, "date_reported": "YYYY-MM-DD",
   "status": string, "mo_description": string, "narrative": string,
   "accused": [{"id": int, "name": string}], "victims": [{"id": int, "name": string}],
   "location": {"address": string, "lat": number, "lng": number}}

GET /api/network/{entity_type}/{entity_id} -> {"nodes": [{"id": string, "label": string,
  "type": "accused"|"case"|"location"}], "edges": [{"source": string, "target": string,
  "relation": string}]}
  This is the SAME shape as visual_payload when visual_type is "network" — build ONE
  NetworkGraph component that accepts this shape regardless of source.

GET /api/trends?group_by=district|crime_type|month -> {"group_by": string,
  "data": [{"key": string, "count": number}]}
  Same rule — one TrendChart component consumes this shape whether it came from a direct
  call or from chat's visual_payload.

YOUR SCOPE:
1. Layout: chat panel (left, ~40% width) + dynamic visualization panel (right, ~60%) that
   swaps between NetworkGraph, TrendChart, or an empty state based on the last message's
   visual_type. Use react-force-graph or vis-network for NetworkGraph, recharts for
   TrendChart.
2. Chat panel: message list, input box, send button. Show a loading state while POST
   /api/chat is in flight. Show citation chips under assistant messages.
3. Case detail panel/modal: opens when a citation chip is clicked, fetches GET
   /api/cases/{fir_id}, shows all fields including narrative.
4. PDF export: client-side only, no backend call — use jsPDF to export the current chat
   history (loop over rendered messages) to a downloadable PDF.
5. Voice input: Web Speech API, browser-native — fills the chat input box with the
   transcribed text, user still presses send. No backend involvement.
6. Language toggle: simple English/Kannada switch for static UI labels; pass the selected
   language as the `language` field in every POST /api/chat request body.
7. Handle empty/error states gracefully: if visual_payload is null, don't render a broken
   graph/chart component — show a neutral placeholder instead. If /api/chat fails or times
   out, show a retry option, don't let the UI hang.

GIT WORKFLOW:
- Work on branch feature/frontend-ui, push to shared repo, entirely inside /frontend.
- Start against hardcoded mock JSON matching the shapes above if backend routes aren't
  live yet; swap to real fetch calls as your teammates push working endpoints — don't
  wait idle.
- Merge to main at hour 4, 8, 12, 18, 24.
- Do not touch /backend.

DEFINITION OF DONE for hour 24: full user journey works end-to-end against the real
backend — ask a question, see the answer with citations, see the graph or chart render,
click a citation to open case detail, export the conversation as PDF.
```

---

## 6. Integration checkpoints (do these live, as a team, not solo)

- **Hour 4:** Member 1's stub routes + schema are in `main`. Member 2 and 3 confirm they can build against the mock shapes.
- **Hour 8:** Member 1's real Postgres queries are live. Member 2 swaps stub `db_service` calls for real imports.
- **Hour 12:** Member 2's `/api/chat` returns real answers with citations (even if RAG/graph paths are partial). Member 3 wires the chat UI to it live, not against mocks.
- **Hour 18:** Full network + trend visual rendering confirmed end-to-end from a real chat query, not just from direct API calls.
- **Hour 22–24:** Freeze features. Run your 5–6 rehearsed demo queries against the fully merged `main` branch on the actual demo machine/network.