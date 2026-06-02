"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Sparkline from "@/components/charts/Sparkline";

const pct = (n: number | null) => (n == null ? "-" : (n * 100).toFixed(2) + "%");
const won = (n: number | null) =>
  n == null ? "-" : Math.round(n).toLocaleString("ko-KR") + "원";
const eok = (n: number | null) =>
  n == null ? "-" : (n / 1e8).toLocaleString("ko-KR", { maximumFractionDigits: 0 }) + "억";

const HORIZONS = [1, 3, 5, 10, 20];

export default function TopPicks({
  initialRows,
  initialHorizon = 5,
}: {
  initialRows: any[];
  initialHorizon?: number;
}) {
  const [horizon, setHorizon] = useState(initialHorizon);
  const [rows, setRows] = useState<any[]>(initialRows);
  const [notableOnly, setNotableOnly] = useState(true);
  const [loading, setLoading] = useState(false);
  const [spark, setSpark] = useState<Record<string, (number | null)[]>>({});

  async function loadSparks(rs: any[]) {
    const tickers = rs.map((r) => r.ticker);
    if (!tickers.length) return setSpark({});
    try {
      setSpark((await api.closes(tickers, 20)).data);
    } catch {
      setSpark({});
    }
  }

  useEffect(() => {
    loadSparks(initialRows);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function reload(h: number, notable: boolean) {
    setLoading(true);
    try {
      const data = (await api.topPicks(h, 20, notable)).data;
      setRows(data);
      loadSparks(data);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card">
      <h2>오늘의 주목 매수 — ML 기대수익률 상위</h2>
      <div style={{ display: "flex", gap: 12, marginBottom: 8, alignItems: "center", flexWrap: "wrap" }}>
        <label>
          예측 기간{" "}
          <select
            value={horizon}
            onChange={(e) => {
              const h = Number(e.target.value);
              setHorizon(h);
              reload(h, notableOnly);
            }}
          >
            {HORIZONS.map((h) => (
              <option key={h} value={h}>{h}일</option>
            ))}
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={notableOnly}
            onChange={(e) => {
              setNotableOnly(e.target.checked);
              reload(horizon, e.target.checked);
            }}
          />{" "}
          최근 외국인·기관 순매수 종목만
        </label>
        {loading && <span className="muted">조회 중…</span>}
      </div>

      {rows.length === 0 ? (
        <p className="muted">
          예측 데이터가 없습니다. 백엔드에서 <code>train</code> → <code>predict</code>를
          실행하세요.
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>종목</th>
              <th>추세(20일)</th>
              <th>{horizon}일 기대수익률</th>
              <th>예측가</th>
              <th>외국인 순매수</th>
              <th>기관 순매수</th>
              <th>KOSPI 초과확률</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.ticker}>
                <td>{r.rank}</td>
                <td>
                  <a href={`/stocks/${r.ticker}`}>{r.name_kr ?? r.ticker}</a>{" "}
                  <span className="muted">{r.ticker}</span>
                </td>
                <td>
                  <Sparkline values={spark[r.ticker] ?? []} />
                </td>
                <td className={r.predicted_return >= 0 ? "pos" : "neg"}>
                  {pct(r.predicted_return)}
                </td>
                <td>{won(r.predicted_price)}</td>
                <td className={r.foreign_net >= 0 ? "pos" : "neg"}>{eok(r.foreign_net)}</td>
                <td className={r.institution_net >= 0 ? "pos" : "neg"}>{eok(r.institution_net)}</td>
                <td>{pct(r.prob_outperform_kospi)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="note">
        최근 순매수(외국인+기관 &gt; 0)인 종목 중 ML {horizon}일 기대수익률 상위.
        예측 생성일 기준이며, 불확실성을 포함합니다 (투자 권유 아님).
      </p>
    </div>
  );
}
