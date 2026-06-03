# Daily data refresh on Railway (scheduler service) — Option A

Goal: update the **Railway Postgres** every day automatically, without populating
or storing the database on a local computer.

Approach: add a **second Railway service** (alongside the API service) that runs
the built-in always-on scheduler:

```
python -m kospi_flow.cli scheduler
```

The scheduler runs the KST timetable from context-doc §5 — preliminary (15:50),
first-EOD (16:30), and final-EOD + ML inference (18:30) — and **computes the
trading date itself** from `KOSPI_TIMEZONE` (`Asia/Seoul`), so it needs no
per-day date arguments. Every run ingests a rolling window straight into
Postgres; there is no local DB and no `copy-db` step.

This service uses its own image, `infra/docker/Dockerfile.scheduler`, which adds
the real-data + ML extras (`pykrx`, `lightgbm`) that the slim read-only API
image deliberately omits. The live API service is unchanged.

---

## Prerequisite — KRX login credentials (KRX_ID / KRX_PW)

pykrx (>=1.2.x) **auto-logs into the KRX data portal** using the `KRX_ID` /
`KRX_PW` environment variables (`pykrx/website/comm/auth.py`). These are **plain**
env vars (not `KOSPI_`-prefixed). **Without them**, the investor-flow / foreign /
market-cap / index / ticker-list endpoints all return empty — only Naver-backed
OHLCV works — and pykrx prints `KRX 로그인 실패: KRX_ID 또는 KRX_PW ...`. Register a
free account at <https://data.krx.co.kr> and set both vars wherever pykrx runs
(locally for testing, and on the Railway service). pykrx re-logins automatically
on session expiry, so a long-running scheduler is fine.

> Confirm the creds first by running the probe **locally** with `KRX_ID`/`KRX_PW`
> set; only once flows return locally is it worth testing Railway.

## STEP 0 (gating) — verify KRX is reachable from Railway's IP

Even with valid credentials, KRX sometimes blocks **datacenter** IPs that work
fine from a residential connection. Railway containers run in a datacenter, so
confirm reachability **before** relying on the scheduler. Set `KRX_ID`/`KRX_PW` on
the service first (STEP 1), then probe. The test must check `flow_rows`/
`foreign_rows`, not `price_rows` (prices work even unauthenticated/blocked).

1. Create the scheduler service (see STEP 1) but **temporarily** set its start
   command (Railway → service → Settings → Deploy → Custom Start Command) to a
   one-shot probe (use a recent trading day):

   ```
   python -m kospi_flow.cli ingest --start 2026-06-02 --end 2026-06-02 --tickers 005930 --no-index
   ```

2. Deploy and read the logs. The last line is the ingestion summary:
   - **`flow_rows>0` and `foreign_rows>0`** → KRX works from Railway. Proceed with
     Option A: clear the Custom Start Command so the image CMD (`scheduler`) runs.
   - **`flow_rows=0` / `foreign_rows=0`** (only `price_rows>0`) → Railway's IP is
     blocked. Option A won't get real flows. Fall back to **Option B** (run the
     same scheduler on a host whose IP is known to reach KRX — e.g. the machine
     where pykrx already works — pointed at Railway's *public* Postgres URL).

Do not skip this step; everything below assumes the probe returned flows.

---

## STEP 1 — create the scheduler service

In the Railway project that already hosts the API + Postgres:

1. **New → GitHub Repo → `HajinHyukson/Acquin`** (same repo as the API service).
2. Service → **Settings → Config-as-code** → set the config file path to:
   ```
   infra/railway/scheduler.json
   ```
   This builds `infra/docker/Dockerfile.scheduler` and disables the healthcheck
   (the scheduler has no HTTP port).
3. Set environment variables (Service → **Variables**):
   ```
   KOSPI_DATABASE_URL = ${{Postgres.DATABASE_URL}}   # internal URL (same project)
   KOSPI_DATA_SOURCE  = pykrx
   KOSPI_TIMEZONE     = Asia/Seoul
   KRX_ID             = <your KRX data-portal id>     # plain name, NOT KOSPI_-prefixed
   KRX_PW             = <your KRX data-portal password>
   ```
   Railway encrypts variable values. `KRX_ID`/`KRX_PW` authorize the pykrx data
   endpoints (see Prerequisite above).
   `${{Postgres.DATABASE_URL}}` is the **internal** reference — fast, private, and
   no public proxy needed because the scheduler runs inside the same Railway
   project as the database. (`core/db.normalize_db_url` rewrites the `postgres://`
   DSN to `postgresql+psycopg://` automatically.)
4. Deploy. With STEP 0 cleared, the CMD runs `scheduler` and the service stays up,
   firing the daily jobs at the KST times above.

---

## STEP 2 — the model bundle (predictions)

The **predict** step loads a trained bundle at
`/app/data/processed/models/<model>.joblib` (`kospi_flow/ml/inference.py:load_bundle`).

**Chosen approach: bundles are committed and baked into the image.** The five
LightGBM bundles (`gbm_return_{1,3,5,10,20}d.joblib`, trained on this machine) live
in the repo under `models/` and `Dockerfile.scheduler` copies them to
`/app/data/processed/models/`. So predictions work on first deploy — no Volume,
no train-on-Railway needed.

The scheduler refreshes **all five horizons daily** (the set the frontend's Top
Picks dropdown surfaces), controlled by `KOSPI_PREDICT_HORIZONS`
(default `1,3,5,10,20`; one bundle must exist per listed horizon).

> **Do not mount a Railway Volume at `/app/data/processed`** — it would shadow the
> baked-in `models/` directory and hide the bundles.

To **refresh the models** later: retrain on this machine
(`python -m kospi_flow.cli train --horizon <h>` against the local DB), copy the
new `.joblib`s into `models/`, commit, and redeploy. (The model itself only needs
periodic retraining; daily `predict` just re-scores the latest features.)

---

## Notes

- **Re-ingest window:** the scheduler ingests a rolling 120-day window each run
  (idempotent upsert on primary key — `run_entry(lookback_days=120)`), so a late
  correction within ~4 months is picked up. To cut KRX calls, run fewer entries
  (the timetable is `DEFAULT_SCHEDULE` in `kospi_flow/jobs/scheduler.py`).
- **No local footprint:** the scheduler writes facts/features/predictions to
  Postgres; the only local writes are tiny per-run raw Parquet snapshots under
  `/app/data/raw` (filenames carry no date, so they overwrite — they do not grow).
- **Billing:** an always-on Railway service is usage-billed continuously. If that
  matters, prefer a once-daily Railway **cron** service over the always-on loop
  (cron needs explicit `--start/--end`; the always-on `scheduler` does not).
