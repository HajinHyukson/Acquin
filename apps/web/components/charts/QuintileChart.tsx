"use client";

import { useState } from "react";
import EChart from "../EChart";

interface Quintile {
  quintile: number;
  n: number;
  flow_pct_mcap_mean: number;
  mean_return: Record<string, number | null>;
  hit_rate: Record<string, number | null>;
}
interface Profile {
  flow_window: number;
  horizons: number[];
  groups: Record<string, { quintiles: Quintile[]; note?: string }>;
}

const LABELS: Record<string, string> = {
  foreign: "외국인",
  institution: "기관",
  retail: "개인",
};
const Q_LABELS = ["Q1 (강한 순매도)", "Q2", "Q3", "Q4", "Q5 (강한 순매수)"];

export default function QuintileChart({ profile }: { profile: Profile }) {
  const groups = Object.keys(profile.groups ?? {}).filter((g) => g in LABELS);
  const [group, setGroup] = useState(groups.includes("foreign") ? "foreign" : groups[0]);
  const [horizon, setHorizon] = useState(
    profile.horizons?.includes(5) ? 5 : profile.horizons?.[0]
  );

  const quintiles = profile.groups[group]?.quintiles ?? [];
  const h = String(horizon);
  const returns = quintiles.map((q) => {
    const v = q.mean_return[h];
    return v == null ? null : +(v * 100).toFixed(2);
  });
  const hits = quintiles.map((q) => q.hit_rate[h]);

  const option = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      formatter: (ps: any) => {
        const i = ps[0].dataIndex;
        const q = quintiles[i];
        const hr = hits[i] == null ? "-" : (hits[i]! * 100).toFixed(0) + "%";
        return `${Q_LABELS[i]}<br/>평균 ${horizon}일 수익률: ${
          returns[i] == null ? "-" : returns[i] + "%"
        }<br/>적중률: ${hr} · 표본 ${q?.n ?? 0}`;
      },
    },
    grid: { left: 56, right: 16, top: 16, bottom: 56 },
    xAxis: {
      type: "category",
      data: Q_LABELS.slice(0, quintiles.length),
      axisLabel: { color: "#8a93a6", interval: 0, fontSize: 10 },
    },
    yAxis: {
      type: "value",
      name: "평균 수익률 %",
      axisLabel: { color: "#8a93a6", formatter: "{value}%" },
      splitLine: { lineStyle: { color: "#222a3a" } },
    },
    series: [
      {
        type: "bar",
        data: returns.map((v) => ({
          value: v,
          itemStyle: { color: (v ?? 0) >= 0 ? "#2ecc71" : "#e74c3c" },
        })),
      },
    ],
  } as any;

  if (!quintiles.length) {
    return (
      <p className="muted">
        {profile.groups[group]?.note === "insufficient data"
          ? "데이터가 부족하여 분위 분석을 계산할 수 없습니다."
          : "분위 데이터 없음"}
      </p>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 12, marginBottom: 8, alignItems: "center" }}>
        <label>
          투자자{" "}
          <select value={group} onChange={(e) => setGroup(e.target.value)}>
            {groups.map((g) => (
              <option key={g} value={g}>{LABELS[g]}</option>
            ))}
          </select>
        </label>
        <label>
          향후 기간{" "}
          <select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
            {profile.horizons.map((hh) => (
              <option key={hh} value={hh}>{hh}일</option>
            ))}
          </select>
        </label>
      </div>
      <EChart option={option} height={300} />
      <p className="note">
        {LABELS[group]} 순매수 강도(시총 대비, 최근 {profile.flow_window}일)별 그룹의
        이후 {horizon}일 평균 수익률. 좌(순매도)→우(순매수)로 수익률이 오르면 매수세가
        가격을 선행함을 시사합니다.
      </p>
    </div>
  );
}
