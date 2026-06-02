# Post-Backfill Runbook

Steps after the `backfill` reaches **0 pending**. Everything here is **local CPU
work — no KRX calls, no login, no Korean IP** (except step 8, the daily update,
which fetches from KRX). Run from the repo root (`C:\Users\gkwls\desktop\hydro`).
Commands are PowerShell; the `python -m kospi_flow.cli ...` lines are identical
on any OS.

> Coverage warnings from `validate` are fine — only `errors=0` matters. Missing
> investor-flow rows for some names (ETFs/REITs/SPACs/preferred classes, halts,
> recent IPOs) are expected and handled (treated as 0 in features).

---

## 1. Confirm the load + compact the DB

```powershell
python -m kospi_flow.cli validate
python -c "import sqlite3; sqlite3.connect('data/kospi_flow.db').execute('VACUUM'); print('vacuumed')"
```

Quick row-count sanity check:

```powershell
python -c "from kospi_flow.core.db import get_database; from kospi_flow.core.models import FactPriceDaily, FactInvestorFlowDaily, FactForeignHoldingDaily, FactIndexDaily; from sqlalchemy import func, select; db=get_database(); s=db.session().__enter__(); print('price  :', s.scalar(select(func.count()).select_from(FactPriceDaily))); print('flows  :', s.scalar(select(func.count()).select_from(FactInvestorFlowDaily))); print('foreign:', s.scalar(select(func.count()).select_from(FactForeignHoldingDaily))); print('index  :', s.scalar(select(func.count()).select_from(FactIndexDaily)))"
```

---

## 2. Build features

```powershell
python -m kospi_flow.cli features
```

---

## 3. Train models (real data)

Single horizon (5-day):

```powershell
python -m kospi_flow.cli train --horizon 5
```

Or all project horizons (1/3/5/10/20):

```powershell
foreach ($h in 1,3,5,10,20) { python -m kospi_flow.cli train --horizon $h }
```

---

## 4. Generate predictions

```powershell
python -m kospi_flow.cli predict --horizon 5
```

All horizons:

```powershell
foreach ($h in 1,3,5,10,20) { python -m kospi_flow.cli predict --horizon $h }
```

---

## 5. (Optional) drift + model review

```powershell
python -m kospi_flow.cli drift --horizon 5
python -m kospi_flow.cli models
```

---

## 6. Serve the API

```powershell
python -m kospi_flow.cli serve --port 8000
```

(Equivalent: `python -m uvicorn apps.api.main:app --port 8000`. Avoid the bare
`uvicorn ...` command — its shim is often not on PATH on Windows. If you see
`No module named uvicorn`, run `python -m pip install "uvicorn[standard]" fastapi`.)

In a second terminal — verify it uses the real KOSPI index and spot-check a stock:

```powershell
python -c "import requests; print(requests.get('http://127.0.0.1:8000/market/overview').json()['data'])"
python -c "import requests; print(requests.get('http://127.0.0.1:8000/stocks/005930/projection').json()['data'])"
```

Expect `benchmark_source = index:1001`. Browse interactive docs at
`http://127.0.0.1:8000/docs`.

---

## 7. (Optional) frontend

```powershell
cd apps/web
copy .env.local.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`. Return to the repo root afterwards: `cd ..\..`

---

## 8. (Optional) keep it current going forward — needs the Korean route + login

You do **not** re-backfill. Each trading day, append the latest data + reconcile.
This step hits KRX, so run it on the Korean IP with `KRX_ID`/`KRX_PW` set.

One-shot for a recent window (fixed dates):

```powershell
python -m kospi_flow.cli daily --start 2026-05-01 --end 2026-06-02 --train
```

Or run the always-on KST scheduler (set host `TZ=Asia/Seoul`):

```powershell
python -m kospi_flow.cli scheduler
```

---

## Minimum path

**Steps 1 → 2 → 3 → 4 → 6.** After step 6 you have real KOSPI investor-flow
charts, screeners, and ML projections served over the API.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `train` slow / high memory | Train one horizon at a time; it's a ~1.6M-row panel. |
| `predict` says model not found | Run the matching `train --horizon N` first. |
| API `/projection` 404 for a ticker | Predictions only exist after `predict`; some names have no model row. |
| `/market/overview` shows `benchmark_source = proxy` | The KOSPI index (`1001`) didn't ingest — re-run the index part of the backfill on the KR route. |
