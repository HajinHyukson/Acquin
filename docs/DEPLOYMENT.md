# Deployment

**Important:** Vercel can host the **Next.js frontend only**. It cannot run this
Python/ML/pandas backend or hold the ~2 GB database (Vercel serverless functions
are size- and time-limited and have an ephemeral, read-only filesystem; SQLite
won't persist there). So this is a **split deployment**:

```
  Browser ──▶ Vercel (Next.js frontend, apps/web)
                  │  calls NEXT_PUBLIC_API_BASE
                  ▼
            FastAPI backend  ──▶  managed Postgres
            (Render/Railway/Fly)        ▲
                                        │ data load / daily updates
            Korean-IP host (pykrx) ─────┘   (writes straight to prod, or copy-db)
```

- **Frontend** → Vercel.
- **Backend API** → a container/Python host (Render shown here; Railway/Fly equivalent).
- **Database** → managed Postgres (Render/Neon/Supabase).
- **Data ingestion** → still runs on your **Korean-IP host** (pykrx needs a KR IP),
  writing to the hosted Postgres.

---

## 1. Backend + database (Render)

A blueprint is included at `render.yaml` (web service + free Postgres).

1. Push the repo to GitHub.
2. Render → **New → Blueprint** → select the repo. It creates `kospi-flow-api`
   (build `pip install -e ".[postgres]"`, start `… cli serve --host 0.0.0.0 --port $PORT`)
   and `kospi-flow-db`, wiring `KOSPI_DATABASE_URL` automatically.
3. Wait for the first deploy, note the URL, e.g. `https://kospi-flow-api.onrender.com`.
   Check `…/health` and `…/docs`.

Platform Postgres URLs come as `postgres://…`; the app auto-rewrites them to the
psycopg3 dialect, so no manual change is needed.

> Render's **free Postgres is ~1 GB** — smaller than the full ~2 GB universe.
> For the full dataset use a larger plan, or **Neon/Supabase** (set
> `KOSPI_DATABASE_URL` to their connection string), or load a **curated subset**
> of tickers.

## 2. Load data into the hosted Postgres

The DB starts empty. Two options, both from your **Korean-IP host**:

**A. Push your local SQLite up (one-time):**
```powershell
python -m pip install -e ".[postgres]"
python -m kospi_flow.cli copy-db --source "sqlite:///./data/kospi_flow.db" `
  --dest "postgresql://USER:PASS@HOST:5432/kospi_flow"
```
(Use Render's *External* connection string. The schema is created automatically.)

**B. Ingest straight to prod (recommended for ongoing updates):** on the KR host,
point the pipeline at the hosted DB and run it there:
```powershell
$env:KOSPI_DATA_SOURCE = "pykrx"
$env:KOSPI_DATABASE_URL = "postgresql://USER:PASS@HOST:5432/kospi_flow"
python -m kospi_flow.cli daily --start 2026-05-01 --end 2026-06-02 --train
# or: python -m kospi_flow.cli scheduler   (daily EOD, KST)
```
This is how you keep prod current going forward — the KR host ingests/retrains
directly into the hosted Postgres; the API/Vercel just read it.

## 3. Frontend (Vercel)

1. Vercel → **New Project** → import the repo.
2. **Root Directory = `apps/web`** (monorepo — important).
3. Framework auto-detects Next.js. Add an env var:
   - `NEXT_PUBLIC_API_BASE = https://kospi-flow-api.onrender.com`
4. Deploy → note the domain, e.g. `https://kospi-flow.vercel.app`.

## 4. Wire CORS (so the browser can call the API)

On Render, set `KOSPI_CORS_ORIGINS` to your Vercel domain and redeploy:
```
KOSPI_CORS_ORIGINS = https://kospi-flow.vercel.app
```
(Server-rendered pages don't need this, but client widgets — top picks, event
study, watchlists, sparklines — fetch from the browser and do.)

---

## What you need to do (summary)
1. Create a GitHub repo and push this project.
2. Render: deploy the blueprint → get the **API URL**; pick a Postgres plan that
   fits your data (or Neon/Supabase for the full set).
3. From your **KR host**, load data into the hosted Postgres (`copy-db`, or
   ingest directly via option B).
4. Vercel: import repo, **Root Directory `apps/web`**, set `NEXT_PUBLIC_API_BASE`
   to the API URL → deploy.
5. Set `KOSPI_CORS_ORIGINS` on the API to your Vercel domain.

After that, nothing runs on your computer except the **periodic KR-IP ingestion**
(which can also move to a small Korean VPS / cron).

## Notes & limits
- **Auth:** the API is currently unauthenticated (MVP). Before exposing publicly,
  add auth + rate limiting (see `docs/SECURITY.md`) — anyone with the API URL can
  read/modify watchlists.
- **Free tiers sleep:** Render free web services idle after inactivity (cold
  start on first request). Fine for personal use; upgrade for always-on.
- **Licensing:** pykrx data is prototype-only for redistribution — see
  `docs/DATA_LICENSING.md` before making this public/commercial.
