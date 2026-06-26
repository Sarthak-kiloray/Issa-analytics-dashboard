# Deployment Guide

Recommended setup for the demo:

- Backend API: Render Web Service
- Frontend app: Vercel Static/Vite app
- Database: existing Neon read-only Postgres

This keeps the API and UI separately deployable while using the same repo.

## 1. Push To GitHub

Create an empty GitHub repo, then from this folder:

```bash
git add .
git commit -m "Build Issa Insight analytics app"
git branch -M main
git remote add origin git@github.com:YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

Use an HTTPS remote if your machine is not set up for SSH:

```bash
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
```

Before pushing, confirm secret files are not staged:

```bash
git status --short
```

You should not see `backend/.env`, `backend/.env.example`, or `frontend/.env`.

## 2. Deploy Backend On Render

Create a new **Web Service** on Render from the GitHub repo.

Settings:

- Root directory: `backend`
- Runtime: Python 3
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

If Render is building from the repository root and shows `No such file or directory: requirements.txt`, either set **Root Directory** to `backend` or use these root-level commands instead:

- Build command: `cd backend && pip install -r requirements.txt`
- Start command: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Environment variables:

```text
ISSA_DATABASE_URL=postgresql://...
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.5
APP_ENV=production
ALLOWED_ORIGINS=https://issaanalyticsdashboard.vercel.app
```

After deployment, verify:

```text
https://YOUR_BACKEND_DOMAIN.onrender.com/health
```

It should return:

```json
{"status":"ok"}
```

## 3. Deploy Frontend On Vercel

Create a new Vercel project from the same GitHub repo.

Settings:

- Framework preset: Vite
- Root directory: `frontend`
- Build command: `npm run build`
- Output directory: `dist`

Environment variable:

```text
VITE_API_BASE_URL=https://YOUR_BACKEND_DOMAIN.onrender.com
```

Deploy. Then copy the Vercel URL and update the Render backend `ALLOWED_ORIGINS` value to exactly that frontend URL.

## 4. Smoke Test

On the deployed frontend:

1. Open the Schema page and confirm `conversations` and `messages` appear.
2. Open Anomaly Radar and Client Risk Queue.
3. Ask: `Show me new client conversations started each month this year`.
4. Click one recommended action and confirm it runs a follow-up query.

## 5. Submission Links

Include:

- GitHub repo URL
- Vercel frontend URL
- Render backend health URL
- Loom walkthrough URL
