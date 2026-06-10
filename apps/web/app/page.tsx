import { api } from "@/lib/api";
import IndexChart from "@/components/charts/IndexChart";
import TopPicks from "@/components/TopPicks";
import StockSearch from "@/components/StockSearch";

export default async function HomePage() {
  let overview: any = null;
  let stocks: any[] = [];
  let index: any[] = [];
  let picks: any[] = [];
  let error: string | null = null;
  try {
    overview = (await api.marketOverview()).data;
    [stocks, index, picks] = await Promise.all([
      api.listStocks().then((r) => r.data).catch(() => []),
      api.marketIndex().then((r) => r.data).catch(() => []),
      api.topPicks(5).then((r) => r.data).catch(() => []),
    ]);
  } catch (e: any) {
    error = e.message;
  }

  if (error) {
    return (
      <div className="card">
        <h1>시장 개요</h1>
        <p className="neg">API에 연결할 수 없습니다: {error}</p>
        <p className="muted">
          백엔드를 먼저 실행하세요: <code>python -m kospi_flow.cli serve</code>
        </p>
      </div>
    );
  }

  const isReal = overview.benchmark_source?.startsWith("index:");
  const benchLabel = isReal ? "KOSPI 지수" : "KOSPI 프록시";

  return (
    <div>
      <h1>시장 개요</h1>
      <div className="grid2">
        <div className="card">
          <div>기준일: {overview.as_of ?? "-"}</div>
          <div>종목 수: {overview.n_stocks}</div>
          <div>
            {benchLabel} 1일 수익률:{" "}
            <span className={overview.market_return_1d >= 0 ? "pos" : "neg"}>
              {overview.market_return_1d != null
                ? (overview.market_return_1d * 100).toFixed(2) + "%"
                : "-"}
            </span>
          </div>
          <div className="muted">벤치마크: {overview.benchmark_source}</div>
        </div>

        {/* Search any stock (replaces the full list) */}
        <StockSearch stocks={stocks} />

        {/* Today's notable ML picks */}
        <TopPicks initialRows={picks} initialHorizon={5} />

        {index.length > 0 && (
          <div className="card">
            <h2>{benchLabel}</h2>
            <IndexChart rows={index} name={benchLabel} />
          </div>
        )}
      </div>
    </div>
  );
}
