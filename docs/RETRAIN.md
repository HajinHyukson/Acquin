# Retraining the models (KR host → commit → Railway redeploy)

This is the **human/CI half** of the retrain loop. The production daily pipeline
only *recommends* a retrain (a `RETRAIN_RECOMMENDED` alert when feature drift hits
the PSI alert band or a model passes `KOSPI_MAX_MODEL_AGE_DAYS`); it does **not**
retrain in prod, because Railway bakes the bundles into the image and its
filesystem is ephemeral. The actual retrain runs **here**, on a host with the real
KOSPI data, and ships new bundles by committing and pushing them.

> Decided 2026-06-06: retrain locally on the KR host (not a GitHub Action reading
> Railway Postgres). See context doc §25 Phase D.

## When to retrain

- A `RETRAIN_RECOMMENDED` / `MODEL_DRIFT_ALERT` alert fired (feature drift), **or**
- on a slow calendar cadence (≈ monthly), **or**
- after a data/feature change.

Do **not** retrain daily — a day adds ~0.08% of rows, so the refit is essentially
identical, and daily retraining defeats drift monitoring (§11.8).

## Prerequisites (KR host)

- The real KOSPI data is loaded and current (see [`REAL_DATA.md`](REAL_DATA.md));
  point at it with `KOSPI_DATABASE_URL` / `KOSPI_DATA_SOURCE`, or run against the
  local SQLite you backfilled into.
- Install the ML extras: `python -m pip install -e ".[lightgbm]"` (and
  `".[postgres]"` if training against Postgres).

## One command

```bash
# Trains every horizon in KOSPI_PREDICT_HORIZONS (default 1,3,5,10,20) under one
# date-stamped version, then copies the bundles into models/ and appends a row
# per horizon to models/metrics_history.csv.
python scripts/retrain.py
```

Useful flags:

```bash
python scripts/retrain.py --horizons 5,20          # subset of horizons
python scripts/retrain.py --model-version v2026-06  # explicit version label
python scripts/retrain.py --model-version "v$(git rev-parse --short HEAD)"
python scripts/retrain.py --no-sync                 # train only; leave models/ untouched
```

The default version is a date stamp `vYYYYMMDD`, so each retrain registers a
distinct `ml_model_registry` row (the latest stays active) and appends a metrics
line instead of overwriting history (§24.3).

## Commit + push (Railway redeploys)

```bash
git add models/
git commit -m "Retrain models v2026-06-09"
git push
```

Railway rebuilds the scheduler/API image from the pushed commit, so the new
bundles are baked in and the daily `predict` step uses them.

### What gets committed

- `models/gbm_return_{1,3,5,10,20}d.joblib` — the **same 5 filenames overwritten**
  (≈4.9 MB each). Keep overwriting these — do not create versioned `*.joblib`
  copies in git; joblib compresses poorly and git keeps every blob forever
  (§24.3).
- `models/metrics_history.csv` — the durable, diff-friendly performance log
  (date, model_name, model_version, horizon, mean_ic, icir, directional_accuracy,
  auc, rmse, mae, n_samples, backend, trained_at). Tiny (~KB); keep all of it.

## Verify

- Check the printed `mean_ic` per horizon and the new `metrics_history.csv` row.
- After Railway redeploys, the API serves predictions from the new bundle; the
  `/models` endpoint lists the freshly registered versions.

## Tuning the training window (one-time, real data only)

Phase B added `KOSPI_TRAIN_WINDOW_DAYS` (trailing-window training; default = all
history). Pick a value once by comparing out-of-sample IC on real data:

```bash
python -m kospi_flow.cli train --horizon 5                     # all history
KOSPI_TRAIN_WINDOW_DAYS=504  python -m kospi_flow.cli train --horizon 5   # ~2y
KOSPI_TRAIN_WINDOW_DAYS=756  python -m kospi_flow.cli train --horizon 5   # ~3y
KOSPI_TRAIN_WINDOW_DAYS=1260 python -m kospi_flow.cli train --horizon 5   # ~5y
```

Set the winning value as `KOSPI_TRAIN_WINDOW_DAYS` for `retrain`, and record the
choice in the context doc decision log (§17).
