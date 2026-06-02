-- Reference DDL for the Phase 1 core schema (PostgreSQL flavour).
--
-- This file is REFERENCE ONLY. The authoritative schema lives in the ORM models
-- (kospi_flow/core/models.py) and is applied via Alembic
-- (infra/migrations/versions/0001_initial_baseline.py) or
-- `python -m kospi_flow.cli init-db`. Use this file to review the schema or to
-- bootstrap a PostgreSQL/TimescaleDB instance by hand.
--
-- For production on PostgreSQL, consider NUMERIC instead of DOUBLE PRECISION for
-- exact KRW amounts, and TimescaleDB hypertables on the fact_* tables.

CREATE TABLE IF NOT EXISTS dim_stock (
    ticker          VARCHAR(6) PRIMARY KEY,
    isin            VARCHAR(12),
    name_kr         TEXT,
    name_en         TEXT,
    market          TEXT NOT NULL DEFAULT 'KOSPI',
    sector          TEXT,
    listing_date    DATE,
    delisting_date  DATE,
    is_preferred    BOOLEAN NOT NULL DEFAULT FALSE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fact_price_daily (
    date                DATE NOT NULL,
    ticker              VARCHAR(6) NOT NULL REFERENCES dim_stock(ticker),
    open                DOUBLE PRECISION,
    high                DOUBLE PRECISION,
    low                 DOUBLE PRECISION,
    close               DOUBLE PRECISION,
    adj_close           DOUBLE PRECISION,
    volume              DOUBLE PRECISION,
    trading_value       DOUBLE PRECISION,
    market_cap          DOUBLE PRECISION,
    shares_outstanding  DOUBLE PRECISION,
    return_1d           DOUBLE PRECISION,
    source              TEXT,
    freshness_state     TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT now(),
    updated_at          TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (date, ticker)
);

CREATE TABLE IF NOT EXISTS fact_investor_flow_daily (
    date            DATE NOT NULL,
    ticker          VARCHAR(6) NOT NULL REFERENCES dim_stock(ticker),
    investor_group  TEXT NOT NULL,
    buy_volume      DOUBLE PRECISION,
    sell_volume     DOUBLE PRECISION,
    net_buy_volume  DOUBLE PRECISION,
    buy_amount      DOUBLE PRECISION,
    sell_amount     DOUBLE PRECISION,
    net_buy_amount  DOUBLE PRECISION,
    source          TEXT,
    freshness_state TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (date, ticker, investor_group)
);

CREATE TABLE IF NOT EXISTS fact_foreign_holding_daily (
    date                          DATE NOT NULL,
    ticker                        VARCHAR(6) NOT NULL REFERENCES dim_stock(ticker),
    foreign_held_shares           DOUBLE PRECISION,
    foreign_ownership_pct         DOUBLE PRECISION,
    foreign_limit_shares          DOUBLE PRECISION,
    foreign_limit_exhaustion_pct  DOUBLE PRECISION,
    source                        TEXT,
    freshness_state               TEXT,
    created_at                    TIMESTAMP NOT NULL DEFAULT now(),
    updated_at                    TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (date, ticker)
);

CREATE TABLE IF NOT EXISTS fact_features_daily (
    date                          DATE NOT NULL,
    ticker                        VARCHAR(6) NOT NULL REFERENCES dim_stock(ticker),
    feature_version               TEXT NOT NULL DEFAULT 'v0',
    foreign_net_5d_amt            DOUBLE PRECISION,
    institution_net_20d_pct_mcap  DOUBLE PRECISION,
    retail_streak_days            INTEGER,
    foreign_flow_z_60d            DOUBLE PRECISION,
    price_return_5d               DOUBLE PRECISION,
    volatility_20d                DOUBLE PRECISION,
    created_at                    TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (date, ticker, feature_version)
);

CREATE TABLE IF NOT EXISTS fact_ml_prediction_daily (
    date                  DATE NOT NULL,
    ticker                VARCHAR(6) NOT NULL REFERENCES dim_stock(ticker),
    horizon_days          INTEGER NOT NULL,
    model_name            TEXT NOT NULL,
    predicted_return      DOUBLE PRECISION,
    predicted_price       DOUBLE PRECISION,
    predicted_return_p10  DOUBLE PRECISION,
    predicted_return_p50  DOUBLE PRECISION,
    predicted_return_p90  DOUBLE PRECISION,
    prob_outperform_kospi DOUBLE PRECISION,
    model_version         TEXT,
    feature_version       TEXT,
    created_at            TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (date, ticker, horizon_days, model_name)
);
