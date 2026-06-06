"""Command-line job runner for Phase 1 data operations.

Usage examples (run from the repository root)::

    python -m kospi_flow.cli init-db
    python -m kospi_flow.cli ingest --start 2021-01-01 --end 2021-03-31
    python -m kospi_flow.cli features
    python -m kospi_flow.cli validate
    python -m kospi_flow.cli info

The default data source is the offline ``sample`` provider; override with the
``KOSPI_DATA_SOURCE`` environment variable or ``--source``.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from kospi_flow.analytics.pipeline import generate_features
from kospi_flow.core.config import get_settings
from kospi_flow.core.db import get_database
from kospi_flow.core.enums import FreshnessState
from kospi_flow.core.logging import get_logger
from kospi_flow.data.ingestion import build_ingestor
from kospi_flow.data.providers import available_providers
from kospi_flow.data.validation import DataValidator

logger = get_logger("kospi_flow.cli")


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _settings_with_overrides(args) -> object:
    settings = get_settings()
    if getattr(args, "source", None):
        settings.data_source = args.source
    if getattr(args, "database_url", None):
        settings.database_url = args.database_url
    return settings


def cmd_init_db(args) -> int:
    settings = _settings_with_overrides(args)
    db = get_database(settings)
    db.create_all()
    logger.info("Initialised database at %s", settings.database_url)
    return 0


def cmd_ingest(args) -> int:
    settings = _settings_with_overrides(args)
    db = get_database(settings)
    db.create_all()  # ensure schema exists for first run
    ingestor = build_ingestor(
        settings=settings,
        database=db,
        freshness_state=FreshnessState(args.freshness),
    )
    tickers = args.tickers.split(",") if args.tickers else None
    result = ingestor.run(
        start=args.start,
        end=args.end,
        tickers=tickers,
        include_foreign=not args.no_foreign,
        include_index=not args.no_index,
    )
    print(result.summary())
    return 0


def cmd_backfill(args) -> int:
    settings = _settings_with_overrides(args)
    db = get_database(settings)
    db.create_all()
    ingestor = build_ingestor(
        settings=settings,
        database=db,
        freshness_state=FreshnessState(args.freshness),
    )
    tickers = args.tickers.split(",") if args.tickers else None
    result = ingestor.backfill(
        start=args.start,
        end=args.end,
        tickers=tickers,
        include_foreign=not args.no_foreign,
        include_index=not args.no_index,
        restart=args.restart,
    )
    print(result.summary())
    return 0


def cmd_features(args) -> int:
    settings = _settings_with_overrides(args)
    db = get_database(settings)
    tickers = args.tickers.split(",") if args.tickers else None
    written = generate_features(db, tickers=tickers)
    print(f"feature_rows={written}")
    return 0


def cmd_train(args) -> int:
    from kospi_flow.ml.train import train_and_evaluate

    settings = _settings_with_overrides(args)
    db = get_database(settings)
    tickers = args.tickers.split(",") if args.tickers else None
    report = train_and_evaluate(
        db,
        horizon=args.horizon,
        tickers=tickers,
        n_splits=args.splits,
        model_name=args.model_name,
        model_version=args.model_version,
        settings=settings,
    )
    import json

    print(json.dumps(report.as_dict(), indent=2, default=str))
    return 0


def cmd_retrain(args) -> int:
    from kospi_flow.jobs.retrain import retrain_all

    settings = _settings_with_overrides(args)
    db = get_database(settings)
    horizons = (
        [int(h) for h in args.horizons.split(",") if h.strip()]
        if args.horizons
        else list(settings.predict_horizon_list)
    )
    tickers = args.tickers.split(",") if args.tickers else None
    result = retrain_all(
        horizons,
        tickers=tickers,
        model_version=args.model_version,
        n_splits=args.splits,
        sync=not args.no_sync,
        database=db,
        settings=settings,
    )

    import json

    print(
        json.dumps(
            {
                "model_version": result.model_version,
                "horizons": [r.horizon for r in result.reports],
                "mean_ic": {r.horizon: r.mean_ic for r in result.reports},
                "synced": result.synced,
                "models_dir": result.models_dir,
            },
            indent=2,
            default=str,
        )
    )
    if not args.no_sync:
        print(
            "\nNext: review models/, then commit + push so Railway redeploys:\n"
            f"  git add models/\n"
            f"  git commit -m \"Retrain models {result.model_version}\"\n"
            f"  git push"
        )
    return 0


def cmd_predict(args) -> int:
    from kospi_flow.ml.inference import predict_and_store

    settings = _settings_with_overrides(args)
    db = get_database(settings)
    tickers = args.tickers.split(",") if args.tickers else None
    model_name = args.model_name or f"gbm_return_{args.horizon}d"
    count = predict_and_store(db, model_name, tickers=tickers, settings=settings)
    print(f"predictions_stored={count}")
    return 0


def cmd_daily(args) -> int:
    from kospi_flow.jobs.daily import run_daily_pipeline

    settings = _settings_with_overrides(args)
    db = get_database(settings)
    tickers = args.tickers.split(",") if args.tickers else None
    horizons = tuple(int(h) for h in str(args.horizons).split(","))
    report = run_daily_pipeline(
        start=args.start,
        end=args.end,
        tickers=tickers,
        horizons=horizons,
        train=args.train,
        database=db,
        settings=settings,
    )
    import json

    print(json.dumps(report.as_dict(), indent=2))
    return 0 if report.ok else 1


def cmd_drift(args) -> int:
    from kospi_flow.ml.drift import compute_drift
    from kospi_flow.ml.inference import load_bundle

    settings = _settings_with_overrides(args)
    db = get_database(settings)
    model_name = args.model_name or f"gbm_return_{args.horizon}d"
    bundle = load_bundle(model_name, settings)
    summary = compute_drift(db, bundle, window=args.window, settings=settings)
    import json

    print(json.dumps(summary, indent=2, default=str))
    return 0


def cmd_models(args) -> int:
    from kospi_flow.ml.registry import list_models

    settings = _settings_with_overrides(args)
    db = get_database(settings)
    with db.session() as s:
        rows = list_models(s)
    for r in rows:
        flag = "*" if r.is_active else " "
        ic = f"{r.mean_ic:.3f}" if r.mean_ic is not None else "n/a"
        print(f"{flag} {r.model_name} {r.model_version} h={r.horizon_days} "
              f"backend={r.backend} IC={ic} n={r.n_samples}")
    if not rows:
        print("(no models registered)")
    return 0


def cmd_scheduler(args) -> int:
    from kospi_flow.jobs.scheduler import DEFAULT_SCHEDULE, serve

    settings = _settings_with_overrides(args)
    print("Scheduled jobs (KST):")
    for e in DEFAULT_SCHEDULE:
        print(f"  {e.time_kst}  {e.job:12s} {e.description}")
    print("Starting scheduler loop (Ctrl-C to stop)...")
    serve(settings=settings)
    return 0


def resolve_port(raw: str | None) -> int:
    """Resolve the serve port robustly.

    Accepts a literal port ("8080"), nothing (None), or an un-expanded shell
    placeholder like "$PORT"/"${PORT}" (which happens when a platform runs the
    start command without a shell). In the latter two cases we read the ``PORT``
    environment variable, falling back to 8000.
    """
    import os

    if raw and str(raw).isdigit():
        return int(raw)
    env = os.environ.get("PORT", "")
    return int(env) if env.isdigit() else 8000


def cmd_serve(args) -> int:
    try:
        import uvicorn
    except ImportError:
        print(
            "uvicorn is not installed. Run:\n"
            '  python -m pip install "uvicorn[standard]" fastapi'
        )
        return 1
    port = resolve_port(args.port)
    print(f"Serving API on http://{args.host}:{port}  (docs at /docs)")
    uvicorn.run("apps.api.main:app", host=args.host, port=port, reload=args.reload)
    return 0


def cmd_copy_db(args) -> int:
    from kospi_flow.jobs.migrate import copy_database

    settings = _settings_with_overrides(args)
    source = args.source or settings.database_url
    counts = copy_database(source, args.dest, batch=args.batch)
    import json

    print(json.dumps(counts, indent=2))
    return 0


def cmd_validate(args) -> int:
    settings = _settings_with_overrides(args)
    db = get_database(settings)
    report = DataValidator(db).validate()
    print(report.summary())
    for issue in report.issues:
        print(f"  [{issue.severity}] {issue.check}: {issue.message}")
    return 0 if report.ok else 1


def cmd_info(args) -> int:
    settings = get_settings()
    print(f"data_source        : {settings.data_source}")
    print(f"available providers: {available_providers()}")
    print(f"database_url       : {settings.database_url}")
    print(f"raw_data_path      : {settings.raw_data_path}")
    print(f"processed_data_path: {settings.processed_data_path}")
    print(f"timezone           : {settings.timezone}")
    print(f"market             : {settings.market}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kospi_flow.cli",
        description="KOSPI Investor Flow - data + ML job runner",
    )
    parser.add_argument(
        "--source", help="Override data source (e.g. sample, pykrx, licensed)"
    )
    parser.add_argument("--database-url", help="Override the SQLAlchemy database URL")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-db", help="Create all tables")
    p_init.set_defaults(func=cmd_init_db)

    p_ing = sub.add_parser("ingest", help="Ingest universe + facts for a date range")
    p_ing.add_argument("--start", type=_parse_date, required=True, help="YYYY-MM-DD")
    p_ing.add_argument("--end", type=_parse_date, required=True, help="YYYY-MM-DD")
    p_ing.add_argument("--tickers", help="Comma-separated tickers (default: all)")
    p_ing.add_argument(
        "--freshness",
        default=FreshnessState.FINAL_EOD.value,
        choices=[s.value for s in FreshnessState],
        help="Freshness state to stamp on ingested rows",
    )
    p_ing.add_argument(
        "--no-foreign", action="store_true", help="Skip foreign-holding ingestion"
    )
    p_ing.add_argument(
        "--no-index", action="store_true", help="Skip benchmark-index ingestion"
    )
    p_ing.set_defaults(func=cmd_ingest)

    p_bf = sub.add_parser(
        "backfill",
        help="Resumable real-data load: re-run the same command to continue "
        "where it left off (skips tickers already done for the date range)",
    )
    p_bf.add_argument("--start", type=_parse_date, required=True, help="YYYY-MM-DD")
    p_bf.add_argument("--end", type=_parse_date, required=True, help="YYYY-MM-DD")
    p_bf.add_argument("--tickers", help="Comma-separated tickers (default: all)")
    p_bf.add_argument(
        "--restart",
        action="store_true",
        help="Clear saved progress for this date range and start over",
    )
    p_bf.add_argument(
        "--freshness",
        default=FreshnessState.FINAL_EOD.value,
        choices=[s.value for s in FreshnessState],
        help="Freshness state to stamp on ingested rows",
    )
    p_bf.add_argument("--no-foreign", action="store_true", help="Skip foreign holdings")
    p_bf.add_argument("--no-index", action="store_true", help="Skip benchmark index")
    p_bf.set_defaults(func=cmd_backfill)

    p_feat = sub.add_parser("features", help="Compute and store features")
    p_feat.add_argument("--tickers", help="Comma-separated tickers (default: all)")
    p_feat.set_defaults(func=cmd_features)

    p_train = sub.add_parser("train", help="Train + walk-forward evaluate an ML model")
    p_train.add_argument("--horizon", type=int, default=5, help="Forward horizon (days)")
    p_train.add_argument("--splits", type=int, default=3, help="Walk-forward folds")
    p_train.add_argument("--tickers", help="Comma-separated tickers (default: all)")
    p_train.add_argument("--model-name", help="Override model name")
    p_train.add_argument(
        "--model-version",
        help="Version label (default: date stamp vYYYYMMDD; a distinct value "
        "per retrain keeps the registry + metrics history instead of overwriting)",
    )
    p_train.set_defaults(func=cmd_train)

    p_retrain = sub.add_parser(
        "retrain",
        help="Train all horizons + stage bundles under models/ for commit (KR host)",
    )
    p_retrain.add_argument(
        "--horizons", help="Comma-separated (default: KOSPI_PREDICT_HORIZONS)"
    )
    p_retrain.add_argument("--tickers", help="Comma-separated tickers (default: all)")
    p_retrain.add_argument(
        "--model-version", help="Version label (default: date stamp vYYYYMMDD)"
    )
    p_retrain.add_argument("--splits", type=int, default=3, help="Walk-forward folds")
    p_retrain.add_argument(
        "--no-sync",
        action="store_true",
        help="Train only; do not copy bundles into models/",
    )
    p_retrain.set_defaults(func=cmd_retrain)

    p_pred = sub.add_parser("predict", help="Generate + store ML predictions")
    p_pred.add_argument("--horizon", type=int, default=5, help="Model horizon (days)")
    p_pred.add_argument("--tickers", help="Comma-separated tickers (default: all)")
    p_pred.add_argument("--model-name", help="Override model name")
    p_pred.set_defaults(func=cmd_predict)

    p_daily = sub.add_parser(
        "daily", help="Run the full daily pipeline (ingest->features->predict->validate)"
    )
    p_daily.add_argument("--start", type=_parse_date, required=True, help="YYYY-MM-DD")
    p_daily.add_argument("--end", type=_parse_date, required=True, help="YYYY-MM-DD")
    p_daily.add_argument("--tickers", help="Comma-separated tickers (default: all)")
    p_daily.add_argument("--horizons", default="5", help="Comma-separated horizons")
    p_daily.add_argument(
        "--train", action="store_true", help="Retrain models before inference"
    )
    p_daily.set_defaults(func=cmd_daily)

    p_drift = sub.add_parser("drift", help="Compute + store model feature drift (PSI)")
    p_drift.add_argument("--horizon", type=int, default=5, help="Model horizon (days)")
    p_drift.add_argument("--model-name", help="Override model name")
    p_drift.add_argument("--window", type=int, default=20, help="Recent days to score")
    p_drift.set_defaults(func=cmd_drift)

    p_models = sub.add_parser("models", help="List registered models + metrics")
    p_models.set_defaults(func=cmd_models)

    p_sched = sub.add_parser(
        "scheduler", help="Run the blocking KST job scheduler (context doc S5)"
    )
    p_sched.set_defaults(func=cmd_scheduler)

    p_serve = sub.add_parser("serve", help="Run the FastAPI server (uvicorn)")
    p_serve.add_argument("--host", default="127.0.0.1", help="Bind host (0.0.0.0 to deploy)")
    p_serve.add_argument(
        "--port",
        type=str,
        default=None,
        help="Bind port (default: $PORT env or 8000; tolerates a literal $PORT)",
    )
    p_serve.add_argument(
        "--reload", action="store_true", help="Auto-reload on code changes (dev)"
    )
    p_serve.set_defaults(func=cmd_serve)

    p_copy = sub.add_parser(
        "copy-db", help="Copy all data to another DB (e.g. SQLite → Postgres)"
    )
    p_copy.add_argument("--dest", required=True, help="Destination SQLAlchemy URL")
    p_copy.add_argument("--source", help="Source URL (default: KOSPI_DATABASE_URL)")
    p_copy.add_argument("--batch", type=int, default=5000, help="Insert batch size")
    p_copy.set_defaults(func=cmd_copy_db)

    p_val = sub.add_parser("validate", help="Run data validation checks")
    p_val.set_defaults(func=cmd_validate)

    p_info = sub.add_parser("info", help="Print effective configuration")
    p_info.set_defaults(func=cmd_info)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
