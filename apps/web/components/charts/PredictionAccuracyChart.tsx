"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import EChart from "../EChart";

const HORIZONS = [1, 3, 5, 10, 20];

const pct0 = (n: number | null | undefined) =>
  n == null ? "-" : (n * 100).toFixed(0) + "%";
const pct2 = (n: number | null | undefined) =>
  n == null ? "-" : (n * 100).toFixed(2) + "%";

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div style={{ minWidth: 110 }}>
      <div className="muted">{label}</div>
      <div style={{ fontSize: "1.25rem", fontWeight: 600 }}>{value}</div>
      {hint && <div className="muted" style={{ fontSize: "0.75rem" }}>{hint}</div>}
    </div>
  );
}

export default function PredictionAccuracyChart({
  ticker,
  initialHorizon = 5,
  initialData,
}: {
  ticker: string;
  initialHorizon?: number;
  initialData: any | null;
}) {
  const [horizon, setHorizon] = useState(initialHorizon);
  const [data, setData] = useState<any | null>(initialData);
  const [loading, setLoading] = useState(false);

  async function reload(h: number) {
    setLoading(true);
    try {
      setData((await api.predictionAccuracy(ticker, h)).data);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  const selector = (
    <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 8 }}>
      <label>
        예측 기간{" "}
        <select
          value={horizon}
          onChange={(e) => {
            const h = Number(e.target.value);
            setHorizon(h);
            reload(h);
          }}
        >
          {HORIZONS.map((h) => (
            <option key={h} value={h}>{h}일</option>
          ))}
        </select>
      </label>
      {loading && <span className="muted">조회 중…</span>}
    </div>
  );

  if (!data?.rows?.length) {
    return (
      <div>
        {selector}
        <p className="muted">
          이 기간의 과거 예측 기록이 아직 없습니다. 데이터 호스트에서{" "}
          <code>python -m kospi_flow.cli backtest --horizons {horizon}</code>를
          실행하면 과거 5년 워크포워드 기록이 생성됩니다.
        </p>
      </div>
    );
  }

  const rows = data.rows;
  const s = data.summary;
  const dates = rows.map((r: any) => r.target_date);
  const actual = rows.map((r: any) => r.actual_price);
  const p10 = rows.map((r: any) => r.p10_price);
  const p50 = rows.map((r: any) => r.p50_price);
  const bandWidth = rows.map((r: any) =>
    r.p10_price == null || r.p90_price == null ? null : r.p90_price - r.p10_price
  );
  const rollDates = data.rolling_hit_rate.map((r: any) => r.date);
  const rollVals = data.rolling_hit_rate.map((r: any) => +(r.hit_rate * 100).toFixed(1));

  const option = {
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    grid: [
      { left: 64, right: 20, top: 28, height: "52%" },
      { left: 64, right: 20, top: "74%", height: "18%" },
    ],
    legend: {
      data: ["실제 주가", "예측 밴드 (P10–P90)", "예측 중앙값(P50)"],
      textStyle: { color: "#8a93a6" },
    },
    xAxis: [
      { type: "category", gridIndex: 0, data: dates, axisLabel: { color: "#8a93a6" } },
      { type: "category", gridIndex: 1, data: rollDates, axisLabel: { color: "#8a93a6" } },
    ],
    yAxis: [
      {
        type: "value",
        gridIndex: 0,
        scale: true,
        name: "원",
        axisLabel: { color: "#8a93a6" },
        splitLine: { lineStyle: { color: "#222a3a" } },
      },
      {
        type: "value",
        gridIndex: 1,
        min: 0,
        max: 100,
        name: "적중률 %",
        axisLabel: { color: "#8a93a6", formatter: "{value}%" },
        splitLine: { show: false },
      },
    ],
    dataZoom: [{ type: "inside", xAxisIndex: [0, 1], start: 0, end: 100 }],
    series: [
      {
        // Invisible base of the band; the next series stacks the band height
        // on top of it so the area between P10 and P90 is shaded.
        name: "band-base",
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: p10,
        stack: "band",
        lineStyle: { opacity: 0 },
        symbol: "none",
        tooltip: { show: false },
      },
      {
        name: "예측 밴드 (P10–P90)",
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: bandWidth,
        stack: "band",
        lineStyle: { opacity: 0 },
        symbol: "none",
        areaStyle: { color: "rgba(138,147,166,0.30)" },
        tooltip: { show: false },
      },
      {
        name: "예측 중앙값(P50)",
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: p50,
        symbol: "none",
        lineStyle: { color: "#8a93a6", type: "dashed", width: 1 },
        itemStyle: { color: "#8a93a6" },
      },
      {
        name: "실제 주가",
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: actual,
        symbol: "none",
        lineStyle: { color: "#4c8bf5", width: 2 },
        itemStyle: { color: "#4c8bf5" },
      },
      {
        name: `${data.rolling_window}일 이동 방향 적중률`,
        type: "line",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: rollVals,
        symbol: "none",
        lineStyle: { color: "#2ecc71" },
        itemStyle: { color: "#2ecc71" },
        markLine: {
          symbol: "none",
          label: { formatter: "50% (동전 던지기)", color: "#8a93a6" },
          lineStyle: { color: "#8a93a6", type: "dotted" },
          data: [{ yAxis: 50 }],
        },
      },
    ],
  } as any;

  return (
    <div>
      {selector}
      <div
        style={{
          display: "flex",
          gap: 24,
          flexWrap: "wrap",
          padding: "8px 0 4px",
        }}
      >
        <Stat
          label="방향 적중률"
          value={pct0(s.direction_hit_rate)}
          hint="오를지/내릴지 맞힌 비율"
        />
        <Stat
          label="밴드 적중률"
          value={pct0(s.band_coverage)}
          hint="실제가 예측 범위(P10–P90) 안"
        />
        <Stat label="평균 오차" value={pct2(s.mae)} hint="예측-실제 수익률 차이" />
        <Stat
          label="표본"
          value={`${s.n.toLocaleString("ko-KR")}건`}
          hint={`${s.first_date} ~ ${s.last_date}`}
        />
        {s.spearman_ic != null && (
          <Stat label="IC" value={s.spearman_ic.toFixed(2)} hint="예측-실제 순위 상관" />
        )}
      </div>
      <EChart option={option} height={420} />
      <p className="note">
        각 시점에서 그 시점까지의 데이터만으로 학습한 모델이 낸 예측(워크포워드
        백테스트)과 실제 결과의 비교입니다. 과거 기록이며 미래 성과를 보장하지
        않습니다.
      </p>
    </div>
  );
}
