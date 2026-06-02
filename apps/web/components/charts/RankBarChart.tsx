"use client";

import EChart from "../EChart";

export interface RankItem {
  label: string;
  value: number; // already scaled to display units (e.g. 억)
}

export default function RankBarChart({
  items,
  unit = "억",
}: {
  items: RankItem[];
  unit?: string;
}) {
  const labels = items.map((i) => i.label);
  const data = items.map((i) => ({
    value: i.value,
    itemStyle: { color: i.value >= 0 ? "#2ecc71" : "#e74c3c" },
  }));

  const option = {
    backgroundColor: "transparent",
    grid: { left: 140, right: 28, top: 12, bottom: 32 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      valueFormatter: (v: number) =>
        `${Number(v).toLocaleString("ko-KR", { maximumFractionDigits: 0 })} ${unit}`,
    },
    xAxis: {
      type: "value",
      axisLabel: { color: "#8a93a6" },
      splitLine: { lineStyle: { color: "#222a3a" } },
    },
    yAxis: {
      type: "category",
      data: labels,
      inverse: true,
      axisLabel: { color: "#e6e6e6" },
    },
    series: [{ type: "bar", data }],
  } as any;

  const height = Math.max(180, items.length * 24 + 60);
  return <EChart option={option} height={height} />;
}
