# KOSPI Investor Flow Intelligence Platform — Project Context

**Project name:** KOSPI Investor Flow Intelligence Platform  
**Primary market:** KOSPI  
**Document purpose:** Reusable context document for coding-agent sessions  
**Last updated:** 2026-06-03
**Current phase:** MVP complete and **deployed**. Real KOSPI data loaded (948 tickers, ~5y), models trained, and production data served from Railway Postgres. Production split deployment is live: **Vercel** frontend at `https://acquin.vercel.app`, **Railway** FastAPI backend at `https://acquin-production.up.railway.app`, and Railway Postgres behind the API. Remaining: API auth/rate limiting, ops maturity, and licensed-data/legal hardening.
**Document version:** 0.6

---

## 1. How to use this document

Paste this document at the beginning of any new coding-agent session. The coding agent should use it as the source of truth for:

1. Project goals and non-negotiable requirements.
2. Current phase and completed work.
3. Data model, architecture, and ML assumptions.
4. Implementation standards.
5. What to update when a phase is completed.

At the end of each phase, update:

- `Current phase`
- `Phase progress tracker`
- `Progress log`
- `Decision log`
- `Known issues / technical debt`
- `Next coding-agent task brief`

Do not remove old progress notes. Append new notes chronologically.

---

## 2. Product summary

Build an application that tracks KOSPI investor-flow behavior by stock, focused on:

- 개인
- 기관
- 외국인

The app should provide:

1. Historical charts of investor flows and position proxies for each KOSPI stock.
2. Actual foreign ownership charts where available.
3. Screener filters based on recent position shifts by investor group.
4. Filters based on amount, percentage, lookback window, and consecutive-day streaks.
5. Trend analysis for each stock.
6. Historical analysis of the relationship between investor flow and subsequent stock-price movement.
7. ML-based projections of future stock prices or future returns using roughly five years of KOSPI historical data.
8. Daily updates after KOSPI market close, with final or reconciled data after official EOD data becomes available.

Reference UI/data inspiration:

- Naver Finance ranking page: `https://finance.naver.com/sise/sise_deal_rank.naver`
- Naver Finance investor-specific ranking example: `https://finance.naver.com/sise/sise_deal_rank.naver?investor_gubun=1000`

Naver should be treated as a UI/reference source, not necessarily the production-grade data source.

---

## 3. Critical product distinction

Do not mislabel investor net flow as true holdings.

### Publicly realistic data distinction

| Investor type | Daily buy/sell/net flow | Actual holdings |
|---|---:|---:|
| 개인 | Usually available as flow | Usually not available as true daily holdings |
| 기관 | Usually available as flow | Usually not available as true daily holdings |
| 외국인 | Usually available as flow | Foreign holding quantity and ownership ratio are commonly available |

### Required terminology in the app

Use:

- `개인 순매수`
- `기관 순매수`
- `외국인 순매수`
- `개인 누적 순매수`
- `기관 누적 순매수`
- `외국인 누적 순매수`
- `외국인 보유량`
- `외국인 보유비율`

Avoid:

- `개인 보유량`, unless a real holdings source is licensed and verified.
- `기관 보유량`, unless a real holdings source is licensed and verified.

When visualizing 개인/기관 “holdings-like” history, label it clearly as:

```text
누적 순매수 기준 포지션 프록시
```

or in English:

```text
Cumulative net-buy proxy, not actual holdings
```

---

## 4. Data source strategy

### 4.1 Preferred production sources

The production version should prefer official or licensed data sources:

| Data need | Preferred source | Notes |
|---|---|---|
| KOSPI ticker universe | KRX / Koscom / licensed vendor | Must include historical listings and delistings if possible. |
| Daily OHLCV | KRX / Koscom / licensed vendor | Must support adjusted prices or corporate-action adjustment. |
| Market cap / listed shares | KRX / Koscom / licensed vendor | Needed for percentage normalization. |
| Investor flow by stock | KRX / Koscom / licensed vendor | 개인/기관/외국인 buy, sell, net buy by stock/date. |
| Foreign holdings | KRX / Koscom / licensed vendor | 외국인 보유량 and 외국인 보유비율. |
| Prototype data | pykrx or equivalent | Acceptable for MVP/prototype only, subject to source/licensing constraints. |
| Broker API supplement | Korea Investment Securities API or similar | Optional, especially for estimated intraday or near-real-time investor data. |

### 4.2 Licensing note

Before commercial deployment or redistribution, confirm whether the selected data source permits:

- Storage
- Redistribution
- User-facing charts
- Derived analytics
- ML model training
- Paid subscription products

Data licensing must be resolved before production launch.

---

## 5. Update timing and data freshness

The app must update after the KOSPI market close.

### Recommended daily schedule, Korea time

| Time KST | Job |
|---:|---|
| 15:40–16:10 | Pull preliminary OHLCV/close data if available. Mark as preliminary. |
| 16:15–17:00 | Pull first EOD data where available. Update dashboards as first-pass EOD. |
| 18:20–19:00 | Pull final/reconciled investor flow data. Mark trading date as complete. |
| 19:00+ | Run feature generation, screeners, correlation refresh, ML inference, and alerts. |
| Next morning | Reconciliation job for missing data, corporate actions, and source corrections. |

### Data freshness states

Every daily row should support a freshness/completion flag:

```text
PRELIMINARY
FIRST_EOD
FINAL_EOD
RECONCILED
ERROR
```

User-facing pages should display the latest data timestamp and whether the data is preliminary or final.

---

## 6. High-level architecture

### 6.1 Suggested stack

| Layer | Recommended tools |
|---|---|
| Data ingestion | Python, Polars or Pandas, Airflow or Prefect |
| Raw data storage | S3/MinIO/local object store using Parquet |
| Application DB | PostgreSQL + TimescaleDB for MVP |
| Analytics DB, later scale | ClickHouse if query volume becomes large |
| Backend API | FastAPI |
| Frontend | Next.js / React |
| Charts | Plotly, Apache ECharts, or TradingView Lightweight Charts |
| ML | scikit-learn, LightGBM, CatBoost, MLflow, Optuna |
| Cache | Redis |
| Deployment | Docker Compose for MVP, cloud deployment later |

### 6.2 Pipeline overview

```text
Data Source APIs / files
        ↓
Raw ingestion jobs
        ↓
Raw immutable Parquet storage
        ↓
Cleaning / normalization
        ↓
PostgreSQL / TimescaleDB core tables
        ↓
Feature generation
        ↓
Analytics tables + ML inference outputs
        ↓
FastAPI backend
        ↓
Next.js frontend
```

### 6.3 Core services

| Service | Responsibility |
|---|---|
| `ingestion-service` | Pull market, price, investor-flow, and foreign-holding data. |
| `data-validation-service` | Check row counts, missing tickers, duplicate records, source freshness, abnormal values. |
| `feature-service` | Generate rolling investor-flow, streak, return, volatility, and normalized features. |
| `analytics-service` | Generate correlation, event-study, and similar-case analytics. |
| `ml-service` | Train models, evaluate models, save model artifacts, generate daily predictions. |
| `api-service` | Serve stock pages, screeners, analytics, and ML predictions. |
| `frontend-app` | User interface for dashboards, stock pages, charts, and filters. |

---

## 7. Core database schema

The exact schema can evolve, but the coding agent should keep these logical tables intact.

### 7.1 `dim_stock`

Stores stock metadata.

| Column | Type | Notes |
|---|---|---|
| `ticker` | text | Six-digit KRX stock code. Primary logical identifier. |
| `isin` | text | Nullable if unavailable. |
| `name_kr` | text | Korean stock name. |
| `name_en` | text | Optional. |
| `market` | text | `KOSPI` for this project phase. |
| `sector` | text | KRX or vendor sector classification. |
| `listing_date` | date | Nullable for prototype. |
| `delisting_date` | date | Nullable. |
| `is_preferred` | boolean | Preferred share flag. |
| `is_active` | boolean | Current listing status. |
| `created_at` | timestamp | Audit. |
| `updated_at` | timestamp | Audit. |

### 7.2 `fact_price_daily`

Stores stock-level daily price, volume, and market-cap data.

| Column | Type | Notes |
|---|---|---|
| `date` | date | Trading date. |
| `ticker` | text | FK to `dim_stock`. |
| `open` | numeric | Raw open. |
| `high` | numeric | Raw high. |
| `low` | numeric | Raw low. |
| `close` | numeric | Raw close. |
| `adj_close` | numeric | Adjusted close; required for modeling. |
| `volume` | numeric | Shares traded. |
| `trading_value` | numeric | KRW trading value. |
| `market_cap` | numeric | KRW market cap. |
| `shares_outstanding` | numeric | Listed shares. |
| `return_1d` | numeric | Daily log or simple return; be explicit. |
| `source` | text | Data vendor/source. |
| `freshness_state` | text | PRELIMINARY/FIRST_EOD/FINAL_EOD/RECONCILED/ERROR. |
| `created_at` | timestamp | Audit. |
| `updated_at` | timestamp | Audit. |

Primary key candidate:

```text
(date, ticker)
```

### 7.3 `fact_investor_flow_daily`

Stores investor buy/sell/net-flow data by stock/date/investor group.

| Column | Type | Notes |
|---|---|---|
| `date` | date | Trading date. |
| `ticker` | text | FK to `dim_stock`. |
| `investor_group` | text | `retail`, `institution`, `foreign`, etc. |
| `buy_volume` | numeric | Shares bought. |
| `sell_volume` | numeric | Shares sold. |
| `net_buy_volume` | numeric | `buy_volume - sell_volume`. |
| `buy_amount` | numeric | KRW buy amount. |
| `sell_amount` | numeric | KRW sell amount. |
| `net_buy_amount` | numeric | `buy_amount - sell_amount`. |
| `source` | text | Data source. |
| `freshness_state` | text | PRELIMINARY/FIRST_EOD/FINAL_EOD/RECONCILED/ERROR. |
| `created_at` | timestamp | Audit. |
| `updated_at` | timestamp | Audit. |

Primary key candidate:

```text
(date, ticker, investor_group)
```

Recommended investor-group enum values:

```text
retail
institution
foreign
other_corporation
other_foreign
financial_investment
insurance
trust
private_equity
bank
pension_fund
```

Only the first three are required in the MVP.

### 7.4 `fact_foreign_holding_daily`

Stores actual foreign ownership data.

| Column | Type | Notes |
|---|---|---|
| `date` | date | Trading date or data date. |
| `ticker` | text | FK to `dim_stock`. |
| `foreign_held_shares` | numeric | Actual foreign-held shares. |
| `foreign_ownership_pct` | numeric | Foreign ownership ratio. |
| `foreign_limit_shares` | numeric | Nullable. |
| `foreign_limit_exhaustion_pct` | numeric | Nullable. |
| `source` | text | Data source. |
| `freshness_state` | text | PRELIMINARY/FIRST_EOD/FINAL_EOD/RECONCILED/ERROR. |
| `created_at` | timestamp | Audit. |
| `updated_at` | timestamp | Audit. |

Primary key candidate:

```text
(date, ticker)
```

### 7.5 `fact_features_daily`

Stores precomputed features for screeners, analytics, and ML.

| Column | Type | Notes |
|---|---|---|
| `date` | date | Feature date. |
| `ticker` | text | FK to `dim_stock`. |
| `foreign_net_5d_amt` | numeric | Example rolling feature. |
| `institution_net_20d_pct_mcap` | numeric | Example normalized feature. |
| `retail_streak_days` | integer | Signed streak. Positive = net buy streak, negative = net sell streak. |
| `foreign_flow_z_60d` | numeric | 60D z-score. |
| `price_return_5d` | numeric | 5D return. |
| `volatility_20d` | numeric | 20D volatility. |
| `feature_version` | text | Version identifier. |
| `created_at` | timestamp | Audit. |

This table may become wide. For MVP, a wide feature table is acceptable. Later, consider feature store patterns.

### 7.6 `fact_ml_prediction_daily`

Stores model predictions.

| Column | Type | Notes |
|---|---|---|
| `date` | date | Prediction date, after EOD data is available. |
| `ticker` | text | FK to `dim_stock`. |
| `horizon_days` | integer | Example: 1, 3, 5, 10, 20. |
| `predicted_return` | numeric | Expected forward return. |
| `predicted_price` | numeric | Derived from close and predicted return. |
| `predicted_return_p10` | numeric | Lower quantile. |
| `predicted_return_p50` | numeric | Median quantile. |
| `predicted_return_p90` | numeric | Upper quantile. |
| `prob_outperform_kospi` | numeric | Classification output. |
| `model_name` | text | Example: `lightgbm_return_10d`. |
| `model_version` | text | MLflow or internal version. |
| `feature_version` | text | Feature set version. |
| `created_at` | timestamp | Audit. |

