# Loading Real KOSPI Data via pykrx (Korean-IP host)

KRX rate-limits and IP-blocks most of its data endpoints (investor flows, market
cap, foreign holdings, index) for non-Korean / datacenter IPs. From a **Korean
IP** (a PC in Korea, a Korean VPS, or a VPN with a KR exit) the `pykrx` provider
can pull everything with **no API key**. This guide is the turnkey runbook.

> Licensing note: `pykrx` is acceptable for prototype/personal use only.
> Redistribution / commercial use needs a licensed feed — see
> [`DATA_LICENSING.md`](DATA_LICENSING.md).

## 1. Prerequisites

- A host with a Korean IP.
- Python 3.11+.
- Install with the pykrx extra:
  ```bash
  python -m pip install -e ".[pykrx]"
  ```

## 2. Configure

Copy `.env.example` → `.env` and set at least:

```bash
KOSPI_DATA_SOURCE=pykrx
# SQLite is fine to start; for a full universe + 5y, prefer PostgreSQL:
# KOSPI_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/kospi_flow
KOSPI_DATABASE_URL=sqlite:///./data/kospi_flow.db

# Pacing between KRX calls. 0.3s is a safe default; raise to 0.5–1.0 if you see
# "returned empty" warnings (that means KRX is throttling you).
KOSPI_PYKRX_REQUEST_DELAY=0.3
```

## 3. Smoke-test reachability FIRST

Confirm the blocked endpoints actually work from your IP before a long run:

```bash
python -m kospi_flow.cli init-db
# One ticker, a few weeks — should print non-zero flow_rows AND foreign_rows.
python -m kospi_flow.cli ingest --start 2024-01-02 --end 2024-01-31 --tickers 005930
```

Expected: `price_rows`, `flow_rows`, `foreign_rows`, and `index_rows` all > 0. If
`flow_rows=0`/`foreign_rows=0`, your IP is still blocked (not a KR IP, or KRX is
throttling) — raise `KOSPI_PYKRX_REQUEST_DELAY` and retry, or check the IP.

## 4. Full backfill (restartable, chunked)

`backfill` checkpoints progress **per ticker** keyed by the `(start, end)` date
range, so **re-running the exact same command picks up where it left off** —
already-loaded tickers are skipped and only the rest are fetched. This is the
intended workflow when a data session times out mid-run (e.g. the pykrx KRX
login expires after ~1 hour): re-authenticate / re-login and run the same
command again; it continues until the whole universe is loaded.

```bash
# Whole KOSPI universe (~950 tickers), ~6 years. Long-running — use tmux/screen.
# Use FIXED dates (not "today") so every re-run shares the same scope & resumes.
python -m kospi_flow.cli backfill --start 2019-01-01 --end 2026-06-01

# Re-run the SAME command after a timeout to continue:
python -m kospi_flow.cli backfill --start 2019-01-01 --end 2026-06-01

# Curated subset first (also resumable):
python -m kospi_flow.cli backfill --start 2019-01-01 --end 2026-06-01 \
    --tickers 005930,000660,373220,207940,005380
```

Notes:
- A ticker is marked **done** once it returns data and is skipped on later runs.
  A ticker that returns nothing (token expired, or genuinely no data) is retried
  on subsequent runs, then `skipped` after a few empty attempts.
- Each run logs `N/total already done, M pending`. When `M` reaches 0 (or only a
  few persistently-empty/dataless names remain), the load is complete.
- `--restart` clears saved progress for that date range and starts over.
- If you hit empties, raise `KOSPI_PYKRX_REQUEST_DELAY` (e.g. `0.6`) and re-run.
- Keep `--start`/`--end` identical across re-runs — a different range is a
  different scope and won't resume.

## 5. Build features, models, predictions

```bash
python -m kospi_flow.cli features
python -m kospi_flow.cli train --horizon 5      # now on REAL data
python -m kospi_flow.cli predict --horizon 5
python -m kospi_flow.cli drift  --horizon 5      # PSI now meaningful on a wide universe
python -m kospi_flow.cli validate
```

The benchmark automatically uses the **real KOSPI index** (code `1001`) once it
is ingested (`benchmark_source = index:1001` in `/market/overview`); otherwise it
falls back to the cap-weighted proxy.

## 6. Serve / schedule

```bash
uvicorn apps.api.main:app --port 8000
# Daily EOD automation (set host TZ=Asia/Seoul):
python -m kospi_flow.cli scheduler        # or use infra/cron/kospi-flow.cron
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `... returned empty (attempt n) — KRX may be rate-limiting` | Raise `KOSPI_PYKRX_REQUEST_DELAY`; re-run (idempotent). |
| `flow_rows=0`/`foreign_rows=0` but `price_rows>0` | IP is geo-blocked for those endpoints — verify you're on a KR IP. |
| Backfill interrupted | Just re-run the same `backfill` command; it resumes. |
| `trading_value` looks like close×volume | pykrx single-ticker OHLCV omits 거래대금; it is derived. Switch to a licensed feed for true turnover. |
