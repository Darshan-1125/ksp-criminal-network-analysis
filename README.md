# Karnataka Crime GPT (KSP) 🛡️

**AI-Powered Criminal Network Analysis & Trend Intelligence Dashboard**

Karnataka Crime GPT is an enterprise-grade conversational intelligence platform built for law enforcement agencies, crime analysts, and policy researchers. It combines a **FastAPI** backend, **PostgreSQL with pgvector**, a **LangGraph-based multi-agent routing pipeline**, and an interactive **React + Vite** frontend.

---

## 🌟 Key Features

* 💬 **Conversational AI & Multi-Agent Router**: Query Karnataka synthetic crime data using natural language (supports English and Kannada via text or browser voice input).
* 🕸️ **Accomplice Network Analysis**: View interactive, force-directed network graphs linking accused individuals, accomplices, modus operandi, and crime locations.
* 📊 **Crime Trends & Analytics**: Aggregate crime data by district, crime type, or month with real-time interactive bar and line charts.
* 🧠 **Session Memory & Entity Resolution**: Automatically resolves pronouns (*"his other Murder cases"*) and direct numeric accused IDs (*"Accused ID 72"* or *"Accused #32"*).
* 🔒 **Role-Based Access Control (RBAC)**: Enforces role-based permissions (`admin`, `supervisor`, `investigator`, `analyst`, `policymaker`, `read_only`) with automated redaction logic for sensitive personal information.
* 🗑️ **Session Deletion & Audit Logging**: Session deletion endpoints scoped via JWT authentication with full law enforcement compliance audit logs (`DELETE_SESSION`).
* 🎛️ **Draggable Resizable Panels**: Custom split-view layout with draggable resize divider, min/max panel width constraints, and `localStorage` preference persistence.
* 📄 **High-Contrast PDF Export**: Export full chat transcripts to structured, high-contrast PDF documents with WinAnsi encoding protection for emojis.

---

## 🏗️ System Architecture

```mermaid
graph TD
    Client[React + Vite Frontend] -->|REST API + JWT Auth| FastAPI[FastAPI Backend Server]
    
    subgraph FastAPI Backend
        Router[LangGraph Query Router]
        Auth[RBAC Auth & Audit Logging]
        RAG[RAG Synthesis Engine]
    end
    
    Router -->|Structured Search| DB[(PostgreSQL Database)]
    Router -->|Vector Search| PGVector[(pgvector Embeddings)]
    Router -->|Entity Network| Graph[Accomplice Network Builder]
    
    RAG -->|GPT-4o / LangChain| Client
```

---

## 🚀 Quick Start Guide

### Prerequisites

Ensure you have the following installed on your system:
- **Python 3.10+** (Python 3.13 recommended)
- **Node.js 18+** & **npm**
- **PostgreSQL** with the `pgvector` extension enabled

---

### 1. Backend Setup

1. **Navigate to the backend directory**:
   ```bash
   cd backend
   ```

2. **Create and activate a Python virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**:
   Create or verify `.env` inside `backend/`:
   ```env
   DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ksp_crime
   OPENAI_API_KEY=your_openai_api_key_here
   SECRET_KEY=ksp_jwt_secret_key_change_in_production_2026
   ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=480
   ```

5. **Initialize and Seed the Database**:
   Seed PostgreSQL with 500+ realistic synthetic Karnataka crime records and pre-seeded user accounts:
   ```bash
   python -m app.data.seed
   python -m app.data.seed_users
   ```

6. **Start the FastAPI Server**:
   ```bash
   uvicorn app.main:app --reload
   ```
   The backend server runs at `http://127.0.0.1:8000`.

---

### 2. Frontend Setup

1. **Navigate to the frontend directory**:
   ```bash
   cd ../frontend
   ```

2. **Install Node.js dependencies**:
   ```bash
   npm install
   ```

3. **Start the Development Server**:
   ```bash
   npm run dev
   ```
   Open your browser at `http://localhost:5173`.

---

## 🔐 Seeded Test Credentials

| Username | Password | Role | Permissions & Access Scope |
| :--- | :--- | :--- | :--- |
| `admin1` | `admin_pass123` | `admin` | Full system access, reindexing, audit logs viewer |
| `supervisor1` | `supervisor_pass123` | `supervisor` | Audit log access, full network graphs & trends |
| `investigator1` | `investigator_pass123` | `investigator` | Full case details, suspect network graphs |
| `analyst1` | `analyst_pass123` | `analyst` | Trend analysis & network graph view |
| `policymaker1` | `policymaker_pass123` | `policymaker` | Redacted PII, macro-level crime trends |
| `readonly1` | `readonly_pass123` | `read_only` | General query & case search access |

---

## 📡 API Endpoints Summary

### Authentication & Audit
* `POST /api/auth/login` — Authenticate and receive JWT access and refresh tokens.
* `GET /api/auth/me` — Retrieve current authenticated user profile.
* `GET /api/audit-logs` — Admin/Supervisor audit log viewer.

### Conversational Chat & Sessions
* `POST /api/chat/session` — Initialize a new chat session.
* `GET /api/chat/sessions` — List user's chat sessions.
* `POST /api/chat` — Send query message and receive RAG answer, citations, and visualization payload.
* `GET /api/chat/sessions/{session_id}/messages` — Fetch chat history for session.
* `DELETE /api/chat/sessions/{session_id}` — Delete a session (verifies JWT user ownership & logs audit entry).

### Intelligence & Data
* `GET /api/cases` — Filterable structured case listing with pagination.
* `GET /api/cases/{fir_id}` — Detailed FIR case card.
* `GET /api/network/{entity_type}/{entity_id}` — Fetch node and edge network graph for accused or location.
* `GET /api/trends` — Aggregate crime trend statistics.

---

## 🧪 Automated Testing

### Backend Test Suite
Execute the pytest suite covering query routing, pronoun resolution, pagination, and session deletion:
```bash
cd backend
./venv/bin/python -m pytest tests/test_session_deletion.py tests/test_pagination.py
```

### Frontend Build Verification
Verify production compilation:
```bash
cd frontend
npm run build
```

---

## 📂 Project Structure

```
ksp-criminal-network-analysis/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI application entrypoint
│   │   ├── db.py                    # Database connection & SessionLocal
│   │   ├── models.py                # SQLAlchemy ORM schemas
│   │   ├── routers/                 # API endpoint routers (chat, cases, network, trends, auth)
│   │   ├── services/                # LangGraph router, RAG service, DB service
│   │   └── data/                    # Seed scripts for synthetic crime records & users
│   ├── tests/                       # Pytest automated test suite
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/              # ChatPanel, NetworkGraph, TrendChart, SessionHistory, etc.
│   │   ├── context/                 # AuthContext for authentication state
│   │   ├── App.jsx                  # Main dashboard split layout & resize handles
│   │   └── index.css                # Global design system & responsive styling
│   └── package.json
└── README.md
```