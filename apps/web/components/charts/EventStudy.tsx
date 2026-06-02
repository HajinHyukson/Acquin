"use client";

import { useState } from "react";
import { api } from "@/lib/api";

const EVENT_LABELS: Record<string, string> = {
  foreign_accumulation: "외국인 집중 매수 (5일 상위 10%)",
  institution_accumulation: "기관 집중 매수 (10일 ≥ 0.5% 시총)",
  dual_accumulation: "외국인+기관 동반 매수 3일+",
  retail_exit: "개인 매도 + 외국인/기관 매수",
  price_flow_divergence: "가격 하락 중 매수세 유입 (다이버전스)",
};
const pct = (n: number | null) => (n == null ? "-" : (n * 100).toFixed(2) + "%");

export default function EventStudy({
  ticker,
  initialType,
  initialResult,
}: {
  ticker: string;
  initialType: string;
  initialResult: any;
}) {
  const [type, setType] = useState(initialType);
  const [result, setResult] = useState<any>(initialResult);
  const [loading, setLoading] = useState(false);

  async function change(next: string) {
    setType(next);
    setLoading(true);
    try {
      setResult((await api.events(ticker, next)).data);
    } catch {
      setResult({ results: [], n_events: 0 });
    } finally {
      setLoading(false);
    }
  }

  const results = result?.results ?? [];

  return (
    <div>
      <div style={{ display: "flex", gap: 12, marginBottom: 8, alignItems: "center" }}>
        <label>
          신호{" "}
          <select value={type} onChange={(e) => change(e.target.value)}>
            {Object.entries(EVENT_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </label>
        <span className="muted">
          {loading ? "조회 중…" : `과거 발생 ${result?.n_events ?? 0}회`}
        </span>
      </div>

      {results.length === 0 ? (
        <p className="muted">이 신호에 해당하는 과거 사례가 없습니다.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>이후 기간</th>
              <th>사례수</th>
              <th>평균 수익률</th>
              <th>중앙값</th>
              <th>적중률</th>
              <th>KOSPI 초과</th>
              <th>P10~P90</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r: any) => (
              <tr key={r.horizon}>
                <td>{r.horizon}일</td>
                <td>{r.count}</td>
                <td className={(r.mean_return ?? 0) >= 0 ? "pos" : "neg"}>
                  {pct(r.mean_return)}
                </td>
                <td>{pct(r.median_return)}</td>
                <td>{pct(r.positive_return_rate)}</td>
                <td>{pct(r.outperform_kospi_rate)}</td>
                <td className="muted">
                  {pct(r.p10_return)} ~ {pct(r.p90_return)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="note">
        해당 신호 발생일 이후의 실제 수익률 분포(룩어헤드 없음). 적중률 = 양(+)
        수익률 비율, KOSPI 초과 = 시장 대비 초과 수익 비율.
      </p>
    </div>
  );
}