---

## 8. Screener requirements

The screener must allow users to filter based on recent investor-position shifts.

### 8.1 Required filters

| Filter | Example |
|---|---|
| Market | KOSPI |
| Lookback window | Past 5, 10, 20, or 60 trading days |
| Investor group | 개인, 기관, 외국인, 외국인+기관 |
| Net-buy amount | 외국인 순매수 ≥ ₩50B over 5D |
| Net-buy as % of market cap | 기관 순매수 ≥ 0.5% of market cap over 10D |
| Net-buy volume as % of shares | 외국인 순매수량 ≥ 0.3% of shares outstanding over 20D |
| Consecutive net-buy/net-sell days | 기관 4일 연속 순매수 |
| Flow acceleration | Recent net buy exceeds previous-period average |
| Divergence | Price down while foreign/institution accumulate |
| Liquidity | Average trading value ≥ threshold |
| Market cap | Large/mid/small cap buckets |
| Exclusions | Preferred shares, ETFs, SPACs, suspended stocks, low-liquidity names |

### 8.2 Core percentage metrics

Use these metrics for stable filters:

```text
net_buy_amount_pct_mcap = x_day_net_buy_amount / market_cap

net_buy_volume_pct_shares = x_day_net_buy_volume / shares_outstanding

net_buy_amount_pct_turnover = x_day_net_buy_amount / x_day_total_trading_value

foreign_holding_change_pctp = foreign_ownership_pct_today - foreign_ownership_pct_x_days_ago
```

Avoid percentage change in cumulative net buy when the base is close to zero.

### 8.3 Example screener payload

```json
{
  "market": "KOSPI",
  "lookback_days": 5,
  "investor_groups": ["foreign", "institution"],
  "min_net_buy_amount": 50000000000,
  "min_net_buy_pct_mcap": 0.003,
  "min_consecutive_days": 3,
  "min_avg_trading_value": 10000000000,
  "exclude_preferred": true
}
```

---

## 9. Stock-detail page requirements

Each stock page should include these sections.

### 9.1 Overview

- Ticker and stock name
- Sector
- Market cap
- Current close price
- 1D, 5D, 20D returns
- Average trading value
- Latest data timestamp and freshness state

### 9.2 Price chart

- OHLC or line chart
- Volume
- Moving averages: 5D, 20D, 60D, 120D
- Optional: volatility bands

### 9.3 Investor flow chart

- 개인 daily net buy
- 기관 daily net buy
- 외국인 daily net buy
- Rolling cumulative net buy by investor group
- Toggle KRW amount vs share volume
- Toggle raw amount vs normalized by market cap/shares

### 9.4 Foreign holding chart

- 외국인 보유량
- 외국인 보유비율
- Foreign ownership percentage-point change over selected windows

### 9.5 Trend analysis

- Rolling 5D/20D/60D net flow
- Streaks by investor group
- Foreign/institution co-buy signals
- Retail selling while foreign/institution accumulating
- Price-flow divergence

### 9.6 Historical post-signal analysis

For selected signal conditions, show:

- Average subsequent return after 1D, 3D, 5D, 10D, 20D
- Median subsequent return
- Hit rate
- Outperformance rate vs KOSPI
- Number of historical cases
- Distribution chart
- Recent similar cases

### 9.7 ML projection

Show:

- Expected future return
- Projected future price
- Bear/base/bull price band
- Probability of outperforming KOSPI
- Confidence score
- Top explanatory features
- Model version and prediction timestamp

---

## 10. Analytics and event-study design

### 10.1 Rolling trend features

For each stock and investor group:

```text
net_buy_1d
net_buy_3d
net_buy_5d
net_buy_10d
net_buy_20d
net_buy_60d
net_buy_pct_mcap_5d
net_buy_pct_mcap_20d
net_buy_volume_pct_shares_5d
net_buy_volume_pct_shares_20d
flow_zscore_60d
flow_zscore_252d
signed_streak_days
```

### 10.2 Cross-investor features

```text
foreign_plus_institution_net_5d
foreign_minus_retail_net_5d
institution_minus_retail_net_5d
is_foreign_and_institution_both_buying_3d
is_retail_selling_while_foreign_buying
is_retail_selling_while_institution_buying
```

### 10.3 Event definitions

Candidate event definitions:

| Event | Example definition |
|---|---|
| Foreign accumulation | Foreign 5D net buy is top decile vs stock's own trailing 252D history. |
| Institution accumulation | Institution 10D net buy ≥ 0.5% of market cap. |
| Dual accumulation | Foreign and institution both net buyers for 3+ consecutive days. |
| Retail exit | Retail net selling while foreign/institution net buying. |
| Flow reversal | Foreign shifts from 20D net selling to 5D net buying. |
| Price-flow divergence | Price down over 5D, but foreign/institution net buying is strong. |

### 10.4 Event-study outputs

For each event and horizon:

```text
count
mean_return
median_return
positive_return_rate
outperform_kospi_rate
p10_return
p90_return
best_case
worst_case
latest_matching_dates
```

---

## 11. ML model design

### 11.1 Prediction targets

Train for multiple horizons:

```text
h ∈ {1, 3, 5, 10, 20} trading days
```

Analytical target:

```text
future_return_close_to_close_h = log(adj_close[t + h] / adj_close[t])
```

Tradeable target:

```text
future_return_tradeable_h = log(adj_close[t + h] / open[t + 1])
```

Use the tradeable target for backtesting because investor-flow data is known only after the market close.

Classification target:

```text
outperform_kospi_h = 1 if stock_return_h > kospi_return_h else 0
```

### 11.2 Initial feature set

Investor-flow features by investor group:

```text
net_buy_amt_g_1d
net_buy_amt_g_3d
net_buy_amt_g_5d
net_buy_amt_g_10d
net_buy_amt_g_20d
net_buy_amt_pct_mcap_g_5d
net_buy_volume_pct_shares_g_5d
net_buy_amt_pct_turnover_g_5d
positive_days_g_5d
positive_days_g_20d
streak_days_g
flow_zscore_g_60d
flow_zscore_g_252d
flow_acceleration_g
```

Price/volume controls:

```text
return_1d
return_5d
return_20d
volatility_20d
turnover_20d
volume_zscore_20d
distance_from_20d_ma
distance_from_60d_ma
market_cap_log
liquidity_log
```

Market/sector controls:

```text
kospi_return_1d
kospi_return_5d
sector_return_5d
stock_return_minus_sector_return_5d
beta_252d
```

Optional later features:

```text
PER
PBR
dividend_yield
short_selling_balance
program_trading
margin_credit_balance
USD_KRW
interest_rates
```

### 11.3 Baseline statistical model

Before advanced ML, implement transparent correlation/regression analysis.

Rolling or panel correlation:

```text
corr(investor_net_buy_pct_mcap_window, future_return_h)
```

Panel regression concept:

```text
future_return_i,t,h =
    alpha_i
  + gamma_t
  + beta1 * foreign_net_buy_pct_mcap_i,t,5d
  + beta2 * institution_net_buy_pct_mcap_i,t,5d
  + beta3 * retail_net_buy_pct_mcap_i,t,5d
  + beta4 * return_i,t,5d
  + beta5 * volatility_i,t,20d
  + beta6 * turnover_i,t,20d
  + error_i,t
```

### 11.4 Recommended ML model sequence

| Stage | Model | Purpose |
|---|---|---|
| Baseline | Linear Regression / ElasticNet | Simple benchmark and interpretability. |
| Classification baseline | Logistic Regression | Probability of outperformance. |
| Main model | LightGBM | Nonlinear tabular modeling. |
| Alternative | CatBoost or XGBoost | Compare to LightGBM. |
| Prediction bands | Quantile LightGBM | P10/P50/P90 return bands. |
| Advanced later | Temporal sequence model | Only after tabular models prove useful. |

Initial production recommendation:

```text
LightGBM regression for expected forward return.
LightGBM classifier for probability of KOSPI outperformance.
LightGBM quantile models for prediction bands.
```

### 11.5 Training methodology

Use time-based walk-forward validation. Never use random train/test splits for the main reported results.

Example:

| Fold | Train | Validation | Test |
|---|---|---|---|
| 1 | Years 1–3 | Year 4 H1 | Year 4 H2 |
| 2 | Years 1–4 | Year 5 Q1 | Year 5 Q2 |
| 3 | Years 1–4.5 | Year 5 Q3 | Year 5 Q4 |

Safeguards:

- No look-ahead leakage.
- Shift or lag any feature that is not available by the prediction timestamp.
- Use adjusted prices for return targets.
- Include delisted names if possible to reduce survivorship bias.
- Normalize flow by market cap, shares outstanding, and trading value.
- Winsorize extreme features.
- Use only data available after the EOD update for day `t`.
- Earliest assumed trade for a signal from day `t` is next trading day open or close, depending on selected backtest convention.

### 11.6 Evaluation metrics

| Metric | Purpose |
|---|---|
| MAE / RMSE | Return prediction error. |
| Directional accuracy | Up/down usefulness. |
| AUC / log loss | Classification quality. |
| Daily Spearman IC | Ranking quality. |
| ICIR | Stability of ranking signal. |
| Precision@K | Quality of top-ranked stock picks. |
| Top-decile minus bottom-decile return | Signal spread. |
| Backtested return after transaction costs | Practical usefulness. |
| Max drawdown | Risk. |
| Turnover | Transaction-cost sensitivity. |
| Calibration | Whether predicted probabilities are reliable. |

### 11.7 User-facing ML output format

Example:

```text
10D expected return: +2.1%
Projected price: ₩74,300
Prediction band: ₩69,000 – ₩78,500
Probability of KOSPI outperformance: 61%
Historical similar-case hit rate: 58%
Similar historical cases: 143
Model version: lightgbm_return_10d_v003
Prediction generated: 2026-05-28 19:15 KST
```

---

## 12. API design

### 12.1 Core endpoints

```text
GET /health
GET /metadata/data-freshness

GET /stocks
GET /stocks/{ticker}
GET /stocks/{ticker}/price
GET /stocks/{ticker}/investor-flows
GET /stocks/{ticker}/foreign-holdings
GET /stocks/{ticker}/features
GET /stocks/{ticker}/correlations
GET /stocks/{ticker}/events
GET /stocks/{ticker}/projection

GET /market/overview
GET /market/investor-flows
GET /market/top-net-buy

POST /screeners/investor-flow
POST /screeners/streaks
POST /screeners/divergence
POST /screeners/foreign-institution-co-buy
```

### 12.2 Response conventions

All API responses should include:

```json
{
  "data": {},
  "metadata": {
    "source": "...",
    "freshness_state": "FINAL_EOD",
    "latest_data_date": "YYYY-MM-DD",
    "generated_at": "YYYY-MM-DDTHH:MM:SS+09:00"
  }
}
```

For errors:

```json
{
  "error": {
    "code": "DATA_NOT_AVAILABLE",
    "message": "Investor-flow data is not available for this ticker/date.",
    "details": {}
  }
}
```

---

## 13. Frontend pages

### 13.1 Required MVP pages

| Page | Purpose |
|---|---|
| `/` | Market overview dashboard. |
| `/screener` | Investor-flow screener. |
| `/stocks/[ticker]` | Stock detail page. |
| `/rankings` | Naver-style ranking by net buy/sell and investor group. |
| `/models` | Model performance and methodology summary. |
| `/data-status` | Data freshness, update status, and error reports. |

### 13.2 Screener table columns

| Column |
|---|
| Rank |
| Ticker |
| Name |
| Sector |
| Price |
| 1D return |
| 5D return |
| 20D return |
| Foreign 5D net buy |
| Institution 5D net buy |
| Retail 5D net buy |
| Foreign 5D net buy / market cap |
| Institution 5D net buy / market cap |
| Foreign streak |
| Institution streak |
| ML 10D expected return |
| Probability of KOSPI outperformance |

---

## 14. Phase roadmap

### Phase 0 — Project context and planning

**Status:** Completed  
**Completion date:** 2026-05-28  
**Goal:** Establish project scope, architecture, roadmap, and coding-agent handoff document.

Deliverables:

- Project context document.
- Phase roadmap.
- Data model proposal.
- ML methodology proposal.
- Update protocol for future coding-agent sessions.

