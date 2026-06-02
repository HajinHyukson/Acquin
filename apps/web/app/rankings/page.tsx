import { api } from "@/lib/api";
import RankBarChart from "@/components/charts/RankBarChart";
import Sparkline from "@/components/charts/Sparkline";

const fmt = (n: number) =>
  n == null ? "-" : (n / 1e8).toLocaleString("ko-KR", { maximumFractionDigits: 0 }) + "억";

export default async function RankingsPage({
  searchParams,
}: {
  searchParams: { group?: string; lookback?: string };
}) {
  const group = searchParams.group ?? "foreign";
  const lookback = Number(searchParams.lookback ?? 5);
  let rows: any[] = [];
  let closes: Record<string, (number | null)[]> = {};
  let error: string | null = null;
  try {
    rows = (await api.topNetBuy(group, lookback)).data;
    closes = await api
      .closes(rows.map((r) => r.ticker), 20)
      .then((r) => r.data)
      .catch(() => ({}));
  } catch (e: any) {
    error = e.message;
  }

  const labels: Record<string, string> = {
    foreign: "외국인",
    institution: "기관",
    retail: "개인",
  };

  return (
    <div>
      <h1>순매수 랭킹 — {labels[group] ?? group} (최근 {lookback}일)</h1>
      <div className="card">
        {["foreign", "institution", "retail"].map((g) => (
          <a key={g} href={`/rankings?group=${g}&lookback=${lookback}`} style={{ marginRight: 12 }}>
            {labels[g]}
          </a>
        ))}
      </div>
      {error ? (
        <p className="neg">API 오류: {error}</p>
      ) : (
        <>
          {rows.length > 0 && (
            <div className="card">
              <RankBarChart
                items={rows.slice(0, 20).map((r) => ({
                  label: `${r.name_kr ?? r.ticker}`,
                  value: +(r.net_buy_amount / 1e8).toFixed(0),
                }))}
              />
            </div>
          )}
          <table>
          <thead>
            <tr>
              <th>순위</th>
              <th>티커</th>
              <th>종목명</th>
              <th>추세(20일)</th>
              <th>순매수 금액</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.ticker}>
                <td>{r.rank}</td>
                <td>
                  <a href={`/stocks/${r.ticker}`}>{r.ticker}</a>
                </td>
                <td>{r.name_kr}</td>
                <td>
                  <Sparkline values={closes[r.ticker] ?? []} />
                </td>
                <td className={r.net_buy_amount >= 0 ? "pos" : "neg"}>
                  {fmt(r.net_buy_amount)}
                </td>
              </tr>
            ))}
          </tbody>
          </table>
        </>
      )}
      <p className="note">금액은 순매수(매수-매도) 기준이며 보유량이 아닙니다.</p>
    </div>
  );
}
