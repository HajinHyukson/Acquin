"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import RankBarChart from "@/components/charts/RankBarChart";

const fmtAmt = (n: number | null) =>
  n == null ? "-" : (n / 1e8).toLocaleString("ko-KR", { maximumFractionDigits: 0 }) + "억";
const fmtPct = (n: number | null) => (n == null ? "-" : (n * 100).toFixed(2) + "%");

export default function ScreenerPage() {
  const [lookback, setLookback] = useState(5);
  const [group, setGroup] = useState("foreign");
  const [minAmt, setMinAmt] = useState(0);
  const [rows, setRows] = useState<any[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true);
    setErr(null);
    try {
      const res = await api.screen({
        lookback_days: lookback,
        investor_groups: [group],
        min_net_buy_amount: minAmt * 1e8,
        exclude_preferred: true,
      });
      setRows(res.data);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h1>투자자 순매수 스크리너</h1>
      <div className="card" style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        <label>
          투자자{" "}
          <select value={group} onChange={(e) => setGroup(e.target.value)}>
            <option value="foreign">외국인</option>
            <option value="institution">기관</option>
            <option value="retail">개인</option>
          </select>
        </label>
        <label>
          기간(일){" "}
          <select value={lookback} onChange={(e) => setLookback(Number(e.target.value))}>
            {[5, 10, 20, 60].map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </label>
        <label>
          최소 순매수(억){" "}
          <input
            type="number"
            value={minAmt}
            onChange={(e) => setMinAmt(Number(e.target.value))}
            style={{ width: 100 }}
          />
        </label>
        <button onClick={run} disabled={loading}>
          {loading ? "조회 중..." : "스크리닝"}
        </button>
      </div>

      {err && <p className="neg">API 오류: {err}</p>}
      {rows.length > 0 && (
        <div className="card">
          <RankBarChart
            items={rows.slice(0, 20).map((r) => ({
              label: r.name_kr ?? r.ticker,
              value: +(r.net_buy_amount / 1e8).toFixed(0),
            }))}
          />
        </div>
      )}
      <table>
        <thead>
          <tr>
            <th>티커</th>
            <th>종목명</th>
            <th>순매수</th>
            <th>순매수/시총</th>
            <th>연속일</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.ticker}>
              <td>
                <a href={`/stocks/${r.ticker}`}>{r.ticker}</a>
              </td>
              <td>{r.name_kr}</td>
              <td className={r.net_buy_amount >= 0 ? "pos" : "neg"}>{fmtAmt(r.net_buy_amount)}</td>
              <td>{fmtPct(r.net_buy_pct_mcap)}</td>
              <td>{r.streak_days}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
