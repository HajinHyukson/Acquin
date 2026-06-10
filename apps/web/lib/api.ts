// Thin client for the FastAPI backend. Set NEXT_PUBLIC_API_BASE to point at it.
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export interface Envelope<T> {
  data: T;
  metadata: {
    source: string | null;
    freshness_state: string | null;
    latest_data_date: string | null;
    generated_at: string;
    [k: string]: unknown;
  };
}

async function getJson<T>(path: string): Promise<Envelope<T>> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${path} -> ${res.status}`);
  }
  return res.json();
}

async function postJson<T>(path: string, body: unknown): Promise<Envelope<T>> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API ${path} -> ${res.status}`);
  return res.json();
}

async function delJson<T>(path: string): Promise<Envelope<T>> {
  const res = await fetch(`${API_BASE}${path}`, { method: "DELETE", cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path} -> ${res.status}`);
  return res.json();
}

const enc = encodeURIComponent;

export const api = {
  marketOverview: () => getJson<Record<string, any>>("/market/overview"),
  marketIndex: () => getJson<any[]>("/market/index"),
  topPicks: (horizon = 5, limit = 20, notableOnly = true) =>
    getJson<any[]>(
      `/market/top-picks?horizon=${horizon}&limit=${limit}&notable_only=${notableOnly}`
    ),
  closes: (tickers: string[], days = 20) =>
    getJson<Record<string, (number | null)[]>>(
      `/market/closes?days=${days}&tickers=${tickers.map(enc).join(",")}`
    ),
  topNetBuy: (group: string, lookback = 5) =>
    getJson<any[]>(`/market/top-net-buy?investor_group=${group}&lookback_days=${lookback}`),
  listStocks: () => getJson<any[]>("/stocks"),
  stock: (t: string) => getJson<any>(`/stocks/${t}`),
  price: (t: string, start?: string, end?: string) => {
    const q = new URLSearchParams();
    if (start) q.set("start", start);
    if (end) q.set("end", end);
    const qs = q.toString();
    return getJson<any[]>(`/stocks/${t}/price${qs ? `?${qs}` : ""}`);
  },
  flows: (t: string) => getJson<any>(`/stocks/${t}/investor-flows?cumulative=true`),
  foreign: (t: string) => getJson<any[]>(`/stocks/${t}/foreign-holdings`),
  projection: (t: string, model?: string) =>
    getJson<any>(`/stocks/${t}/projection${model ? `?model=${enc(model)}` : ""}`),
  predictionAccuracy: (t: string, horizon = 5, model?: string) => {
    const q = new URLSearchParams({ horizon: String(horizon) });
    if (model) q.set("model", model);
    return getJson<any>(`/stocks/${enc(t)}/prediction-accuracy?${q}`);
  },
  correlations: (t: string) => getJson<any[]>(`/stocks/${t}/correlations`),
  events: (t: string, eventType: string) =>
    getJson<any>(`/stocks/${enc(t)}/events?event_type=${enc(eventType)}`),
  flowReturnProfile: (t: string, flowWindow = 5) =>
    getJson<any>(`/stocks/${enc(t)}/flow-return-profile?flow_window=${flowWindow}`),
  screen: (body: unknown) => postJson<any[]>("/screeners/investor-flow", body),
  models: () => getJson<any[]>("/models"),
  dataStatus: () => getJson<any>("/data-status"),
  dataFreshness: () => getJson<any>("/metadata/data-freshness"),

  // Watchlists
  watchlists: () => getJson<any[]>("/watchlists"),
  watchlist: (name: string) => getJson<any>(`/watchlists/${enc(name)}`),
  watchlistFlows: (name: string) => getJson<any[]>(`/watchlists/${enc(name)}/flows`),
  createWatchlist: (name: string, description?: string) =>
    postJson<any>("/watchlists", { name, description }),
  deleteWatchlist: (name: string) => delJson<any>(`/watchlists/${enc(name)}`),
  addWatchlistItem: (name: string, ticker: string) =>
    postJson<any>(`/watchlists/${enc(name)}/items`, { ticker }),
  removeWatchlistItem: (name: string, ticker: string) =>
    delJson<any>(`/watchlists/${enc(name)}/items/${enc(ticker)}`),
};
