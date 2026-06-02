"use client";

import { useState } from "react";
import EChart from "../EChart";

interface Point {
  date: string;
  net_buy_amount: number | null;
  cumulative_net_buy_amount?: number | null;
}
type ByGroup = Record<string, Point[]>;

const LABELS: Record<string, string> = {
  foreign: "외국인",
  institution: "기관",
  retail: "개인",
};
const COLORS: Record<string, string> = {
  foreign: "#4c8bf5",
  institution: "#2ecc71",
  retail: "#e6a23c",
};
const EOK = 1e8; // 억

export default function FlowChart({ byGroup }: { byGroup: ByGroup }) {
  const [mode, setMode] = useState<"daily" | "cumulative">("daily");
  const groups = Object.keys(byGroup).filter((g) => g in LABELS);
  const dates = groups.length ? byGroup[groups[0]].map((p) => p.date) : [];

  const series = groups.map((g) => ({
    name: LABELS[g],
    type: mode === "daily" ? "bar" : "line",
    smooth: mode === "cumulative",
    showSymbol: false,
    itemStyle: { color: COLORS[g] },
    lineStyle: { color: COLORS[g] },
    data: byGroup[g].map((p) =>
      mode === "daily"
        ? (p.net_buy_amount ?? 0) / EOK
        : (p.cumulative_net_buy_amount ?? 0) / EOK
    ),
  }));

  const option = {
    backgroundColor: "transparent",
    legend: { data: groups.map((g) => LABELS[g]), textStyle: { color: "#8a93a6" } },
    tooltip: { trigger: "axis", valueFormatter: (v: number) => `${v.toFixed(0)}억` },
    grid: { left: 64, right: 16, top: 36, bottom: 48 },
    xAxis: { type: "category", data: dates, axisLabel: { color: "#8a93a6" } },
    yAxis: {
      type: "value",
      name: "억원",
      axisLabel: { color: "#8a93a6" },
      splitLine: { lineStyle: { color: "#222a3a" } },
    },
    dataZoom: [
      { type: "inside", start: 60, end: 100 },
      { type: "slider", start: 60, end: 100, bottom: 4, height: 16 },
    ],
    series,
  } as any;

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <button onClick={() => setMode("daily")} disabled={mode === "daily"}>
          일별 순매수
        </button>
        <button onClick={() => setMode("cumulative")} disabled={mode === "cumulative"}>
          누적 순매수 (포지션 프록시)
        </button>
      </div>
      <EChart option={option} height={360} />
    </div>
  );
}
