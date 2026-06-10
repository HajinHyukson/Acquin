# External model socket — pushing predictions from a separate model

The platform accepts predictions from models developed outside this repo (e.g.
an investor-sentiment crawler + ML) and shows them next to the internal
flow-based models: on the stock page (ML 예측 card, grouped per model), in
`/market/top-picks?model=<name>`, and — once outcomes mature — in the
stock-page **prediction-accuracy panel**, scored with exactly the same
hit-rate / band-coverage / IC machinery as the internal model.

## Contract

One HTTP call. The external model is responsible for its own features and
training; it only ships its *outputs*.

```
POST {API_BASE}/models/{model_name}/predictions
X-API-Key: <KOSPI_INGEST_API_KEY>
Content-Type: application/json
```

```json
{
  "model_version": "v1",
  "feature_version": "sentiment_v0",
  "predictions": [
    {
      "date": "2026-06-09",
      "ticker": "005930",
      "horizon_days": 5,
      "predicted_return": 0.012,
      "predicted_return_p10": -0.02,
      "predicted_return_p50": 0.01,
      "predicted_return_p90": 0.04,
      "prob_outperform_kospi": 0.61
    }
  ]
}
```

Semantics (must match the internal models so the comparisons are fair):

| Field | Meaning |
|---|---|
| `date` | The trading date the prediction was made **on** (using only data available by that date's close — no look-ahead). |
| `horizon_days` | Forward horizon in trading days. |
| `predicted_return` | Expected **log** return over the horizon: `log(P[t+h] / P[t])`. |
| `predicted_return_p10/p50/p90` | Optional uncertainty band (same log-return units). |
| `prob_outperform_kospi` | Optional, 0–1. |

Only `date`, `ticker`, `horizon_days`, `predicted_return` are required.
Re-posting the same `(date, ticker, horizon_days)` upserts (safe to retry).
Unknown tickers are skipped and reported in the response, not rejected.
Names starting with `gbm_` (internal trainer) or `wf::` (backtest rows) are
reserved and rejected.

## Enabling / auth

The endpoint is **disabled by default** (`403 INGEST_DISABLED`). Set
`KOSPI_INGEST_API_KEY=<secret>` on the API service (Railway → Variables) and
send the same value as `X-API-Key`. Keep the key out of the frontend — only
the external model's job needs it.

## Where the predictions surface

| Surface | Behavior |
|---|---|
| `GET /stocks/{t}/projection` | `data.models[]` contains one group per model (`source: internal\|external`); `?model=<name>` features that model in the back-compat `projections` key. The stock page renders each group. |
| `GET /market/top-picks` | Defaults to the internal family; `?model=<name>` ranks by the external model. |
| `GET /stocks/{t}/prediction-accuracy?model=<name>` | Scores the external model's matured predictions (and any `wf::<name>` backtest rows it pushed) against realized prices. |
| `GET /models` | Lists the model with `backend: "external"`. |

## Backfilling an accuracy record

To show up in the accuracy panel with history, push *historical* predictions
the same way — but they must be honest walk-forward outputs (each row computed
using only data up to its `date`). Push them under the same model name; rows
older than `today - horizon` are scored immediately.

## Internal walk-forward backtest (for comparison baselines)

The internal model's 5-year record is generated on the data host:

```bash
python -m kospi_flow.cli backtest --horizons 5          # the headline horizon
python -m kospi_flow.cli backtest --horizons 5,20 --splits 8
```

Rows are stored in `fact_ml_prediction_daily` under `wf::gbm_return_<h>d`
(excluded from all live endpoints; re-running replaces the previous run).
Footprint: roughly the OOS panel size per horizon (~hundreds of thousands of
rows for the full universe) — run it for the horizons the UI features rather
than all five if DB size matters.
