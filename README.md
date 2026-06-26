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

## Current State

This repo starts with a working product skeleton and a deterministic query engine for the core demo prompts. Once the Neon credentials are added, schema discovery can confirm actual table/column names and the SQL templates can be adapted to the real synthetic dataset.

## Push To Your Git Repo

1. Create an empty repo on GitHub.

2. Confirm secrets are not staged:

   ```bash
   git status --short
   ```

   You should not see `backend/.env` or `frontend/.env`.

3. Commit the project:

   ```bash
   git add .
   git commit -m "Initial Issa Insight app"
   ```

4. Connect your remote and push:

   ```bash
   git branch -M main
   git remote add origin git@github.com:YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```

Use the HTTPS remote instead if you prefer:

```bash
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
```

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
