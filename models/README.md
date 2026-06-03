# Shipped model bundles

LightGBM model bundles served by the Railway **scheduler** service.
`infra/docker/Dockerfile.scheduler` copies this directory to
`/app/data/processed/models/`, which is where `kospi_flow/ml/inference.load_bundle`
reads `<model_name>.joblib` from.

| File | Horizon | Used by |
|---|---|---|
| `gbm_return_1d.joblib` | 1 day | daily `predict` + frontend Top Picks |
| `gbm_return_3d.joblib` | 3 days | " |
| `gbm_return_5d.joblib` | 5 days | " (default horizon) |
| `gbm_return_10d.joblib` | 10 days | " |
| `gbm_return_20d.joblib` | 20 days | " |

Each bundle is a dict (regressor / classifier / P10-P50-P90 quantile models,
`feature_cols`, `feature_baseline` for drift, `model_version`, `feature_version`).

## Refreshing

These are trained on the local machine against the real-data DB. To refresh:

```bash
python -m kospi_flow.cli train --horizon 5   # repeat per horizon
cp data/processed/models/gbm_return_*.joblib models/
git add models/ && git commit && git push     # redeploy the scheduler service
```

Note: the daily scheduler re-scores the latest features every day with these
bundles; the bundles themselves only need periodic retraining.
