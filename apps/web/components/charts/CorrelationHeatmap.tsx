"use client";

import EChart from "../EChart";

interface Corr {
  investor_group: string;
  flow_window: number;
  horizon: number;
  n: number;
  pearson: number | null;
  spearman: number | null;
}

const GROUPS = ["retail", "institution", "foreign"];
const LABELS: Record<string, string> = {
  retail: "개인",
  institution: "기관",
  foreign: "외국인",
};

export default function CorrelationHeatmap({
  rows,
  flowWindow = 5,
}: {
  rows: Corr[];
  flowWindow?: number;
}) {
  const horizons = Array.from(
    new Set(rows.filter((r) => r.flow_window === flowWindow).map((r) => r.horizon))
  ).sort((a, b) => a - b);

  const data: [number, number, number | null][] = [];
  GROUPS.forEach((g, yi) => {
    horizons.forEach((h, xi) => {
      const row = rows.find(
        (r) => r.investor_group === g && r.flow_window === flowWindow && r.horizon === h
      );
      data.push([xi, yi, row?.spearman ?? null]);
    });
  });

  const option = {
    backgroundColor: "transparent",
    tooltip: {
      formatter: (p: any) =>
        `${LABELS[GROUPS[p.value[1]]]} · ${horizons[p.value[0]]}일 후<br/>Spearman: ${
          p.value[2] == null ? "-" : p.value[2].toFixed(3)
        }`,
    },
    grid: { left: 64, right: 16, top: 16, bottom: 48 },
    xAxis: {
      type: "category",
      data: horizons.map((h) => `${h}일`),
      name: "향후 기간",
      axisLabel: { color: "#8a93a6" },
    },
    yAxis: {
      type: "category",
      data: GROUPS.map((g) => LABELS[g]),
      axisLabel: { color: "#e6e6e6" },
    },
    visualMap: {
      min: -0.3,
      max: 0.3,
      calculable: true,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      textStyle: { color: "#8a93a6" },
      inRange: { color: ["#e74c3c", "#2b3340", "#2ecc71"] },
    },
    series: [
      {
        type: "heatmap",
        data,
        label: {
          show: true,
          color: "#e6e6e6",
          formatter: (p: any) => (p.value[2] == null ? "" : p.value[2].toFixed(2)),
        },
      },
    ],
  } as any;

  return <EChart option={option} height={220} />;
}
