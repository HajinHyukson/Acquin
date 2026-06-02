# web — Next.js frontend (Phase 2)

Next.js (App Router) app with **Apache ECharts** charts. Pages: market overview
(`/` — today's top ML picks among notable buys + stock search + benchmark index
chart), net-buy rankings (`/rankings`, bar chart + table),
investor-flow screener (`/screener`, bar chart + table), watchlists
(`/watchlists`, create/add/remove + recent flows), stock detail
(`/stocks/[ticker]` — candlestick+volume+MA, investor-flow bars/cumulative
toggle, foreign-holding dual-axis, ML projection), model performance
(`/models`), and data status (`/data-status`).

> Status: **build-verified** (`next build` compiles clean, 9 routes). Charts use
> ECharts.

## Run

1. Start the backend (from the repo root, on your data host):
   ```bash
   python -m kospi_flow.cli serve --port 8000
   ```
2. Start the frontend:
   ```bash
   cd apps/web
   cp .env.local.example .env.local   # set NEXT_PUBLIC_API_BASE (default http://127.0.0.1:8000)
   npm install
   npm run dev
   ```
3. Open http://localhost:3000.

## Wording rules

The UI must label 개인/기관 cumulative series as a net-buy position proxy
(누적 순매수 기준 포지션 프록시), never as holdings. Only 외국인 보유량/보유비율
are real holdings. These notes are baked into the stock page.
