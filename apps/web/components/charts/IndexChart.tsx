"use client";

import EChart from "../EChart";

interface Row {
  date: string;
  close: number | null;
}

export default function IndexChart({ rows, name }: { rows: Row[]; name: string }) {
  const option = {
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    grid: { left: 64, right: 16, top: 24, bottom: 48 },
    xAxis: { type: "category", data: rows.map((r) => r.date), axisLabel: { color: "#8a93a6" } },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: { color: "#8a93a6" },
      splitLine: { lineStyle: { color: "#222a3a" } },
    },
    dataZoom: [
      { type: "inside", start: 60, end: 100 },
      { type: "slider", start: 60, end: 100, bottom: 4, height: 16 },
    ],
    series: [
      {
        name,
        type: "line",
        data: rows.map((r) => r.close),
        smooth: true,
        showSymbol: false,
        lineStyle: { color: "#4c8bf5" },
        itemStyle: { color: "#4c8bf5" },
        areaStyle: { color: "rgba(76,139,245,0.12)" },
      },
    ],
  } as any;

  return <EChart option={option} height={320} />;
}
