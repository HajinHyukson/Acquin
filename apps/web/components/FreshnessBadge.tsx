"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

/** Small global indicator of the latest data date + freshness state. */
export default function FreshnessBadge() {
  const [info, setInfo] = useState<{ date: string; state: string | null } | null>(null);

  useEffect(() => {
    api
      .dataFreshness()
      .then((r) => {
        const p = r.data?.fact_price_daily;
        if (p?.latest_data_date) setInfo({ date: p.latest_data_date, state: p.freshness_state });
      })
      .catch(() => {});
  }, []);

  if (!info) return null;
  return (
    <span className="muted" style={{ fontSize: "0.8rem", whiteSpace: "nowrap" }}>
      데이터 {info.date}
      {info.state ? ` · ${info.state}` : ""}
    </span>
  );
}