Acceptance criteria:

- A new coding-agent session can understand the project without reading prior conversation.
- The document states current phase and next task.
- The document includes a clear progress-update protocol.

Notes:

- This document is the output of Phase 0.

---

### Phase 1 — Data foundation

**Status:** Completed (MVP scope)  
**Start date:** 2026-05-29  
**Completion date:** 2026-05-29  
**Goal:** Build the first reliable data pipeline and schema for KOSPI stocks, prices, investor flows, and foreign holdings.

Deliverables:

1. Project repository structure.
2. Environment configuration.
3. Database schema migrations.
4. Initial data ingestion scripts.
5. Raw data storage layout.
6. Data validation checks.
7. Basic CLI or job runner for daily ingestion.
8. Sample dataset sufficient to test app features.

Minimum implementation scope:

- KOSPI ticker universe.
- Daily OHLCV.
- Market cap and shares outstanding if available.
- Daily investor flow by ticker and investor group.
- Foreign holdings if available.
- At least 5 years of historical data, subject to source availability.

Acceptance criteria:

- Database can be initialized from scratch.
- Ingestion can run for a configurable date range.
- Data can be queried by ticker/date.
- Missing and duplicate rows are detected.
- Freshness state is stored.
- At least one stock has price, investor-flow, and feature-ready rows.

Suggested repository structure:

```text
kospi-investor-flow/
  apps/
    api/
    web/
  packages/
    core/
    data/
    analytics/
    ml/
  infra/
    docker/
    migrations/
  data/
    raw/
    processed/
  notebooks/
  scripts/
  tests/
  docs/
```

---

### Phase 2 — Dashboard and screener

**Status:** Backend completed (MVP); frontend scaffolded (not build-verified)  
**Completion date:** 2026-05-29 (backend)  
**Goal:** Build the first user-facing app with market overview, stock pages, investor-flow charts, and screener filters.

Deliverables:

1. FastAPI endpoints for stocks, price, investor flows, and screeners.
2. Next.js frontend shell.
3. Market overview dashboard.
4. Stock-detail page.
5. Investor-flow charts.
6. Foreign-holding charts where available.
7. Screener filters by amount, percentage, lookback days, and consecutive streak.

Acceptance criteria:

- User can view a stock page by ticker.
- User can filter stocks by foreign/institution/retail net-buy criteria.
- User can rank by recent net-buy amount and net-buy percentage of market cap.
- Charts show data timestamp and freshness state.

---

### Phase 3 — Correlation and event studies

**Status:** Completed (MVP)  
**Completion date:** 2026-05-29  
**Goal:** Add historical analytics that show whether investor-flow signals were followed by future price rises/falls.

Deliverables:

1. Feature-generation job.
2. Forward-return label generation.
3. Rolling correlation calculations.
4. Event-study engine.
5. Similar-case retrieval.
6. API endpoints for correlation and event-study results.
7. Frontend visualizations for subsequent-return distributions.

Acceptance criteria:

- User can select a stock and signal condition.
- App shows historical count, mean return, median return, hit rate, and outperformance rate.
- App supports horizons: 1D, 3D, 5D, 10D, 20D.
- Analytics avoid look-ahead bias.

---

### Phase 4 — ML projection

**Status:** Completed (MVP)  
**Completion date:** 2026-05-29  
**Goal:** Train and serve ML models that estimate future returns and probability of KOSPI outperformance.

Deliverables:

1. ML training dataset builder.
2. Baseline linear/ElasticNet model.
3. LightGBM regression model.
4. LightGBM classifier for outperformance.
5. Optional quantile models for prediction bands.
6. Walk-forward validation framework.
7. Model evaluation report.
8. Daily inference job.
9. API endpoint and frontend display for projections.

Acceptance criteria:

- Model training is reproducible.
- Walk-forward validation is used.
- Model results include ranking metrics such as Daily Spearman IC.
- Predictions are stored in `fact_ml_prediction_daily`.
- Stock page shows expected return, projected price band, probability of outperformance, model version, and prediction timestamp.

---

### Phase 5 — Production hardening

**Status:** Substantially completed (MVP)  
**Completion date:** 2026-05-29  
**Goal:** Improve reliability, licensing readiness, performance, and operational monitoring.

Done: daily orchestrator with retry + per-step error capture; KST job scheduler (`scheduler` CLI + sample crontab) mapping the §5 timetable; alerting system (pluggable console/file/webhook notifiers + rule engine, integrated into the pipeline); model registry (`ml_model_registry`) recording every trained model + OOS metrics with an active-version flag; feature-drift monitoring via PSI (`fact_model_drift_daily`, low-sample guard); user watchlists (`watchlist`/`watchlist_item` tables + CRUD API + flows view); `/data-status` data-quality endpoint; `/models` + `/models/{name}/drift` endpoints; CORS config + Docker healthcheck + `.dockerignore`; security review (`docs/SECURITY.md`) and data-licensing review (`docs/DATA_LICENSING.md`); scheduling/ops guide (`docs/SCHEDULING.md`).

Remaining (require external resources/decisions, not pure code): licensed production data feed + `LicensedProvider` implementation; migration to Airflow/Prefect for SLAs/backfills; API authentication/authorization + rate limiting + TLS; MLflow-based model registry + automated retrain-on-drift; richer notifier integrations (email/Kakao/Telegram); executed legal/data-license sign-off.

Deliverables:

1. Licensed data-source integration if required.
2. Job orchestration with retries.
3. Data-quality dashboard.
4. Model registry and model-drift monitoring.
5. Alerting system.
6. User watchlists.
7. Deployment hardening.
8. Security review.
9. Legal/data-license review.

Acceptance criteria:

- Daily EOD pipeline runs reliably.
- Errors are visible and recoverable.
- App shows data freshness and model freshness.
- Commercial data-usage constraints are documented.
- System can be deployed in a repeatable environment.

---

## 15. Current progress tracker

| Phase | Status | Start date | Completion date | Notes |
|---|---|---:|---:|---|
| Phase 0 — Context and planning | Completed | 2026-05-28 | 2026-05-28 | Initial project context created. |
| Phase 1 — Data foundation | Completed (MVP) | 2026-05-29 | 2026-05-29 | Schema, providers, ingestion, validation, features, CLI, tests. |
| Phase 2 — Dashboard and screener | Backend done; frontend scaffold | 2026-05-29 | 2026-05-29 | FastAPI endpoints + screeners done & tested. Next.js shell scaffolded, not build-verified. |
| Phase 3 — Correlation and event studies | Completed (MVP) | 2026-05-29 | 2026-05-29 | Labels, rolling correlation, event-study engine, similar cases + API. |
| Phase 4 — ML projection | Completed (MVP) | 2026-05-29 | 2026-05-29 | Dataset builder, walk-forward, sklearn/LightGBM models, inference, projection API. |
| Phase 5 — Production hardening | Substantially completed (MVP) | 2026-05-29 | 2026-05-29 | Orchestrator+retry, alerting, watchlists, model registry+drift, scheduler, Docker/CORS, security+licensing review docs. Remaining: licensed feed, Airflow/Prefect, auth, MLflow. |

---

## 16. Progress log

### 2026-05-28 — Phase 0 completed

Created the initial project context document for future coding-agent sessions. The project is defined as a KOSPI investor-flow intelligence platform tracking 개인, 기관, and 외국인 net buying, with foreign actual holdings where available. The roadmap is divided into five implementation phases after planning: data foundation, dashboard/screener, correlation/event studies, ML projection, and production hardening.

Next recommended task:

```text
Start Phase 1 by creating the repository structure, database schema migrations, and an initial data-ingestion prototype for KOSPI ticker/price/investor-flow data.
```

---

### 2026-05-29 — Phase 1 completed (MVP scope)

Status:
- Completed (MVP scope)

Summary:
- Implemented a runnable data foundation: repository structure, configuration, database schema (ORM + Alembic migration), a source-agnostic provider abstraction with three providers, an idempotent ingestion service, validation utilities, a small feature pipeline, a CLI job runner, and a pytest suite. The full pipeline runs offline with no licensed data or network access via a deterministic `sample` provider.

Completed deliverables (vs. Phase 1 list):
1. Repository structure — done (see "Files/modules" below).
2. Environment configuration — `kospi_flow/core/config.py` (pydantic-settings, `KOSPI_` env prefix, `.env`), `.env.example`.
3. Database schema migrations — ORM models as source of truth + Alembic baseline (`infra/migrations`) + reference SQL DDL. Verified `alembic upgrade head` on a fresh DB.
4. Initial data ingestion scripts — `kospi_flow/data/ingestion.py`, CLI `ingest`, `scripts/run_ingestion.py`.
5. Raw data storage layout — raw provider output persisted to `data/raw/<kind>/` as Parquet (CSV fallback) before transformation.
6. Data validation checks — `kospi_flow/data/validation.py` (row presence, duplicate keys, freshness validity, flow/foreign coverage vs. price dates).
7. Basic CLI / job runner — `python -m kospi_flow.cli {info,init-db,ingest,features,validate}`.
8. Sample dataset — `SampleProvider` generates ~deterministic 6-stock universe with price/flow/foreign data over any date range.

Acceptance criteria — all met and verified:
- DB initialized from scratch (`init-db` and Alembic). ✓
- Ingestion runs for a configurable date range (`--start/--end/--tickers`). ✓
- Data queryable by ticker/date. ✓
- Missing and duplicate rows detected (validation + tests). ✓
- Freshness state stored on every fact row. ✓
- At least one stock has price, investor-flow, and feature-ready rows (verified for 005930). ✓

Files/modules created:
- `kospi_flow/` package: `core/{config,db,models,enums,logging}.py`; `data/{ingestion,validation}.py`; `data/providers/{base,sample,pykrx_provider,licensed,__init__}.py`; `analytics/{features,pipeline}.py`; `ml/` (placeholder); `cli.py`.
- `infra/migrations/` Alembic (`alembic.ini`, `env.py`, `script.py.mako`, `versions/0001_initial_baseline.py`) + `sql/0001_initial_schema_reference.sql`.
- `scripts/{init_db,run_ingestion,run_validation}.py`.
- `tests/{conftest,test_config,test_models,test_features,test_ingestion,test_validation}.py` — 22 tests, all passing.
- `pyproject.toml`, `.env.example`, `.gitignore`, `README.md`, `apps/api`, `apps/web` placeholders, data/notebooks/docs scaffolding.

Important decisions (see Decision log for detail):
- MVP defaults to SQLite + an offline deterministic `sample` provider so the pipeline runs anywhere; PostgreSQL/TimescaleDB and pykrx/licensed sources are config swaps.
- ORM models are the single source of truth; the Alembic baseline builds from `Base.metadata`; a test guards ORM/migration parity.
- Monetary/volume columns use `Float` (DOUBLE PRECISION) for the MVP rather than `Numeric` (tracked as technical debt).
- Repository's suggested `packages/*` is realized as subpackages of a single importable `kospi_flow` package.

Tests/checks completed:
- `python -m pytest` → 22 passed.
- CLI `info → init-db → ingest → features → validate` verified end-to-end (0 validation errors/warnings); raw Parquet written; sample row queried.
- `alembic upgrade head` verified on a fresh SQLite DB.

Known issues / blockers:
- `sample` provider data is synthetic and must never be shown to users as real data.
- Sample trading calendar uses Mon–Fri business days; KR market holidays are not modelled.
- Production data source/license still unresolved; `licensed` provider is a stub.
- Float (not Numeric) columns for KRW amounts; revisit for exact-precision production needs.

Data/model assumptions introduced:
- Daily net flows across the three MVP investor groups roughly net to zero in sample data.
- `adj_close == close` in sample data (no corporate actions modelled).
- Feature subset (`v0`): `foreign_net_5d_amt`, `institution_net_20d_pct_mcap`, `retail_streak_days`, `foreign_flow_z_60d`, `price_return_5d`, `volatility_20d`.

Next recommended task:
- Begin Phase 2 (Dashboard and screener): build FastAPI endpoints in `apps/api` over the Phase 1 tables (`/stocks`, `/stocks/{ticker}/price|investor-flows|foreign-holdings`, screener POST endpoints) following the response conventions in §12, then the Next.js shell in `apps/web`. Optionally first validate the `pykrx` provider against real data and load a wider ticker universe.

---

### 2026-05-29 — Phases 2–5 backend completed (MVP scope)

Status:
- Phase 2: backend completed, frontend scaffolded (not build-verified).
- Phase 3: completed (MVP). Phase 4: completed (MVP). Phase 5: partially completed.

