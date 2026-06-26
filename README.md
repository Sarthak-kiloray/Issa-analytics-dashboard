# Issa Insight

A natural-language analytics workspace for Issa's client conversation data. The app is built as a FastAPI backend plus a Vite React frontend, with Postgres schema introspection, guarded read-only SQL execution, and an investigation-oriented UI for business questions.

## Stack

- Backend: FastAPI, Psycopg, Pydantic Settings
- Frontend: Vite, React, plain CSS, Recharts
- Database: read-only Neon Postgres via `ISSA_DATABASE_URL`
- AI: optional OpenAI integration via `OPENAI_API_KEY`

## What Makes It Different

- **Two-pass LLM workflow:** the model first creates a schema-aware SQL plan, then the backend runs read-only SQL, then the model synthesizes a diagnosis from actual query results.
- **Business investigation mode:** open-ended prompts are decomposed into multiple evidence queries instead of one shallow chart.
- **Follow-up memory:** the app sends recent compact Q/A context so prompts like "break that down by channel" resolve correctly.
- **Actionable recommendations:** recommended actions are clickable and launch the next investigation.
- **Proactive intelligence:** Anomaly Radar and Client Risk Queue surface operational issues before users know what to ask.
- **Transparent evidence:** every answer includes SQL, evidence notes, caveats, confidence, charts, and tables.

## Process

I approached the project as an internal analytics product rather than a generic text-to-SQL demo.

1. **Schema first:** I started by inspecting the available Postgres tables and mapping the business meaning of the important fields: conversation start time, client/contact identity, channel, assignee, lifecycle/current step, message direction, AI flags, and operational status flags.
2. **Core query loop:** I built a backend flow that turns a natural-language question into a schema-aware SQL plan, validates and executes read-only SQL, then synthesizes a plain-English answer from the returned rows.
3. **Investigation layer:** I added playbooks for broad business questions like new-client decline, team demand, churn risk, and unusual patterns so the app can decompose ambiguous questions into multiple supporting signals.
4. **Product polish:** I added follow-up memory, clickable recommended actions, confidence/caveats, saved investigations, transparent SQL evidence, interactive charts, and separate pages for proactive operational workflows.
5. **Deployment readiness:** I separated local secrets from committed templates and documented a production deployment path for Render + Vercel.

## Architecture Decisions

- **FastAPI backend instead of putting database access in the frontend:** SQL generation, validation, execution, and secrets stay server-side.
- **React + Vite frontend:** a lightweight client app was enough for the dashboard experience without adding Next.js complexity.
- **Read-only Postgres access:** the app is designed for analytics and investigation, so the database connection is intentionally read-only.
- **Two LLM calls per normal answer:** the first call plans SQL; the second call explains actual query results. This keeps the diagnosis grounded in data instead of letting the model answer from intuition.
- **Deterministic proactive intelligence:** Anomaly Radar and Client Risk Queue are SQL/rule based, not LLM guesses. They can be trusted as operational monitors and then handed off to the LLM workflow for deeper analysis.
- **Frontend chart intelligence:** Recharts keeps visualizations interactive. The frontend detects grouped result shapes and renders multi-series bars/lines instead of depending on static server-generated chart images.
- **Transparent evidence model:** every answer exposes SQL, evidence notes, caveats, confidence, and recommended actions so internal users can inspect how the answer was produced.

## Time Spent

I spent approximately **8-10 focused hours** building the current version: initial product plan, backend query engine, OpenAI integration, live schema adaptation, proactive intelligence pages, frontend UI, chart improvements, documentation, and deployment preparation.

## Local Setup

### Folder Structure

The browser app sidebar is product navigation, not your code file tree. The project files live here:

```text
Issa/
  backend/
    app/
      routers/
      services/
    requirements.txt
    .env.template
  frontend/
    src/
      styles/
    package.json
    .env.example
  Makefile
  README.md
```

### Connect Neon

1. Copy environment files. These local `.env` files are ignored by git:

   ```bash
   cp backend/.env.template backend/.env
   cp frontend/.env.example frontend/.env
   ```

2. Add the Neon read-only connection string to `backend/.env`. Do not paste the password into source code:

   ```bash
   ISSA_DATABASE_URL="postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require"
   ```

3. Start the backend and frontend in two terminals:

   ```bash
   make backend
   make frontend
   ```

4. Confirm the backend can see the database:

   ```bash
   make schema
   ```

Manual setup is also fine:

   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

## Architecture

The backend keeps database access and query safety server-side. The frontend sends natural-language prompts to `/api/query`, then renders the returned answer blocks as KPI cards, charts, tables, diagnosis text, recommended actions, and SQL/evidence panels.

Normal LLM-powered request lifecycle:

1. Frontend sends the user question plus the last few compact history items.
2. Backend loads live Postgres schema context.
3. LLM call #1 returns a JSON query plan with SQL and visualization types.
4. Backend validates and executes read-only SQL against Neon.
5. LLM call #2 receives the plan plus compact query results and returns diagnosis, confidence, caveats, and recommended actions.
6. Frontend renders the answer and lets users continue via follow-up memory or action buttons.

Important backend modules:

- `app/services/db.py`: database connection handling
- `app/services/schema.py`: Postgres schema discovery
- `app/services/sql_guard.py`: read-only SQL validation
- `app/services/query_engine.py`: prompt routing, query planning, execution, and response shaping
- `app/services/intelligence.py`: deterministic Anomaly Radar and Client Risk Queue checks

## Current Schema Assumption

The first live SQL templates are mapped to the schema visible in DBeaver:

- `conversations`: contact profile, assignee, channel, lifecycle/current step, qualification flags, message counts, timestamps
- `messages`: contact-level message events, direction, sender, AI flags, delivery status, timestamps

The app currently derives:

- monthly conversation starts from `conversations.conversation_opened_at` or `conversations.created_at`
- team response time from first incoming `messages` to first later outgoing `messages`
- inactive clients from latest `messages.created_at` or conversation update time
- channel mix from `conversations.channel_name` / `conversations.channel_source`
- backlog from active, unblocked, not-handed-off conversations grouped by assignee

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md).

Recommended demo deployment:

- Backend: Render Web Service from `backend/`
- Frontend: Vercel Vite app from `frontend/`
- Database: existing Neon read-only Postgres

Required production environment variables:

Backend:

```text
ISSA_DATABASE_URL=postgresql://...
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.5
APP_ENV=production
ALLOWED_ORIGINS=https://YOUR_FRONTEND_DOMAIN.vercel.app
```

Frontend:

```text
VITE_API_BASE_URL=https://YOUR_BACKEND_DOMAIN.onrender.com
```
