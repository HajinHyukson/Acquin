# Scheduling & Operations (Phase 5)

The daily EOD pipeline can be driven three ways. All run the same code path
(`kospi_flow.jobs.daily.run_daily_pipeline`).

## 1. Built-in scheduler (simplest)

```bash
python -m kospi_flow.cli scheduler
```

A blocking process that runs jobs at the Korea-time minutes defined in
`kospi_flow/jobs/scheduler.py::DEFAULT_SCHEDULE`:

| KST | Job | Freshness | Notes |
|---|---|---|---|
| 15:50 | preliminary | PRELIMINARY | OHLCV right after close |
| 16:30 | first_eod | FIRST_EOD | first-pass EOD |
| 18:30 | final_eod | FINAL_EOD | flows + features + ML inference + drift + alerts |

Run it as a container (`scheduler` service in `docker-compose.yml`, commented
out by default) or under systemd. Set the host/container `TZ=Asia/Seoul`.

## 2. Cron / cloud scheduler

Use `infra/cron/kospi-flow.cron` (KST). Good for managed cron or k8s CronJobs.

## 3. One-off / manual

```bash
python -m kospi_flow.cli daily --start 2024-01-01 --end 2024-12-31 --train
```

## Pipeline steps & failure handling

`run_daily_pipeline` runs: **ingest → features → predict (per horizon) → drift →
validate → alerts**. Each step is retried (default 3×) and records `ok|error`
with the error message; a failure in one step does not abort the others, so the
report shows exactly what broke. Alerts are dispatched via the configured
notifier (`KOSPI_ALERT_CHANNEL` = none|console|file|webhook).

## Monitoring

- `GET /data-status` — row counts + latest validation report.
- `GET /metadata/data-freshness` — latest date + freshness per table.
- `GET /models` and `GET /models/{name}/drift` — registry metrics + PSI drift.

## Production upgrade path

For backfills, dependency graphs, SLAs, and richer retries, migrate the job
definitions to **Airflow or Prefect** (context doc §6.1). The current scheduler
is intentionally dependency-free for the MVP.