Summary:
- Built the full Python backend across Phases 2–5 on top of the Phase 1 foundation, all running offline on the deterministic `sample` provider and covered by tests (54 total, all passing). Verified the daily pipeline and the live API server end-to-end. The Next.js frontend is scaffolded but was not `npm install`/build-verified in this environment.

Completed deliverables:
- Phase 2 (API): FastAPI app factory with `{data, metadata}` success envelope (KST `generated_at`) and `{error}` envelope. Endpoints: `/health`, `/metadata/data-freshness`, `/stocks`, `/stocks/{ticker}`, `/stocks/{ticker}/{price,investor-flows,foreign-holdings,features}`, `/market/{overview,top-net-buy,investor-flows}`, `POST /screeners/{investor-flow,streaks,foreign-institution-co-buy}`. Screener supports amount, %mcap, %shares, consecutive-streak, avg-trading-value, preferred-exclusion. Cumulative 개인/기관 flows explicitly labelled as a net-buy position proxy.
- Phase 3 (analytics): forward-return labels (close-to-close log, tradeable, simple) + outperform-market label; rolling Pearson/Spearman correlation of net-buy %mcap vs forward return; event-study engine (foreign/institution/dual accumulation, retail exit, price-flow divergence) with count/mean/median/positive-rate/outperform-rate/p10/p90/best/worst + matching dates; nearest-neighbour similar-case retrieval; API `/stocks/{ticker}/correlations` and `/events`. KOSPI benchmark is a cap-weighted market proxy (no index series in sample data).
- Phase 4 (ML): panel dataset builder (flow + price + market features, forward targets) shared by train/inference; time-based walk-forward validation with embargo = horizon; model factory (ElasticNet baseline, gradient-boosting regressor [LightGBM if installed else sklearn HistGradientBoosting], classifier, P10/P50/P90 quantile regressors); metrics incl. MAE/RMSE/directional accuracy/AUC/Daily Spearman IC/ICIR; inference stores to `fact_ml_prediction_daily`; API `/stocks/{ticker}/projection` with bear/base/bull bands, outperform probability, and an uncertainty disclaimer. CLI `train`/`predict`.
- Phase 5 (partial): `kospi_flow/jobs/daily.py` orchestrator (ingest→features→[train]→predict→validate) with retry and per-step status/error capture; CLI `daily`; `/data-status` data-quality endpoint; `infra/docker/Dockerfile` + `docker-compose.yml` (SQLite default, commented TimescaleDB option).
- Frontend: minimal Next.js (App Router) under `apps/web` — overview, rankings, screener, stock-detail pages + API client; documented as not build-verified here.

Files/modules created (high level):
- `kospi_flow/api/` (app, envelope, deps, schemas, routers/{metadata,stocks,market,screeners,analytics,projection,status}); `apps/api/main.py`.
- `kospi_flow/analytics/` (market, screener, labels, correlation, events, similar, service) added to the Phase 1 features/pipeline.
- `kospi_flow/ml/` (dataset, validation, models, metrics, train, inference).
- `kospi_flow/jobs/` (daily).
- `apps/web/` Next.js scaffold; `infra/docker/`.
- Tests: `tests/{test_api,test_analytics,test_ml,test_jobs}.py`.

Tests/checks completed:
- `python -m pytest` → 54 passed.
- `python -m kospi_flow.cli daily --train` over ~2.5y × 3 tickers → all steps ok (backend=sklearn, predictions stored, validation clean).
- Live `uvicorn` boot: `/health`, `/stocks/005930/projection`, and a screener POST all returned correctly.
- Fixed a Windows cp949 console crash in `cli --help` (removed non-ASCII from argparse help).

Important decisions:
- KOSPI benchmark = cap-weighted market proxy from the universe (sample data has no index); replace with the official KOSPI index in production.
- ML backend auto-selects LightGBM if installed, else scikit-learn HistGradientBoosting (LightGBM not installed in this environment, so sklearn was used and tested).
- API logic lives in the importable `kospi_flow.api` package; `apps/api/main.py` is a thin entrypoint (mirrors the Phase 1 packaging decision).

Known issues / blockers:
- Frontend not build-verified (no `npm install` run here); charts rendered as tables pending a chart library.
- ML trained on synthetic sample data → metrics are not meaningful; retrain on real `pykrx`/licensed data.
- Market proxy ≠ real KOSPI index; affects outperformance labels/metrics.
- Phase 5 remainder open (scheduling, model registry/drift, alerting, watchlists, security/legal review).

Data/model assumptions introduced:
- Forward targets use adjusted close; tradeable target enters at next open (no look-ahead). Walk-forward embargo = horizon.
- Feature set `ml_v0`: per-group net5/net20/net5_pct_mcap/streak/z60 + price/vol controls + market controls.

Next recommended task:
- Validate the `pykrx` provider against real KOSPI data, load a wider universe and ~5 years of history, then re-run train/predict so ML metrics are meaningful. Build-verify the `apps/web` frontend (`npm install`) and add charts (TradingView Lightweight Charts / ECharts). Then continue Phase 5 (scheduling, model registry + drift monitoring, alerting, watchlists, security/legal review).

---

### 2026-05-29 — Phase 5 hardening substantially completed (MVP scope)

Status:
- Phase 5: substantially completed. Roadmap MVP (Phases 0–5) is now complete for code deliverables.

Summary:
- Implemented the remaining Phase 5 code deliverables on top of the existing daily orchestrator: a job scheduler, an alerting system, a model registry, feature-drift monitoring, user watchlists, deployment hardening (CORS/healthcheck/.dockerignore), and the security + data-licensing + scheduling review docs. Suite grew to 66 tests, all passing.

