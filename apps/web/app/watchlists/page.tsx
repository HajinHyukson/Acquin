"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Sparkline from "@/components/charts/Sparkline";

const eok = (n: number | null | undefined) =>
  n == null ? "-" : (n / 1e8).toLocaleString("ko-KR", { maximumFractionDigits: 0 }) + "억";

export default function WatchlistsPage() {
  const [lists, setLists] = useState<any[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<any | null>(null);
  const [flows, setFlows] = useState<any[]>([]);
  const [closes, setCloses] = useState<Record<string, (number | null)[]>>({});
  const [newName, setNewName] = useState("");
  const [newTicker, setNewTicker] = useState("");
  const [err, setErr] = useState<string | null>(null);

  async function refreshLists() {
    try {
      setLists((await api.watchlists()).data);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function openList(name: string) {
    setSelected(name);
    setErr(null);
    try {
      setDetail((await api.watchlist(name)).data);
      const f = (await api.watchlistFlows(name)).data;
      setFlows(f);
      const tickers = f.map((x: any) => x.ticker);
      setCloses(
        tickers.length ? (await api.closes(tickers, 20).then((r) => r.data).catch(() => ({}))) : {}
      );
    } catch (e: any) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    refreshLists();
  }, []);

  async function create() {
    if (!newName.trim()) return;
    try {
      await api.createWatchlist(newName.trim());
      setNewName("");
      await refreshLists();
      await openList(newName.trim());
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function addTicker() {
    if (!selected || !newTicker.trim()) return;
    try {
      await api.addWatchlistItem(selected, newTicker.trim());
      setNewTicker("");
      await openList(selected);
    } catch (e: any) {
      setErr(e.message + " (티커가 존재하는지 확인하세요)");
    }
  }

  async function removeTicker(ticker: string) {
    if (!selected) return;
    await api.removeWatchlistItem(selected, ticker).catch((e) => setErr(e.message));
    await openList(selected);
  }

  async function deleteList(name: string) {
    await api.deleteWatchlist(name).catch((e) => setErr(e.message));
    if (selected === name) {
      setSelected(null);
      setDetail(null);
      setFlows([]);
    }
    await refreshLists();
  }

  return (
    <div>
      <h1>관심종목</h1>
      {err && <p className="neg">{err}</p>}

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        {/* Left: list + create */}
        <div className="card" style={{ flex: "1 1 260px" }}>
          <h2>리스트</h2>
          {lists.length === 0 && <p className="muted">아직 관심종목 리스트가 없습니다.</p>}
          {lists.map((w) => (
            <div key={w.name} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
              <a href="#" onClick={(e) => { e.preventDefault(); openList(w.name); }}>
                {w.name} <span className="muted">({w.count})</span>
              </a>
              <a href="#" className="neg" onClick={(e) => { e.preventDefault(); deleteList(w.name); }}>
                삭제
              </a>
            </div>
          ))}
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <input
              placeholder="새 리스트 이름"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <button onClick={create}>생성</button>
          </div>
        </div>

        {/* Right: selected detail + flows */}
        <div className="card" style={{ flex: "2 1 420px" }}>
          {!selected ? (
            <p className="muted">리스트를 선택하세요.</p>
          ) : (
            <>
              <h2>{selected}</h2>
              <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
                <input
                  placeholder="티커 추가 (예: 005930)"
                  value={newTicker}
                  onChange={(e) => setNewTicker(e.target.value)}
                />
                <button onClick={addTicker}>추가</button>
              </div>

              {flows.length === 0 ? (
                <p className="muted">종목이 없습니다.</p>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>종목</th>
                      <th>추세(20일)</th>
                      <th>외국인</th>
                      <th>기관</th>
                      <th>개인</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {flows.map((f) => (
                      <tr key={f.ticker}>
                        <td>
                          <a href={`/stocks/${f.ticker}`}>{f.name_kr ?? f.ticker}</a>
                        </td>
                        <td>
                          <Sparkline values={closes[f.ticker] ?? []} />
                        </td>
                        <td className={(f.foreign_net_buy ?? 0) >= 0 ? "pos" : "neg"}>{eok(f.foreign_net_buy)}</td>
                        <td className={(f.institution_net_buy ?? 0) >= 0 ? "pos" : "neg"}>{eok(f.institution_net_buy)}</td>
                        <td className={(f.retail_net_buy ?? 0) >= 0 ? "pos" : "neg"}>{eok(f.retail_net_buy)}</td>
                        <td>
                          <a href="#" className="neg" onClick={(e) => { e.preventDefault(); removeTicker(f.ticker); }}>
                            ✕
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <p className="note">최근 5거래일 순매수 합계. 보유량이 아닙니다.</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
