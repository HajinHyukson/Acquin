"use client";

import EChart from "../EChart";

interface Row {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
}

function ma(values: (number | null)[], window: number): (number | null)[] {
  return values.map((_, i) => {
    if (i < window - 1) return null;
    let sum = 0;
    for (let j = i - window + 1; j <= i; j++) {
      const v = values[j];
      if (v == null) return null;
      sum += v;
    }
    return +(sum / window).toFixed(0);
  });
}

export default function PriceChart({ rows }: { rows: Row[] }) {
  const dates = rows.map((r) => r.date);
  // ECharts candlestick wants [open, close, low, high].
  const candles = rows.map((r) => [r.open, r.close, r.low, r.high]);
  const closes = rows.map((r) => r.close);
  const volumes = rows.map((r) => r.volume ?? 0);

  const option = {
    backgroundColor: "transparent",
    legend: { data: ["가격", "MA5", "MA20", "MA60"], textStyle: { color: "#8a93a6" } },
    tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    grid: [
      { left: 56, right: 16, top: 36, height: "58%" },
      { left: 56, right: 16, top: "74%", height: "16%" },
    ],
    xAxis: [
      { type: "category", data: dates, boundaryGap: true, axisLabel: { color: "#8a93a6" } },
      {
        type: "category",
        gridIndex: 1,
        data: dates,
        axisLabel: { show: false },
      },
    ],
    yAxis: [
      { scale: true, axisLabel: { color: "#8a93a6" }, splitLine: { lineStyle: { color: "#222a3a" } } },
      { gridIndex: 1, axisLabel: { show: false }, splitLine: { show: false } },
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: [0, 1], start: 70, end: 100 },
      { type: "slider", xAxisIndex: [0, 1], start: 70, end: 100, bottom: 4, height: 16 },
    ],
    series: [
      {
        name: "가격",
        type: "candlestick",
        data: candles,
        itemStyle: {
          color: "#e74c3c",
          color0: "#2f80ed",
          borderColor: "#e74c3c",
          borderColor0: "#2f80ed",
        },
      },
      { name: "MA5", type: "line", data: ma(closes, 5), smooth: true, showSymbol: false, lineStyle: { width: 1 } },
      { name: "MA20", type: "line", data: ma(closes, 20), smooth: true, showSymbol: false, lineStyle: { width: 1 } },
      { name: "MA60", type: "line", data: ma(closes, 60), smooth: true, showSymbol: false, lineStyle: { width: 1 } },
      {
        name: "거래량",
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumes,
        itemStyle: { color: "#3a4763" },
      },
    ],
  } as any;

  return <EChart option={option} height={440} />;
}
