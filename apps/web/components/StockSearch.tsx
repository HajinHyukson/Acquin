"use client";

import { useMemo, useState } from "react";

interface Stock {
  ticker: string;
  name_kr: string | null;
  name_en?: string | null;
  sector: string | null;
}

export default function StockSearch({ stocks }: { stocks: Stock[] }) {
  const [q, setQ] = useState("");
  const ql = q.trim().toLowerCase();

  const matches = useMemo(() => {
    if (!ql) return [];
    return stocks
      .filter(
        (s) =>
          s.ticker.toLowerCase().includes(ql) ||
          (s.name_kr ?? "").toLowerCase().includes(ql) ||
          (s.name_en ?? "").toLowerCase().includes(ql)
      )
      .slice(0, 30);
  }, [ql, stocks]);

  return (
    <div className="card">
      <h2>종목 검색</h2>
      <input
        placeholder="티커 또는 종목명 (예: 005930, 삼성)"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        style={{ width: "100%", maxWidth: 380 }}
        autoFocus
      />
      {ql && matches.length === 0 && <p className="muted">검색 결과가 없습니다.</p>}
      {matches.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>티커</th>
              <th>종목명</th>
              <th>섹터</th>
            </tr>
          </thead>
          <tbody>
            {matches.map((s) => (
              <tr key={s.ticker}>
                <td>
                  <a href={`/stocks/${s.ticker}`}>{s.ticker}</a>
                </td>
                <td>
                  <a href={`/stocks/${s.ticker}`}>{s.name_kr}</a>
                </td>
                <td>{s.sector}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="muted">전체 {stocks.length.toLocaleString("ko-KR")}개 종목에서 검색.</p>
    </div>
  );
}