Completed deliverables:
- Job orchestration with scheduling: `kospi_flow/jobs/scheduler.py` (KST timetable from §5, `due_entries`/`run_entry`/`serve`), CLI `scheduler`, and `infra/cron/kospi-flow.cron`. Daily pipeline already had retry + per-step error capture.
- Data-quality dashboard: `/data-status` endpoint (counts + validation report). `/metadata/data-freshness` already present.
- Model registry + drift: `ml_model_registry` table + `kospi_flow/ml/registry.py` (register/active/list/set_active); `train_and_evaluate` now registers each model and stores a binned feature baseline in the bundle. PSI drift in `kospi_flow/ml/drift.py` persisted to `fact_model_drift_daily` (with a low-sample guard so tiny universes don't false-alert). CLI `drift`, `models`; API `/models`, `/models/{name}/drift`.
- Alerting: `kospi_flow/alerts/` — `Notifier` abstraction (console/file/webhook/null) + rule engine (validation failure, drift alert/warning, watchlist large-flow), dispatched at the end of the daily pipeline via the configured channel.
- User watchlists: `watchlist`/`watchlist_item` tables + `kospi_flow/api/routers/watchlists.py` (create/list/get/delete, add/remove items, `/flows` summary).
- Deployment hardening: CORS middleware (configurable `KOSPI_CORS_ORIGINS`), Docker healthcheck + optional scheduler service, `.dockerignore`, API version 0.3.0.
- Review docs: `docs/SECURITY.md`, `docs/DATA_LICENSING.md`, `docs/SCHEDULING.md`.

Files/modules created or changed:
- New: `kospi_flow/alerts/{__init__,notifier,rules}.py`, `kospi_flow/ml/{registry,drift}.py`, `kospi_flow/jobs/scheduler.py`, `kospi_flow/api/routers/{watchlists,models}.py`, `tests/test_phase5.py`, `infra/cron/kospi-flow.cron`, `.dockerignore`, `docs/{SECURITY,DATA_LICENSING,SCHEDULING}.md`.
- Changed: `core/models.py` (+4 tables), `core/config.py` (alert/drift/CORS settings), `ml/train.py` (registry + baseline), `jobs/daily.py` (drift + alerts steps), `api/app.py` (CORS + new routers), `api/schemas.py`, `cli.py` (drift/models/scheduler commands), `infra/docker/docker-compose.yml`, `.env.example`, `tests/test_models.py`.

Tests/checks completed:
- `python -m pytest` → 66 passed.
- CLI verified: `train`→registers model; `models` lists it; `drift` computes PSI; `daily` runs ingest→features→predict→drift→validate→alerts (file notifier wrote a drift alert).
- TestClient: watchlist CRUD + flows, `/models`, `/models/{name}/drift`, CORS allow-origin reflects config, 25 API paths registered.

Important decisions:
- PSI drift suppressed below `min_rows` (default 200) → `low_sample` status, since PSI is unreliable on small samples (the 3-stock demo universe). A production-width universe exceeds this easily.
- Watchlists are unauthenticated in the MVP (name is the key); auth deferred (documented in SECURITY.md).
- Scheduler is dependency-free (stdlib loop + crontab) for the MVP; migrate to Airflow/Prefect for production SLAs.

Known issues / blockers:
- Same as prior entry: ML metrics on synthetic data are placeholders; market benchmark is a proxy; frontend not build-verified.
- New: drift PSI needs a wide universe to be meaningful; no API auth/rate-limiting yet; licensed feed + MLflow + Airflow/Prefect are future work.

Data/model assumptions introduced:
- Model bundles now carry `feature_baseline` (per-feature decile edges + reference proportions) for drift scoring.

Next recommended task:
- See §20 (updated): integrate a real/licensed data feed and real KOSPI index, build-verify the frontend with charts, then add API auth + migrate scheduling to Airflow/Prefect and the registry to MLflow.

---

### 2026-05-31 — pykrx provider validated against live KRX + hardened

Status:
- In progress on §20 step 1 (real data). pykrx provider validated and hardened; full real-data ingestion is **partially blocked by KRX endpoint availability** from this environment (see below).

Summary:
- Installed `pykrx` 1.2.8 and exercised it against the live KRX API. Confirmed the OHLCV endpoint works and returns real KOSPI prices; the market-cap, investor trading value/volume, and foreign-holding endpoints return empty/blocked responses from this environment (KRX rate-limits and commonly blocks non-Korean/datacenter IPs for those endpoints). Also found a real provider bug: `get_market_ohlcv` returns no `거래대금` column, so the old `float(r.get("거래대금"))` would have crashed.
- Rewrote `kospi_flow/data/providers/pykrx_provider.py` to be production-robust: None/NaN-safe numeric coercion (`_safe_float`), a retry-with-backoff wrapper (`_fetch`) that tolerates empty/blocked responses and returns `[]` instead of crashing, derivation of `trading_value = close × volume` when `거래대금` is absent, and graceful per-endpoint degradation (e.g., prices still ingest when the cap endpoint is blocked).
- Added 9 offline mock-based tests (`tests/test_pykrx_provider.py`) pinning the column mappings and degradation behavior. Verified live: `get_price_daily('005930', 2024-01-02..05)` returned 4 real rows (close 79,600; trading_value derived = ₩1.36T; market_cap None; flows [] — all graceful).

Completed deliverables:
- Validated pykrx column mappings against real API; fixed the 거래대금/None-coercion bugs.
- Hardened provider (retry/backoff, safe coercion, derived trading value, graceful empties).
- Offline test coverage (no network needed in CI).

Files/modules changed:
- `kospi_flow/data/providers/pykrx_provider.py` (rewritten), `tests/test_pykrx_provider.py` (new). Suite: 66 → 75 passing.

Important findings / decisions:
- KRX investor-flow/cap/foreign endpoints are not reliably reachable from this environment → real end-to-end ingestion needs a Korean-IP host or a licensed feed. The provider is now correct and robust for when it runs there.
- Provider degrades gracefully and logs warnings rather than failing the pipeline (consistent with §19.1 "do not silently drop rows" — drops are logged/counted).

Known issues / blockers:
- Full real-data backfill (cap, investor flows, foreign holdings) blocked by KRX endpoint access from here; OHLCV-only is reachable.
- `trading_value` derived as close×volume when 거래대금 missing is an approximation (documented in the provider).

Next recommended task:
- Run the hardened pykrx ingestion from a Korean-IP host (or wire a licensed feed) to backfill cap/flows/foreign; OR proceed to §20 step 2 (real KOSPI index data path) and step 3 (frontend build), which are not blocked by KRX access.

---

### 2026-05-31 — Step 2: market-index data path + benchmark (real index vs proxy)

Status:
- Completed (vendor-neutral infrastructure). Real index *numbers* are blocked from this environment (pykrx index endpoint is IP-blocked like cap/flows), but the system is now index-ready and uses a real index automatically once one is ingested.

Summary:
- Replaced the cap-weighted "market proxy" as the single benchmark with a proper market-index data path: a `fact_index_daily` table, an `IndexRow` provider method (sample synthesizes a deterministic KOSPI index; pykrx maps `get_index_ohlcv` with the same hardening; licensed stub added), ingestion of the benchmark index, and a benchmark layer that **prefers the real index and falls back to the proxy** when no index has been ingested. ML outperformance labels, analytics event studies, and the market API now consume this benchmark.

Completed deliverables:
- `fact_index_daily` table (PK date+index_code) + Alembic baseline coverage + schema test.
- `MarketDataProvider.get_index_ohlcv` (default returns []); `supports_index` flag. Sample provider generates `1001`=코스피; pykrx provider maps the real endpoint; licensed stub raises NotImplemented.
- `Ingestor.ingest_index` + `run(include_index=...)` ingests the configured `benchmark_index_code` (default 1001); CLI `ingest --no-index`; `index_rows` in the run summary.
- `analytics/market.py`: `load_index_series`, `has_index`, `index_return_series`, `index_level_series`, and the benchmark API — `benchmark_return_series`, `benchmark_index_level`, `benchmark_source` (returns `index:<code>` or `proxy`).
- Wiring: `ml/dataset.py` outperformance label and `analytics/service.py` event-study market returns now use `benchmark_index_level`; `GET /market/overview` reports `benchmark_source` + `index_level`; new `GET /market/index` returns the benchmark series (real index, else proxy level).
- Config: `benchmark_index_code` setting (default 1001).

Files/modules changed:
- New: `tests/test_index.py`. Changed: `core/models.py`, `core/config.py`, `data/providers/{base,sample,pykrx_provider,licensed,__init__}.py`, `data/ingestion.py`, `analytics/market.py`, `analytics/service.py`, `ml/dataset.py`, `api/routers/market.py`, `cli.py`, `tests/{test_models,test_pykrx_provider}.py`. Suite: 75 → 84 passing.

Tests/checks completed:
- `python -m pytest` → 84 passed.
- Offline CLI smoke (sample): ingest reported `index_rows=260`; `benchmark_source=index:1001`; benchmark series equals the index (not the proxy); 260 index level points.
- Confirmed graceful fallback: with no index ingested (`--no-index`), `benchmark_source=proxy` and the benchmark equals the cap-weighted proxy.

Important findings / decisions:
- pykrx KOSPI **index** endpoint (`get_index_ohlcv`/`get_index_ticker_list`) is ALSO IP-blocked from this environment — only plain stock OHLCV is reachable. So real index data needs a Korean-IP host or a licensed feed, same as cap/flows/foreign.
- Benchmark prefers the real index and silently falls back to the proxy, so behavior is correct today (proxy) and upgrades automatically when index data arrives.

Known issues / blockers:
- Real KOSPI index numbers blocked here (use sample index offline; real needs Korean-IP host or licensed feed).
- Sample index is synthetic and independent of the universe (intentional, so tests prove the index path is used over the proxy).

Next recommended task:
- DATA SOURCING DECISION NEEDED (see §20 / message to user): pick how to obtain real KRX data (Korean-IP host for pykrx, or a licensed feed such as KIS Developers / Koscom with credentials). Until then, the remaining non-blocked work is §20 step 3 (frontend build + charts, incl. the new `/market/index` overlay).

---

### 2026-05-31 — Data-sourcing decision + Korean-host backfill tooling

Status:
- Decision made by user: **run pykrx from a Korean-IP host** (no API key). Tooling + runbook delivered to make that turnkey. Real backfill itself runs on the user's KR host (cannot execute from this environment).

Summary:
- To make the real backfill reliable on a Korean host, added KRX-call pacing and a restartable chunked backfill (the one live failure mode observed was KRX rate-limiting → empty responses), plus a step-by-step runbook.

Completed deliverables:
- `KOSPI_PYKRX_REQUEST_DELAY` setting (default 0.3s); `PykrxProvider` paces every KRX call via `_fetch(pace=...)` to avoid rate-limit empties.
- `Ingestor.backfill(start, end, chunk_days=365, ...)` + `chunked_date_ranges` helper: ingests in date chunks, idempotent/restartable (upsert on PK), per-chunk progress logging. CLI `backfill` command.
- `docs/REAL_DATA.md`: Korean-host runbook (prereqs, reachability smoke-test, full backfill, features/train/predict, troubleshooting). Referenced from README.

Files/modules changed:
- `core/config.py` (+pykrx_request_delay), `data/providers/pykrx_provider.py` (pacing via `_get`/`_fetch`), `data/ingestion.py` (+backfill, +chunked_date_ranges), `cli.py` (+backfill), `tests/{test_backfill.py(new),test_pykrx_provider.py}`. Suite: 84 → 89 passing.

Tests/checks completed:
- `python -m pytest` → 89 passed. Offline CLI backfill smoke: 4 chunks, aggregated counts correct, re-run idempotent. Pacing unit-tested (delay sleeps before KRX calls).

Important findings / decisions:
- Backfill is the recommended path for wide/multi-year real loads (resumable + paced); `ingest` remains for small/targeted runs.

Known issues / blockers:
- The actual real-data load must run on the user's Korean-IP host; this environment can only reach stock OHLCV. Nothing further is code-blocked.

Next recommended task:
- After the user backfills real data on their KR host: re-run features/train/predict/drift (metrics become meaningful), then §20 step 3 (frontend build + charts).

---

### 2026-06-01 — pykrx live test from US IP: blocked; log noise + test hermeticity fixed

Status:
- Confirmed the KRX data-portal block affects the user's US IP too (only OHLCV reachable). Fixed two real code issues exposed in the process.

Summary:
- User ran the smoke test from a US IP → `stocks=0 price_rows=22 flow_rows=0 foreign_rows=0 index_rows=0`. Same split as this environment: KRX MDC endpoints (`data.krx.co.kr`: ticker list, cap, investor flows, foreign holdings, index) are IP-blocked; only Naver-backed OHLCV works. Conclusion: a Korean IP (VPN/VPS) is required; US IP is not viable for the data the project needs. KRX_ID/KRX_PW (free KRX account) is unlikely to help since even the first/no-pressure call returns empty (IP block, not rate-limit).
- Fixed pykrx log-spam: pykrx calls `logging.info(args, kwargs)` malformed on every failed request, making Python emit a multi-line `--- Logging error --- TypeError` per failure. `core/logging.py` now routes our logs through a dedicated `kospi_flow` logger (propagate=False) and holds the root logger at WARNING, so third-party INFO spam (and the broken-format tracebacks) never emit. Verified: 0 traceback blocks, clean WARNING/INFO output.
- Fixed test hermeticity: a real `.env` (created for the live backfill, `KOSPI_DATA_SOURCE=pykrx`) leaked into pytest via pydantic-settings, breaking `test_config.test_defaults` and `test_jobs.test_daily_pipeline_runs_with_training`. `tests/conftest.py` now disables `.env` loading at import time (`Settings.model_config["env_file"]=None`) so the suite depends only on code defaults + explicit values.

Files/modules changed:
- `kospi_flow/core/logging.py` (dedicated package logger; root held at WARNING), `tests/conftest.py` (hermetic against local `.env`).

Tests/checks completed:
- `python -m pytest` → all passing with a real `.env` present. Reproduced the clean (noise-free) failure output here.

Known issues / blockers:
- Unchanged: real-data load needs a Korean IP. US IP confirmed blocked for KRX MDC endpoints.

Next recommended task:
- User connects via a Korean VPN/VPS, re-runs the smoke test (expect `flow_rows>0` & `foreign_rows>0`), then runs the backfill. Then features/train/predict and §20 step 3 (frontend).

---

### 2026-06-01 — KRX access working on KR route; resumable backfill added

Status:
- Real data confirmed flowing (user reached KR access + KRX login: 948 stocks, real flows/foreign/index). Made the backfill resumable to survive the pykrx 1-hour KRX-login token expiry.

Summary:
- User's KRX login token is valid 1 hour (`로그인 09:45 / 만료 10:45`); a multi-hour single-process backfill would stall when it expires. Reworked `backfill` to be **checkpoint-resumable per ticker**: re-running the identical command skips already-done tickers and continues, so the user just re-logs-in and re-runs until complete. Also fixed pykrx log-spam (root logger held at WARNING) and test hermeticity vs a real `.env` (conftest disables env-file loading) in the prior step.

Completed deliverables:
- New `ingestion_checkpoint` table (PK scope_key+ticker; status done/empty/skipped). `Ingestor.backfill` rewritten: per-ticker full-range fetch, checkpoint keyed by `<start>:<end>`, skips done/skipped, retries empties up to `max_empty_attempts`, `restart=True` to clear. Dropped date-chunking (per-ticker is the resume unit; fewer KRX calls per run). CLI `backfill` gains `--restart`, drops `--chunk-days`.
- Tests: `tests/test_backfill.py` rewritten for resume/skip/restart behavior; `test_models.py` updated. Suite 89 → 91 passing.
- `docs/REAL_DATA.md` updated: "re-run the same command to resume" workflow; use FIXED dates so the scope is stable.

Important decisions:
- Resume granularity is per ticker over the full date range (not date chunks) — minimizes calls per run so more tickers complete within one 1-hour token window; completion signal is `price_rows>0`.
- Backfill scope = `(start, end)`; re-runs MUST use identical literal dates (not "today") to resume.

Known issues / blockers:
- Real-data load runs on the user's KR host only; this env reaches OHLCV only. Token expiry handled via resumable re-runs (or a future auto-refresh in the provider if pykrx exposes a re-login call).

Next recommended task:
- User runs `backfill --start 2019-01-01 --end <fixed today>` repeatedly (re-login between runs) until 0 pending; then features/train/predict/drift; then §20 step 3 (frontend + charts).

---

### 2026-06-02 — Frontend build-verified with charts (§20 step 3 done)

Status:
- Completed. The user had finished the real-data backfill + features/train/predict and the API was serving real KOSPI data; built out the Next.js frontend with real charts and verified it compiles.

Summary:
- Turned the `apps/web` scaffold (which rendered tables and was never build-verified) into a working charted app using **Apache ECharts**. `next build` compiles cleanly (8 routes, no type errors). Also added a `serve` CLI command earlier this session (uvicorn shim wasn't on PATH).

Completed deliverables:
- Client `EChart` wrapper (`components/EChart.tsx`, dark theme) + chart components: `PriceChart` (candlestick + volume + MA5/20/60 + datazoom), `FlowChart` (개인/기관/외국인 daily-bars ↔ cumulative-lines toggle, in 억), `ForeignChart` (보유비율 line + 보유량 dual-axis), `IndexChart` (benchmark level).
- Stock-detail page (`/stocks/[ticker]`) rebuilt around the charts + ML projection table; server component fetches price/flows/foreign/projection and passes to client charts.
- Market overview (`/`) now shows the real-vs-proxy benchmark + index level chart.
- New pages: `/models` (registry metrics: IC/ICIR/RMSE/AUC, active flag) and `/data-status` (counts + freshness + coverage-warning note). Nav updated.
- `lib/api.ts` extended (marketIndex, price range, models, dataStatus, dataFreshness). `echarts` added to package.json; `.gitignore` updated for `apps/web/.next`/`node_modules`/`.env.local`.

Files/modules changed:
- New: `apps/web/components/EChart.tsx`, `components/charts/{PriceChart,FlowChart,ForeignChart,IndexChart}.tsx`, `app/models/page.tsx`, `app/data-status/page.tsx`. Changed: `app/page.tsx`, `app/stocks/[ticker]/page.tsx`, `app/layout.tsx`, `lib/api.ts`, `package.json`. Backend: `kospi_flow/cli.py` (+`serve`).

Tests/checks completed:
- `npm install` + `npm run build` → compiled successfully, all 8 routes, no type errors (chart pages ~424 kB first-load as expected). Built without the API running (pages are dynamic / `no-store`).
- Python suite still 91 passing (after the `serve` command addition).

Known issues / blockers:
- Frontend build-verified here but not run end-to-end against the live API from this environment (no DB here) — the user runs it against their populated DB.

Next recommended task:
- Run the frontend against the live API, then §20 step 4 — production maturity.

---

### 2026-06-02 — Frontend polish: rankings/screener charts + watchlists page

Status: completed; `next build` clean (9 routes, no type errors).

- New reusable `components/charts/RankBarChart.tsx` (horizontal net-buy bar, green/red by sign). Wired into `/rankings` (top-20 bar above the table) and `/screener` (results bar).
- New `/watchlists` page (client): list / create / delete watchlists, add / remove tickers, and a recent-5-day net-buy-by-group table per list. `lib/api.ts` extended with watchlist CRUD + a DELETE helper; nav updated.
- Frontend MVP is now feature-complete: overview + index, stock detail (price/flow/foreign/ML), rankings, screener, watchlists, models, data-status.

Next recommended task:
- §20 step 4 — production maturity (licensed feed, Airflow/Prefect scheduling, API auth + rate-limit + TLS, MLflow registry + retrain-on-drift, real alert channels, legal/data-license sign-off).

---

### 2026-06-02 — Flow→price relationship surfaced per stock (+ quintile analysis)

Status: completed; Python suite green, `next build` clean (9 routes).

Summary:
- Made the buying-pressure → subsequent-return relationship legible per stock. Added the requested **quintile analysis** (forward return by trailing net-buy strength) and a stock-page analytics section combining it with the existing correlation grid and event studies.

Completed deliverables:
- Backend: `analytics/profile.py::flow_return_profile` — buckets each group's trailing net-buy %mcap into quintiles (Q1 순매도 … Q5 순매수) and reports mean/median forward return + hit rate per horizon (no look-ahead, rank-based qcut). `monotonicity()` = Spearman(quintile, mean return) summarising whether buying leads price. Service `stock_flow_return_profile` + endpoint `GET /stocks/{ticker}/flow-return-profile?flow_window=5`.
- Frontend: new `components/charts/{CorrelationHeatmap,QuintileChart,EventStudy}.tsx` and a "매수세 → 향후 수익률 관계" card on the stock page = ① Spearman heatmap (investor × horizon), ② quintile mean-return bars (group/horizon toggles), ③ event-study table (signal selector, client-fetched), + plain-language takeaways derived from 5d/5d Spearman. `lib/api.ts` extended (correlations/events/flowReturnProfile).
- Tests: `test_analytics.py` (+structure + monotonic-relationship detection), `test_api.py` (+endpoint). Suite 91 → 94 passing.

Files changed:
- New: `kospi_flow/analytics/profile.py`, `apps/web/components/charts/{CorrelationHeatmap,QuintileChart,EventStudy}.tsx`. Changed: `analytics/service.py`, `api/routers/analytics.py`, `app/stocks/[ticker]/page.tsx`, `apps/web/lib/api.ts`, tests, README.

Notes / interpretation guidance baked into UI:
- Q1→Q5 rising mean return ⇒ buying pressure leads price for that name; flat/declining ⇒ weak or contrarian (esp. 개인). All framed as past statistical tendency, not causation; low-`n` cautioned.

Next recommended task:
- §20 step 4 — production maturity (unchanged list).

---

### 2026-06-02 — Main page: today's top ML picks + stock search

Status: completed; Python suite green, `next build` clean (9 routes).

Summary:
- Reworked the home page: replaced the full ~948-row stock list with a **search box**, and added a **"오늘의 주목 매수"** leaderboard = today's highest ML-projected-return stocks among those with recent notable buying.

Completed deliverables:
- Backend `GET /market/top-picks?horizon&limit&lookback_days&notable_only`: takes the latest prediction date for the horizon, ranks by `predicted_return` desc, and (when `notable_only`) keeps only stocks with 외국인+기관 net buy > 0 over the lookback window; returns name, predicted_return, predicted_price, prob_outperform_kospi, and recent foreign/institution/retail net buy. Added `_trailing_dates` helper.
- Frontend: `components/TopPicks.tsx` (client; horizon dropdown + notable-only toggle, refetches) and `components/StockSearch.tsx` (client; filters the full list by ticker/name, top-30). Home page (`app/page.tsx`) now = overview + TopPicks + StockSearch + index chart. `lib/api.ts` +`topPicks`.
- Tests: `test_ml.py::test_top_picks_endpoint` (ranking + structure, with predictions present). Suite 94 → 95 passing.

Notes:
- "for today" = latest stored prediction date. LightGBM is now installed in the dev env, so models auto-use it (benign sklearn "no valid feature names" warnings when predicting from arrays).

Next recommended task:
- §20 step 4 — production maturity (unchanged list).

---

### 2026-06-02 — Frontend polish: sparklines, add-to-watchlist, global search

Status: completed; Python suite green, `next build` clean (10 routes).

- **Sparklines**: new `GET /market/closes?tickers=&days=` (batch recent closes, one query) + `components/charts/Sparkline.tsx` (axis-less mini line, green/red by net change). Wired into the Top Picks leaderboard (추세 20일 column; closes fetched client-side after rows load).
- **Add-to-watchlist**: `components/AddToWatchlist.tsx` on the stock-detail header — pick an existing list or create one and add the current ticker (connects the previously-isolated watchlists feature to browsing).
- **Global search**: a GET search form in the nav → new server `/search?q=` page (filters the universe by ticker/name/en, top-100). Search now works from every page, not just home.
- Tests: `/market/closes` + empty `/market/top-picks` (no-predictions case). Suite 95 → 97 passing. README endpoint list updated.
- Follow-up increment (same day): extended **sparklines to `/rankings` and `/watchlists` rows** (reusing `Sparkline` + `/market/closes`), and added a **`FreshnessBadge`** in the nav (latest price date + freshness state, fetched client-side). `next build` clean (10 routes); no backend change so suite unchanged at 97.

Next recommended task:
- §20 step 4 — production maturity (unchanged list).

---

### 2026-06-02 — Deployment prep (Vercel frontend + Render backend + Postgres)

Status: completed (config + tooling); actual cloud deploy requires the user (GitHub repo, Render/Vercel projects, data load). Suite green, frontend unaffected.

Architecture decision: **split deploy** — Vercel hosts only the Next.js frontend (it can't run this pandas/ML backend or hold the ~2 GB DB on serverless). Backend (FastAPI) → Render/Railway/Fly; DB → managed Postgres (Render/Neon/Supabase); pykrx ingestion stays on the Korean-IP host writing to the hosted Postgres.

Completed deliverables:
- **Packaging fix (deploy-blocking):** core deps were missing fastapi/uvicorn/scipy/scikit-learn/joblib (only preinstalled in dev). `pyproject.toml` now declares the full runtime set; added extras `[postgres]` (psycopg3), `[lightgbm]`; version → 0.3.0.
- **DB URL normalization:** `core/db.normalize_db_url` rewrites platform `postgres://`/`postgresql://` → `postgresql+psycopg://` so Render/Neon DSNs work out-of-the-box.
- **`serve` honors `$PORT`** (default None → $PORT or 8000) for container hosts; `--host 0.0.0.0` for deploy.
- **`copy-db` CLI + `jobs/migrate.copy_database`:** copy all tables across DBs (SQLite → Postgres) in FK order, batched. For pushing the local dataset to prod.
- **Deploy configs:** `Procfile`, `render.yaml` (web + free Postgres blueprint), Dockerfile now copies `apps/`, installs `[postgres]`, and binds `$PORT`. `docs/DEPLOYMENT.md` (full split-deploy runbook + "what you must do").
- Tests: `test_migrate.py` (URL normalization + cross-SQLite copy). Suite 97 → 99 passing.

User-side actions (documented in DEPLOYMENT.md): push to GitHub; Render blueprint → API URL + Postgres (pick a plan ≥ data size, or Neon/Supabase); load data from KR host (`copy-db` or ingest directly to prod); Vercel import with Root Directory `apps/web` + `NEXT_PUBLIC_API_BASE`; set `KOSPI_CORS_ORIGINS` to the Vercel domain.

Known issues / blockers:
- API is unauthenticated — add auth before public exposure (SECURITY.md). Free Render Postgres ~1 GB < full dataset. Render free web idles (cold starts).

Next recommended task:
- §20 step 4 — production maturity (auth/rate-limit/TLS first, given public exposure).

---

### 2026-06-02 — Real data loaded; deploying to Railway (backend) + Vercel (frontend)

Status: in progress. Backend + Postgres are LIVE on Railway after iterative deploy fixes; frontend on Vercel is being wired up by the user.

**Repo / git:** code is on GitHub at `https://github.com/HajinHyukson/Acquin.git` (remote `origin`, **HTTPS**, branch `main`). Commit identity `FaustCalc <hajinson1346@gmail.com>` (the machine's global git config; HTTPS creds are cached so `git push` works non-interactively). Latest commits this session: deploy config + the Railway fixes below (HEAD ≈ `f24d411`). A new session CAN push (init already done; `git push` works).

**Real data:** the user backfilled real KOSPI data on their **Korean-IP host** (pykrx) — 948 stocks, ~1.64M price rows, ~4.85M investor-flow rows, foreign holdings, real KOSPI index; ran features/train/predict (LightGBM auto-selected; it's installed on their host). So `train`/`predict`/analytics now run on real data there. The hosted Postgres on Railway is **separate** and must be loaded via `copy-db` from the KR host (or by pointing ingestion at it).

**Railway deploy — fixes applied (each pushed to GitHub):**
- `requirements.txt` added (Nixpacks installs from it) — fixed `ModuleNotFoundError: numpy` (Nixpacks ignored pyproject; Railway only auto-detects a root Dockerfile, ours is nested).
- `railway.json` → builds from `infra/docker/Dockerfile`; `.railwayignore` keeps the 2 GB DB / node_modules / `.env` out of uploads.
- Dockerfile: removed `VOLUME` (Railway rejects it), dropped the hardcoded SQLite default, `/app/data` fallback dirs created, copies `apps/`.
- `serve` start command: removed `--port` (Railway passed a literal un-expanded `$PORT`). Added `cli.resolve_port()` which reads the `PORT` env and tolerates a literal `$PORT`/`${PORT}` — so it works regardless of how the platform invokes it (`Procfile`/Dockerfile/dashboard custom start). Tests in `test_cli_serve.py`.
- `config._default_database_url` adopts a platform-provided `DATABASE_URL` when `KOSPI_DATABASE_URL` is unset; `db.normalize_db_url` rewrites `postgres://`→`postgresql+psycopg://`.

**Current live state:** Railway web service healthcheck (`/health`) green; Postgres provisioned. The user must still: set `KOSPI_DATABASE_URL=${{Postgres.DATABASE_URL}}` on the web service (verify), `copy-db` the data into that Postgres, generate the public domain, and remove any leftover dashboard **Custom Start Command** (the code now tolerates it, but cleaner to clear it so the Dockerfile CMD `serve --host 0.0.0.0` is used).

**Vercel (frontend) — in progress, steps given to user:** import `HajinHyukson/Acquin` → **Root Directory `apps/web`** → env `NEXT_PUBLIC_API_BASE = <Railway public URL>` → deploy → then set `KOSPI_CORS_ORIGINS` on Railway to the Vercel domain.

Tests: suite was green at 101; `test_cli_serve.py` adds 4 (serve port resolution) → ~105. (Full suite not re-run after the last cli edit; `test_cli_serve` + `test_config` pass.)

Known issues / blockers (deploy):
- **API is unauthenticated** — once the Railway/Vercel URLs are public anyone can read/modify watchlists. Recommended next: add API-key auth + rate limiting (offered, user hasn't accepted yet).
- Railway Postgres may be **empty** until the user runs `copy-db` (or ingests to it) — frontend shows 0 stocks / "예측 데이터 없음" until then.
- Verify `KOSPI_DATABASE_URL` is actually set on the Railway web service, else it serves an ephemeral SQLite.
- Railway is usage-billed (no permanent free tier).

Next recommended task:
- Help the user finish Vercel + verify prod data flow (CORS, `NEXT_PUBLIC_API_BASE`, `copy-db` into Railway Postgres), then **add API auth + rate limiting** (§20 step 4) before the app is shared. Then the rest of §20 step 4 (Airflow/Prefect, MLflow, real alert channels, legal sign-off).

---

### 2026-06-03 — Production split deploy verified (Railway + Vercel)

Status:
- Completed. The production frontend, backend API, and Postgres-backed data path are live and verified.

Current deployment structure:
- **Frontend:** Vercel, production domain `https://acquin.vercel.app`.
- **Backend API:** Railway FastAPI service, production domain `https://acquin-production.up.railway.app`.
- **Database:** Railway Postgres attached to the API service via `KOSPI_DATABASE_URL=${{Postgres.DATABASE_URL}}`.
- **Data/ML source of truth:** real KOSPI data and model artifacts were produced from the user's Korean-IP host; production API reads the populated Railway Postgres. Ongoing pykrx ingestion should still run from a Korean-IP host and write to Railway Postgres.

Working production env wiring:
- Vercel frontend env: `NEXT_PUBLIC_API_BASE=https://acquin-production.up.railway.app` (no trailing slash).
- Railway API service env: `KOSPI_CORS_ORIGINS=https://acquin.vercel.app`, `KOSPI_DATABASE_URL=${{Postgres.DATABASE_URL}}`, `KOSPI_DATA_SOURCE=sample`, `KOSPI_DB_ECHO=false`.
- Railway API service build/deploy: Dockerfile builder, `infra/docker/Dockerfile`, repo root as root directory, no custom start command needed; Dockerfile CMD runs `python -m kospi_flow.cli serve --host 0.0.0.0`.

Verification:
- `https://acquin-production.up.railway.app/health` returns 200 with `{"status":"ok"}`.
- `https://acquin-production.up.railway.app/docs` returns FastAPI Swagger UI.
- `https://acquin-production.up.railway.app/market/overview` returns real prod data (`n_stocks=948`, latest data date observed `2026-06-01`) and sends `Access-Control-Allow-Origin: https://acquin.vercel.app`.
- `https://acquin.vercel.app` successfully calls the Railway API after updating `NEXT_PUBLIC_API_BASE`.

Deployment debugging note:
- Do **not** use `https://web-production-c9e69.up.railway.app` for the frontend API base. It returned Railway fallback 404s (`X-Railway-Fallback`) for `/health`, `/docs`, and `/market/overview`; the correct backend API domain is `https://acquin-production.up.railway.app`.
- Vercel Output Directory must be blank/default for the Next.js app. A prior `public` Output Directory setting caused post-build failure after `Collecting build traces`.

Known issues / blockers:
- API is still unauthenticated and public. Anyone with the API URL can read/modify watchlists. Next priority: add API-key auth + rate limiting before wider sharing.
- Production Postgres is populated now, but ongoing data refresh/retrain needs an operational schedule on the Korean-IP host (or a future licensed/KR-hosted ingestion service).

Next recommended task:
- Add API auth + rate limiting, then continue production maturity: scheduled KR-host ingestion, MLflow/model lifecycle, real alert channels, and legal/data-license sign-off.

---

### 2026-06-03 — Daily auto-refresh design: Railway scheduler service (Option A)

Status:
- In progress. Deploy plumbing for an always-on daily refresh into Railway
  Postgres is committed; activation is gated on a reachability test the user runs
  on Railway, and on getting a model bundle onto Railway for the predict step.

Goal (user request):
- Update the production DB daily **without** populating/storing the DB on a local
  computer and using its disk space.

Key correction to prior assumptions:
- The user reports pykrx now reaches the KRX investor-flow/foreign endpoints from
  **their own machine without a VPN** (contradicts the 2026-06-01 "US IP blocked"
  entries; KRX behavior/their network changed). They want the daily job always-on
  and are not constrained to a Korean address.

Design chosen (Option A):
- Run the existing always-on scheduler (`python -m kospi_flow.cli scheduler`,
  `jobs/scheduler.py`) as a **second Railway service** beside the API. It runs the
  §5 KST timetable and computes the trading date itself from `KOSPI_TIMEZONE`
  (`Asia/Seoul`), so no per-day date args. It writes ingest/features/predictions
  **straight into Railway Postgres** via the internal `${{Postgres.DATABASE_URL}}`
  — no local DB, no `copy-db`. Raw Parquet snapshots are tiny and self-overwriting.

Completed deliverables (this session):
- `infra/docker/Dockerfile.scheduler` — dedicated scheduler image (keeps the live
  API image slim/untouched): installs `.[postgres,pykrx,lightgbm]`, adds
  `libgomp1` (LightGBM OpenMP runtime), defaults `KOSPI_DATA_SOURCE=pykrx` +
  `KOSPI_TIMEZONE=Asia/Seoul`, CMD = `cli scheduler`.
- `infra/railway/scheduler.json` — Railway config-as-code for the scheduler
  service (Dockerfile builder, no healthcheck, restart ON_FAILURE).
- `docs/DAILY_REFRESH_RAILWAY.md` — runbook: the gating KRX-reachability probe,
  service creation + env, and the model-bundle options.

Gating test — RESOLVED 2026-06-03 (Option A verified on Railway):
- Root cause of empty flows was NOT the IP: pykrx 1.2.8 now **requires a KRX
  data-portal login** (`KRX_ID`/`KRX_PW` env vars → `website/comm/auth.py`
  auto-login). Without them, only OHLCV returns; flow/foreign/cap/index/ticker
  endpoints are empty (this machine failed identically — KRX enforced login some
  time after the Jun 1–2 backfill).
- With `KRX_ID`/`KRX_PW` set on the Railway scheduler service (and
  `KOSPI_DATA_SOURCE=pykrx` set service-level to override the project's `sample`),
  the Railway probe returned real data: `stocks=948 price_rows=4 flow_rows=12
  foreign_rows=4`, `KRX 로그인 완료`. So **Railway's IP is not blocked** and Option A
  is the live path (no Option B fallback needed). pykrx auto-re-logins on the
  1-hour token expiry, so the always-on scheduler self-reauthenticates.
- Activation: clear the probe Custom Start Command so the image CMD
  (`cli scheduler`) runs. Required service vars: `KOSPI_DATABASE_URL`,
  `KOSPI_DATA_SOURCE=pykrx`, `KRX_ID`, `KRX_PW` (+ `KOSPI_TIMEZONE` default).
- Index endpoint not yet confirmed under login (probe used `--no-index`); if it
  stays empty the benchmark falls back to the cap-weighted proxy (non-blocking).
Model bundle on Railway (RESOLVED — predictions wired):
- Decision: **commit the trained bundles and bake them into the scheduler image**
  (user chose to train on this machine + commit, not skip). The five LightGBM
  bundles (`gbm_return_{1,3,5,10,20}d.joblib`, ~4.7 MB each, trained 2026-06-02)
  are committed under `models/`; `Dockerfile.scheduler` copies them to
  `/app/data/processed/models/`, so `predict`/`drift` work on first deploy with no
  Volume. (A Volume mounted there would *shadow* the baked-in models — documented.)
- Made the predicted horizons configurable (`KOSPI_PREDICT_HORIZONS`, default
  `1,3,5,10,20`) so the scheduler refreshes **every horizon the frontend Top Picks
  surfaces** daily, not just h=5. `scheduler.run_entry` now reads it.
- Verified the committed `gbm_return_5d` bundle loads with the image's
  lightgbm/sklearn (Pipeline regressor + classifier + P10/P50/P90 + drift baseline,
  23 features). Refresh path: retrain locally → copy to `models/` → commit → redeploy.

Code changed this session:
- `core/config.py` (+`predict_horizons` + `predict_horizon_list`),
  `jobs/scheduler.py` (`run_entry` uses configured horizons),
  `infra/docker/Dockerfile.scheduler` (COPY `models/`), `.env.example`,
  `tests/test_phase5.py` (+2 tests), new `models/` dir (5 bundles + README).
- Suite: **107 passed** (`python -m pytest`).

Next recommended task:
- User runs the STEP 0 reachability probe on Railway. If flows return, finish
  Option A (clear the probe start command — the scheduler then ingests + predicts
  all horizons). If blocked, switch to Option B (same image/command on a
  KRX-reachable host → Railway public Postgres URL). Then API auth + rate limiting.

---

## 17. Decision log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-28 | Treat 개인/기관 position history as cumulative net-buy proxy, not true holdings. | True daily holdings for 개인/기관 are generally not publicly available. This avoids misleading labels. |
| 2026-05-28 | Use official/licensed data sources for production; use pykrx or equivalent only for MVP/prototype if needed. | Reduces data reliability and licensing risk. |
| 2026-05-28 | Use time-based walk-forward validation for ML. | Prevents leakage and reflects real trading use. |
| 2026-05-28 | Use tradeable targets for model evaluation. | Investor data is available after close, so same-day close-to-close targets can be unrealistic for trading. |
| 2026-05-28 | Build transparent event studies before relying on ML. | Users need interpretable historical evidence, not only model predictions. |
| 2026-05-29 | MVP defaults to SQLite + an offline deterministic `sample` provider. | Lets the full pipeline and tests run with no DB server, network, or license; Postgres/TimescaleDB and pykrx/licensed are config swaps. |
| 2026-05-29 | ORM models (`kospi_flow/core/models.py`) are the single schema source of truth; Alembic baseline builds from `Base.metadata`. | Avoids hand-maintained DDL drifting from models; a parity test enforces it. |
| 2026-05-29 | Use `Float`/DOUBLE PRECISION for monetary/volume columns in the MVP. | KRW integer amounts fit exactly in float64; avoids Decimal/float friction. Revisit `Numeric` for exact-precision production. |
| 2026-05-29 | Realize suggested `packages/*` as subpackages of one importable `kospi_flow` package. | Simpler imports/packaging for the MVP while keeping ingestion/analytics/ml concerns separated. |
| 2026-05-29 | Use a cap-weighted market-return proxy as the KOSPI benchmark. | Sample/prototype data has no index series; proxy enables outperformance labels now. Swap for the official KOSPI index in production. |
| 2026-05-31 | Benchmark now prefers the real index (`fact_index_daily`) and falls back to the cap-weighted proxy. | Supersedes the 2026-05-29 proxy-only decision: correct today (proxy) and upgrades automatically once a real KOSPI index is ingested, with no caller changes. |
| 2026-05-29 | ML backend auto-selects LightGBM if installed, else scikit-learn HistGradientBoosting. | Keeps the pipeline runnable without LightGBM while preferring it when available; same Pipeline/imputation either way. |
| 2026-05-29 | Walk-forward embargo equals the prediction horizon. | Prevents training-set forward targets from overlapping the test window (leakage). |
| 2026-05-29 | API business logic lives in `kospi_flow.api`; `apps/api/main.py` is a thin entrypoint. | Keeps the API unit-testable via TestClient and consistent with the Phase 1 packaging choice. |
| 2026-05-29 | Drift uses PSI with a low-sample guard (`min_rows`, default 200 → `low_sample`). | PSI is unreliable on small samples; avoids false drift alerts on narrow universes (e.g., the demo). |
| 2026-05-29 | Dependency-free scheduler (stdlib loop + crontab) for the MVP. | Avoids an Airflow/Prefect dependency now; documented migration path for production SLAs/backfills. |
| 2026-05-29 | Watchlists are unauthenticated (name-keyed) in the MVP. | No user system yet; per-user scoping + auth deferred to a hardening pass (see SECURITY.md). |
| 2026-05-29 | Model registry is a DB table, not MLflow. | Lightweight and dependency-free for the MVP; migrate to MLflow when artifact lineage/serving is needed. |
| 2026-05-31 | pykrx provider degrades gracefully (retry/backoff, returns [] on blocked endpoints) instead of failing. | KRX endpoints are flaky/IP-blocked; the daily pipeline should ingest what it can and log the rest, not abort. |
| 2026-05-31 | Derive pykrx `trading_value` as close×volume when 거래대금 is absent. | pykrx single-ticker OHLCV omits 거래대금; an approximation keeps turnover features populated until a true source is wired. |
| 2026-05-31 | Real data sourced via pykrx on a Korean-IP host (user's choice); paced + chunked backfill added. | No API key needed; KRX endpoints reachable from KR IPs. Pacing avoids rate-limit empties; chunked backfill is resumable for wide multi-year loads. |
| 2026-06-02 | Split deploy: **frontend → Vercel, backend+Postgres → Railway**, ingestion stays on the KR host. | Vercel can't run the pandas/ML backend or hold the ~2 GB DB; Railway runs the Docker image with managed Postgres. User chose Railway over the Render blueprint (`render.yaml` kept as an alternative). |
| 2026-06-02 | `serve` reads `PORT` from env and tolerates a literal un-expanded `$PORT`; start command omits `--port`. | Railway ran the start command without shell expansion, passing `$PORT` literally and crashing argparse. `resolve_port()` makes it robust regardless of builder/start-command source. |
| 2026-06-02 | Adopt platform `DATABASE_URL` + rewrite `postgres://`→`postgresql+psycopg://`. | Railway/Render hand out un-prefixed `postgres://` DSNs; this makes them work without manual edits and with psycopg3. |
| 2026-06-03 | Production API base is `https://acquin-production.up.railway.app`; Vercel production frontend is `https://acquin.vercel.app`. | The earlier `web-production-c9e69.up.railway.app` Railway domain returned fallback 404s and was not the working API service route. Vercel must use the verified Railway API domain in `NEXT_PUBLIC_API_BASE`; Railway CORS must allow the Vercel production origin. |
| 2026-06-03 | Daily refresh = a **second Railway service** running `cli scheduler`, writing to Postgres via the internal `${{Postgres.DATABASE_URL}}`; its own image (`Dockerfile.scheduler`) with pykrx/lightgbm so the slim API image is untouched. | Satisfies "update Postgres daily without a local DB/space": the scheduler writes straight to Postgres and computes the KST date itself (no per-day args, no `copy-db`). Gated on confirming KRX is reachable from Railway's datacenter IP. |
---

## 18. Known issues and technical debt

| Issue | Status | Notes |
|---|---|---|
| Production data source not finalized | Open | Need to choose KRX/Koscom/KIS/vendor source and confirm license. |
| Corporate-action adjustment method not finalized | Open | Required before reliable ML/backtesting. |
| Historical delisted-stock coverage not finalized | Open | Needed to reduce survivorship bias. |
| Sector classification source not finalized | Open | Needed for sector-relative features. |
| Foreign-holding availability by date/source not verified | Confirmed unreachable here | pykrx foreign-exhaustion endpoint returns empty/blocked from this environment (2026-05-31). Provider handles it gracefully; needs Korean-IP host or licensed feed. |
| KRX investor-flow/cap endpoints blocked from this env | Open | pykrx OHLCV works; cap + investor trading value/volume return empty (KRX IP/rate limits). Real backfill needs a Korean-IP host or licensed feed. |
| pykrx trading_value derived (close×volume) | Open | `get_market_ohlcv` lacks 거래대금; derived value is an approximation until a source provides true 거래대금. |
| Preferred-share/ETF/SPAC exclusion rules not finalized | Open | Required for clean screeners. `dim_stock.is_preferred` exists but exclusion logic is not yet applied. |
| Sample provider data is synthetic | Open (by design) | Must never be shown to users as real data; use `pykrx`/`licensed` for real data. |
| Sample trading calendar ignores KR market holidays | Open | Uses Mon–Fri business days; real providers carry the true calendar. |
| Monetary columns use Float not Numeric | Open | Acceptable for MVP; revisit for exact-precision KRW in production Postgres. |
| ML metrics computed on synthetic data | Resolved in prod | Real data backfilled + models retrained on the user's Korean-IP host; Railway production API now serves populated real-data Postgres. |
| KOSPI benchmark is a cap-weighted proxy | Resolved (path); data blocked | Index data path built (`fact_index_daily` + benchmark prefers real index, falls back to proxy). Real index numbers still blocked from this env — needs Korean-IP host or licensed feed. |
| Real KRX index endpoint blocked from this env | Open | pykrx `get_index_ohlcv`/`get_index_ticker_list` IP-blocked here (2026-05-31), like cap/flows. Sample index works offline. |
| Frontend not build-verified | Resolved | `apps/web` is a full Next.js + ECharts app, `next build` clean (10 routes), deployed on Vercel at `https://acquin.vercel.app`. |
| Phase 5 hardening incomplete | Mostly resolved | Scheduling, registry, drift, alerting, watchlists, security + licensing review docs now done. Remaining: licensed feed, Airflow/Prefect, API auth, MLflow. |
| API has no authentication/rate limiting | Open — **live-deploy blocker** | Railway/Vercel URLs are public; anyone with the URL can read/modify watchlists. Add API-key auth + rate limiting next (see docs/SECURITY.md). |
| Railway prod Postgres may be empty | Resolved | Production API returns real populated data (`n_stocks=948`, latest observed data date `2026-06-01`) through Railway Postgres. Ongoing refresh still needs a KR-host schedule or licensed ingestion path. |
| Preferred-share exclusion only | Open | Screener excludes preferred shares; ETF/SPAC/REIT exclusion still needs an instrument-type field/source. |
| KRX requires login (KRX_ID/KRX_PW) | Resolved 2026-06-03 | pykrx 1.2.8 auto-logs into the KRX data portal via `KRX_ID`/`KRX_PW`; without them flow/foreign/cap/index/ticker endpoints return empty (only OHLCV). Confirmed on this machine AND Railway. With creds set, the Railway probe returned real data (stocks=948, real flows/foreign), so Railway's IP is NOT blocked — Option A is live. The earlier "US IP blocked" note (2026-06-01) is superseded: it was the missing login, surfaced once KRX enforced it. |
| Model bundle absent on Railway containers | Resolved | Five LightGBM bundles committed under `models/` and baked into the scheduler image (`Dockerfile.scheduler` → `/app/data/processed/models/`); scheduler predicts all horizons in `KOSPI_PREDICT_HORIZONS` (default 1,3,5,10,20). Do NOT mount a Volume at `/app/data/processed` (it would shadow them). Refresh = retrain locally → copy to `models/` → commit → redeploy. |

---

## 19. Coding standards and implementation rules

### 19.1 General rules

- Prefer explicit, readable code over clever abstractions.
- Keep ingestion, cleaning, feature generation, analytics, ML, API, and frontend concerns separated.
- Store raw source data before transforming it.
- Make every job idempotent where practical.
- Add timestamps and source metadata to all data rows.
- Add tests for transformations and feature calculations.
- Do not silently drop rows; log and count dropped rows.
- Be explicit about time zones. Market/data timestamps should use Korea time where relevant.

### 19.2 Data rules

- Use `ticker + date` as core keys.
- Use adjusted prices for ML return labels.
- Use raw prices for user display where appropriate.
- Store both amount-based and volume-based investor flows.
- Normalize investor flows by market cap, shares outstanding, and trading value.
- Maintain data freshness states.
- Include source and ingestion timestamp.

### 19.3 ML rules

- Never use random train/test split as the primary validation method.
- Never train with future data.
- Use only features available by the prediction timestamp.
- Report baseline model performance before advanced model performance.
- Store model version, feature version, and prediction generation timestamp.
- Show uncertainty and confidence; avoid deterministic “guaranteed price” language.

### 19.4 UI wording rules

Use labels carefully:

```text
개인 순매수
기관 순매수
외국인 순매수
개인 누적 순매수
기관 누적 순매수
외국인 누적 순매수
외국인 보유량
외국인 보유비율
```

For 개인/기관 cumulative charts, include a small note:

```text
누적 순매수는 실제 보유량이 아닌 기준일 이후 순매수 누적값입니다.
```

---

## 20. Next coding-agent task brief

Use this brief to start the next coding-agent session.

```text
You are working on the KOSPI Investor Flow Intelligence Platform.

Read this context doc first (esp. the 2026-06-02 progress entries). The Phases
0–5 MVP is CODE-COMPLETE and the app is DEPLOYED. ~105 tests
(`python -m pytest`; last full run green at 101, +4 serve-port tests).

WHAT EXISTS
- Backend: kospi_flow.{core,data,analytics,ml,api,jobs,alerts}. FastAPI
  (apps.api.main:app) — stocks/market/screeners/analytics/projection/status/
  watchlists/models endpoints + /market/{top-picks,closes,index}, CORS, envelope
  responses. CLI: info/init-db/ingest/backfill/features/train/predict/daily/
  drift/models/scheduler/serve/copy-db/validate.
- Analytics (the product core): per-stock flow→price relationship —
  /correlations, /events, and /flow-return-profile (quintile analysis); surfaced
  on the stock page (heatmap + quintile chart + event study).
- Frontend: apps/web Next.js + ECharts, BUILD-VERIFIED (10 routes). Home = today's
  top ML picks (notable buys) + sparklines + stock search + index chart; stock
  detail (price/flow/foreign + flow→price analytics + ML projection + add-to-
  watchlist); rankings/screener/watchlists/models/data-status; nav freshness badge.
- Benchmark prefers the real KOSPI index (fact_index_daily), falls back to proxy.

DEPLOYMENT STATE (live — see 2026-06-03 entry)
- Repo: github.com/HajinHyukson/Acquin (origin, HTTPS, branch main). Git is
  initialized here; `git push` works (creds cached; identity FaustCalc
  <hajinson1346@gmail.com>). Commit + push as you change deploy files.
- Backend → Railway FastAPI at `https://acquin-production.up.railway.app`
  (Docker via railway.json + infra/docker/Dockerfile), backed by Railway
  Postgres. Frontend → Vercel at `https://acquin.vercel.app` (Root Directory
  apps/web, env `NEXT_PUBLIC_API_BASE=https://acquin-production.up.railway.app`).
- Deploy plumbing done: requirements.txt (Nixpacks), .railwayignore, render.yaml
  (alt), copy-db tool, cli.resolve_port() ($PORT tolerance), DATABASE_URL adoption
  + postgres:// normalization. Full runbook: docs/DEPLOYMENT.md.

REAL DATA: lives on the user's Korean-IP host (pykrx; 948 tickers, ~5y, models
trained — LightGBM). This agent environment can only reach stock OHLCV (cap/
flow/foreign/index are KRX-IP-blocked), so YOU cannot ingest — the user runs it.
Railway Postgres is populated in production; future refresh/retrain still runs
from the KR host (or a future licensed/KR-hosted ingestion service).

DO NEXT (in order)
1. **API auth + rate limiting** (BLOCKER for public exposure) — the URLs are
   public and the API is unauthenticated (anyone can read/modify watchlists).
   Add an API-key dependency (KOSPI_API_KEY setting) + simple rate limiting; have
   the frontend send the key. This is the immediate §20-step-4 priority.
2. Rest of production maturity (§20 step 4): Airflow/Prefect scheduling, MLflow
   registry + retrain-on-drift, real alert channels (email/Kakao/Telegram),
   LicensedProvider for a licensed feed, legal/data-license sign-off.
3. Optional polish: sector filter / sortable tables on picks & rankings; a
   compare view.

CANNOT do from this env: real pykrx ingest (KR-IP only), and running the live
Railway/Vercel/Postgres (the user owns those) — you make code changes, push to
GitHub, and the user redeploys. Confirm with the user before assuming prod state.

Important product constraint (unchanged): do not label 개인/기관 cumulative net
buy as actual holdings — only 외국인 보유량/보유비율 are real holdings; cumulative
개인/기관 series are a net-buy position proxy (§19.4). Already wired into API
metadata + the frontend.

At completion, update this context doc (status, progress log, decisions, known
issues, this brief) using the section 21 template.
```

---

## 21. Phase-completion update template

When a phase is completed or partially completed, append a new entry using this template.

```text
### YYYY-MM-DD — Phase X update

Status:
- Not started / In progress / Partially completed / Completed / Blocked

Summary:
- ...

Completed deliverables:
- ...

Files/modules created or changed:
- ...

Important decisions:
- ...

Tests/checks completed:
- ...

Known issues / blockers:
- ...

Data/model assumptions introduced:
- ...

Next recommended task:
- ...
```

Also update the table in `Current progress tracker`.

---

## 22. Open questions

These should be resolved as implementation progresses.

1. Which data source will be used for production: KRX direct, Koscom, broker API, paid vendor, or another source?
2. Is this app for personal/private use or commercial/public use?
3. Should ETFs, ETNs, preferred shares, SPACs, REITs, and low-liquidity names be included or excluded?
4. Which corporate-action adjustment method will be used for historical returns?
5. How much intraday functionality is needed, if any?
6. Should the ML target be absolute return, KOSPI-relative return, or both?
7. Should the app support only KOSPI first, or be designed from the beginning to support KOSDAQ later?
8. Which notification channels are needed later: email, Kakao, Telegram, Slack, browser push?
9. Should users be able to save custom screeners and watchlists in the MVP?
10. What is the acceptable delay after market close for final data availability?

---

## 23. Glossary

| Term | Meaning |
|---|---|
| 개인 | Retail/individual investors. |
| 기관 | Institutional investors. |
| 외국인 | Foreign investors. |
| 순매수 | Net buy = buy amount minus sell amount. |
| 누적 순매수 | Cumulative net buy from a selected base date. Not the same as true holdings. |
| 외국인 보유량 | Actual foreign-held shares, if sourced from verified foreign ownership data. |
| 외국인 보유비율 | Foreign ownership percentage. |
| EOD | End of day. |
| Look-ahead bias | Using future information that would not have been available at prediction time. |
| Survivorship bias | Training only on stocks that still exist today, ignoring delisted stocks. |
| Walk-forward validation | Time-based model validation that simulates future prediction. |
| IC | Information coefficient; rank correlation between model predictions and realized returns. |
| ICIR | Information coefficient information ratio; stability of IC over time. |
