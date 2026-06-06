# KOSPI Investor Flow Intelligence Platform

Tracks KOSPI investor-flow behavior (개인 / 기관 / 외국인 net buying) by stock,
with actual foreign holdings where available, plus screeners, historical
analytics, and ML projections.

> **Phases 1–5 MVP code-complete** (89 tests passing): data schema + ingestion +
> validation (P1); FastAPI service with stock pages, market views, and screeners
> (P2); correlation + event-study analytics (P3); walk-forward ML training +
> projections (P4); and production hardening (P5) — daily orchestrator + retry,
> KST job scheduler, alerting (console/file/webhook), model registry + PSI drift
> monitoring, user watchlists, CORS/Docker, and security/licensing review docs.
> A Next.js + ECharts frontend under `apps/web` (build-verified) provides the
> market overview, stock-detail charts, screener, models, and data-status pages.
> See
> [`kospi_investor_flow_project_context.md`](kospi_investor_flow_project_context.md)
> for the full plan, roadmap, and per-phase progress log.

## Important product constraint

개인/기관 cumulative net buy is **not** actual holdings. Only **foreign**
holdings are treated as real holdings, and only when sourced from verified
foreign-ownership data. Use the labels `개인 순매수`, `기관 순매수`,
`외국인 순매수`, `외국인 보유량`, `외국인 보유비율`, and label cumulative
개인/기관 series as `누적 순매수 기준 포지션 프록시`.

## Repository layout

```text
kospi_flow/            Python package (the suggested packages/* live here)
  core/                config, db engine/session, ORM models, enums, logging
  data/                provider abstraction, ingestion, validation
    providers/         sample (offline), pykrx (prototype), licensed (stub)
  analytics/           features, screener, market aggregates, labels,
                       correlation, event study, similar cases
  ml/                  dataset, walk-forward, models, metrics, training,
                       inference, registry, drift (PSI)
  alerts/              notifier (console/file/webhook) + rule engine
  api/                 FastAPI app, routers, envelope, deps, schemas
  jobs/                daily pipeline orchestrator + KST scheduler (P5)
apps/api/main.py       runnable uvicorn entrypoint
apps/web/              minimal Next.js frontend (scaffold)
infra/migrations       Alembic migrations + reference SQL DDL
infra/docker           Dockerfile + docker-compose (+ healthcheck)
infra/cron             sample crontab for the KST timetable
data/raw, data/processed   raw data + model artifacts (gitignored)
scripts/               thin CLI wrappers
tests/                 pytest suite (89 tests)
notebooks/, docs/      analysis + SECURITY/DATA_LICENSING/SCHEDULING docs
```

## Setup

Requires Python 3.11+.

```bash
python -m pip install -e .          # core dependencies
python -m pip install -e ".[dev]"   # + pytest
python -m pip install -e ".[pykrx]" # optional: real prototype data source
```

Copy `.env.example` to `.env` to override defaults (data source, database URL,
storage paths, timezone). All variables use the `KOSPI_` prefix. The default
data source is the **offline `sample` provider**, so everything below runs with
no network access or credentials.

## Initialize the database and run a sample ingestion

```bash
# 1. Inspect effective configuration
python -m kospi_flow.cli info

# 2. Create the schema (SQLite by default, at data/kospi_flow.db)
python -m kospi_flow.cli init-db

# 3. Ingest ~3 months of sample data for the default universe
python -m kospi_flow.cli ingest --start 2021-01-01 --end 2021-03-31

#    ...or a single ticker:
python -m kospi_flow.cli ingest --start 2021-01-01 --end 2021-03-31 --tickers 005930

# 4. Compute features into fact_features_daily
python -m kospi_flow.cli features

# 5. Validate (missing rows, duplicates, coverage gaps, freshness)
python -m kospi_flow.cli validate
```

Equivalent thin wrappers exist under `scripts/` (e.g.
`python scripts/run_ingestion.py --start 2021-01-01 --end 2021-03-31`).

## Train models and run the API (Phases 2–5)

```bash
# Train an ML model (walk-forward) and store predictions
python -m kospi_flow.cli train --horizon 5
python -m kospi_flow.cli predict --horizon 5

# Or run the whole daily pipeline at once (ingest→features→predict→validate)
python -m kospi_flow.cli daily --start 2021-01-01 --end 2023-12-31 --train

# Serve the API
uvicorn apps.api.main:app --port 8000   # docs at http://127.0.0.1:8000/docs
```

Key endpoints (all wrapped in a `{data, metadata}` envelope):
`GET /health`, `/metadata/data-freshness`, `/data-status`, `/stocks`,
`/stocks/{ticker}`, `/stocks/{ticker}/{price,investor-flows,foreign-holdings,features,correlations,events,flow-return-profile,projection}`,
`/market/{overview,index,top-picks,closes,top-net-buy,investor-flows}`, `/watchlists` (+ items/flows),
`/models` (+ `/{name}/drift`), and
`POST /screeners/{investor-flow,streaks,foreign-institution-co-buy}`.

