"use client";

import EChart from "../EChart";

/** Tiny axis-less line for inline trends (e.g. table rows). */
export default function Sparkline({
  values,
  width = 120,
  height = 36,
}: {
  values: (number | null)[];
  width?: number;
  height?: number;
}) {
  const clean = values.filter((v): v is number => v != null);
  if (clean.length < 2) {
    return <span className="muted">-</span>;
  }
  const up = clean[clean.length - 1] >= clean[0];
  const color = up ? "#2ecc71" : "#e74c3c";

  const option = {
    backgroundColor: "transparent",
    grid: { left: 1, right: 1, top: 3, bottom: 3 },
    xAxis: { type: "category", show: false, data: clean.map((_, i) => i) },
    yAxis: { type: "value", show: false, scale: true },
    tooltip: { show: false },
    series: [
      {
        type: "line",
        data: clean,
        showSymbol: false,
        smooth: true,
        lineStyle: { color, width: 1.5 },
        areaStyle: { color: up ? "rgba(46,204,113,0.12)" : "rgba(231,76,60,0.12)" },
      },
    ],
  } as any;

  return (
    <div style={{ width, height, display: "inline-block", verticalAlign: "middle" }}>
      <EChart option={option} height={height} />
    </div>
  );
}
