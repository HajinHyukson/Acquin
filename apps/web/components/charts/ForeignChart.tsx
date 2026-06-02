"use client";

import EChart from "../EChart";

interface Row {
  date: string;
  foreign_ownership_pct: number | null;
  foreign_held_shares: number | null;
}

export default function ForeignChart({ rows }: { rows: Row[] }) {
  const dates = rows.map((r) => r.date);
  const pct = rows.map((r) =>
    r.foreign_ownership_pct == null ? null : +(r.foreign_ownership_pct * 100).toFixed(2)
  );
  const shares = rows.map((r) =>
    r.foreign_held_shares == null ? null : +(r.foreign_held_shares / 1e6).toFixed(2)
  );

  const option = {
    backgroundColor: "transparent",
    legend: { data: ["보유비율", "보유량"], textStyle: { color: "#8a93a6" } },
    tooltip: { trigger: "axis" },
    grid: { left: 56, right: 56, top: 36, bottom: 48 },
    xAxis: { type: "category", data: dates, axisLabel: { color: "#8a93a6" } },
    yAxis: [
      {
        type: "value",
        name: "%",
        position: "left",
        axisLabel: { color: "#8a93a6", formatter: "{value}%" },
        splitLine: { lineStyle: { color: "#222a3a" } },
      },
      {
        type: "value",
        name: "백만주",
        position: "right",
        axisLabel: { color: "#8a93a6" },
        splitLine: { show: false },
      },
    ],
    dataZoom: [
      { type: "inside", start: 60, end: 100 },
      { type: "slider", start: 60, end: 100, bottom: 4, height: 16 },
    ],
    series: [
      {
        name: "보유비율",
        type: "line",
        yAxisIndex: 0,
        data: pct,
        smooth: true,
        showSymbol: false,
        lineStyle: { color: "#4c8bf5" },
        itemStyle: { color: "#4c8bf5" },
        areaStyle: { color: "rgba(76,139,245,0.15)" },
      },
      {
        name: "보유량",
        type: "line",
        yAxisIndex: 1,
        data: shares,
        smooth: true,
        showSymbol: false,
        lineStyle: { color: "#8a93a6", type: "dashed" },
        itemStyle: { color: "#8a93a6" },
      },
    ],
  } as any;

  return <EChart option={option} height={320} />;
}