### Operations (Phase 5)

```bash
python -m kospi_flow.cli drift --horizon 5      # compute + store PSI feature drift
python -m kospi_flow.cli models                 # list registered models + metrics
python -m kospi_flow.cli scheduler              # blocking KST job scheduler (§5 timetable)
python scripts/retrain.py                       # retrain all horizons + stage models/ for commit
```

The `daily` pipeline runs ingest → features → predict → drift → validate →
alerts, with retries and per-step error capture. When feature drift hits the PSI
alert band (or a bundle exceeds `KOSPI_MAX_MODEL_AGE_DAYS`) it emits a
`RETRAIN_RECOMMENDED` alert; retrain on the data host with `scripts/retrain.py`
then commit + push (see [`docs/RETRAIN.md`](docs/RETRAIN.md)). Alerts dispatch
through a configurable notifier (`KOSPI_ALERT_CHANNEL` = none|console|file|webhook).
See
[`docs/SCHEDULING.md`](docs/SCHEDULING.md), [`docs/SECURITY.md`](docs/SECURITY.md),
and [`docs/DATA_LICENSING.md`](docs/DATA_LICENSING.md). A sample crontab is at
`infra/cron/kospi-flow.cron`.

### Frontend

A Next.js + ECharts app lives in `apps/web` (build-verified; see its README):
market overview with the benchmark index chart, a stock-detail page
(candlestick+volume+MA, investor-flow bars/cumulative, foreign-holding dual-axis,
ML projection), plus screener, rankings, models, and data-status pages.

```bash
cd apps/web
cp .env.local.example .env.local     # set NEXT_PUBLIC_API_BASE (default 127.0.0.1:8000)
npm install
npm run dev                          # http://localhost:3000  (API must be serving)
```

### Docker

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

### Cloud deploy (Vercel + Render + Postgres)

Split deployment — Vercel hosts the **frontend only**; the FastAPI backend +
Postgres go on Render (blueprint at `render.yaml`), and pykrx ingestion stays on
a Korean-IP host writing to the hosted Postgres. Full runbook:
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). Push local data up with
`python -m kospi_flow.cli copy-db --dest postgresql://…`.

### Migrations (Alembic)

`init-db` creates tables directly from the ORM models — convenient for local
work. For shared/Postgres deployments use Alembic instead:

```bash
alembic -c infra/migrations/alembic.ini upgrade head
# future schema changes:
alembic -c infra/migrations/alembic.ini revision --autogenerate -m "describe change"
```

To target PostgreSQL/TimescaleDB, set
`KOSPI_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/kospi_flow`.

## Data sources

| Source     | Name       | Use                                            |
|------------|------------|------------------------------------------------|
| Sample     | `sample`   | Offline, deterministic synthetic data. Default. Never present to users as real data. |
| pykrx      | `pykrx`    | Real KOSPI data, **prototype only** (licensing unresolved). Needs network + `pip install pykrx`. |
| Licensed   | `licensed` | Production stub — implement once a source/license is finalised. |

Switch with `KOSPI_DATA_SOURCE=<name>` or `--source <name>`. All providers
implement `kospi_flow.data.providers.base.MarketDataProvider`, so the pipeline
is source-agnostic.

**Loading real data:** KRX IP-blocks most endpoints (flows/cap/foreign/index)
outside Korea — from a Korean-IP host, `pykrx` works with no API key. See
[`docs/REAL_DATA.md`](docs/REAL_DATA.md) for the step-by-step runbook. Use the
restartable, paced backfill for wide multi-year loads:

```bash
python -m kospi_flow.cli backfill --start 2019-01-01 --end 2024-12-31   # all KOSPI
```

`KOSPI_PYKRX_REQUEST_DELAY` paces KRX calls to avoid rate-limit empties; the
backfill upserts on the primary key so it is idempotent/resumable.

## Tests

```bash
python -m pytest
```

Tests cover config defaults/overrides, schema (tables, primary keys,
ORM/Alembic parity), feature math, end-to-end ingestion (incl. idempotency),
and validation behavior. They use an in-memory SQLite database and the sample
provider, so they need no external services.

## Core schema

Six logical tables (see context doc §7 and
`infra/migrations/sql/0001_initial_schema_reference.sql`):
`dim_stock`, `fact_price_daily`, `fact_investor_flow_daily`,
`fact_foreign_holding_daily`, `fact_features_daily`, `fact_ml_prediction_daily`.

Every fact row carries `source` and `freshness_state`
(`PRELIMINARY` / `FIRST_EOD` / `FINAL_EOD` / `RECONCILED` / `ERROR`) plus audit
timestamps.
