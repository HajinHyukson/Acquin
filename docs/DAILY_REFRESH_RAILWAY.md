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

## STEP 0 (gating) — verify KRX is reachable from Railway's IP

pykrx/KRX commonly blocks **datacenter** IPs even when a residential connection
works. Railway containers run in a datacenter, so confirm reachability **before**
relying on the scheduler. Investor-flow / foreign-holding endpoints are the ones
that get blocked; plain price (OHLCV) is reachable almost everywhere, so the test
must check `flow_rows`/`foreign_rows`, not `price_rows`.

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
   ```
   `${{Postgres.DATABASE_URL}}` is the **internal** reference — fast, private, and
   no public proxy needed because the scheduler runs inside the same Railway
   project as the database. (`core/db.normalize_db_url` rewrites the `postgres://`
   DSN to `postgresql+psycopg://` automatically.)
4. Deploy. With STEP 0 cleared, the CMD runs `scheduler` and the service stays up,
   firing the daily jobs at the KST times above.

---

## STEP 2 — the model bundle (so the predict step works)

`ingest` and `features` write to Postgres with no extra setup. The **predict**
step needs a trained model bundle at `/app/data/processed/models/<model>.joblib`
(`kospi_flow/ml/inference.py:load_bundle`). A fresh container has none, so until a
bundle is present the daily pipeline's `predict`/`drift` steps log an error and
skip — **ingest/features still succeed** (per-step error capture in
`jobs/daily.py`), so the data refresh is unaffected.

Because the full history now lives in Railway Postgres, the self-contained option
is to **train on Railway** onto a persistent Volume:

1. Service → **Volumes** → attach a volume mounted at `/app/data/processed`
   (so `/app/data/processed/models/*.joblib` survives restarts/redeploys).
2. One-time bootstrap — temporarily set the Custom Start Command to train, deploy
   once, then clear it:
   ```
   python -m kospi_flow.cli train --horizon 5
   ```
   (`lightgbm` is in this image, so it is auto-selected, matching the host models.)
3. After the volume holds a bundle, the daily `predict` step works. Retrain
   periodically (e.g. weekly) by re-running the bootstrap command, or run a
   separate weekly Railway cron service with `daily --train`.

Alternative (no volume): commit an exported active bundle from your host into the
repo so it is baked into the image. Simpler to start, but couples deploys to a
binary artifact and to whoever trained it. The Volume + train-on-Railway path is
preferred now that the data lives in Postgres.

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
