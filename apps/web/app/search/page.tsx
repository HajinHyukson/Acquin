import { api } from "@/lib/api";

export default async function SearchPage({
  searchParams,
}: {
  searchParams: { q?: string };
}) {
  const q = (searchParams.q ?? "").trim();
  const ql = q.toLowerCase();

  let stocks: any[] = [];
  let error: string | null = null;
  try {
    stocks = (await api.listStocks()).data;
  } catch (e: any) {
    error = e.message;
  }

  const matches = ql
    ? stocks
        .filter(
          (s) =>
            s.ticker.toLowerCase().includes(ql) ||
            (s.name_kr ?? "").toLowerCase().includes(ql) ||
            (s.name_en ?? "").toLowerCase().includes(ql)
        )
        .slice(0, 100)
    : [];

  return (
    <div>
      <h1>종목 검색</h1>
      <form action="/search" method="get" className="card">
        <input
          type="search"
          name="q"
          defaultValue={q}
          placeholder="티커 또는 종목명 (예: 005930, 삼성)"
          style={{ width: "100%", maxWidth: 400 }}
          autoFocus
        />
      </form>

      {error && <p className="neg">API 오류: {error}</p>}

      {q && (
        <p className="muted">
          "{q}" 검색 결과 {matches.length}건
          {matches.length === 100 ? " (상위 100건)" : ""}
        </p>
      )}

      {matches.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>티커</th>
              <th>종목명</th>
              <th>섹터</th>
            </tr>
          </thead>
          <tbody>
            {matches.map((s) => (
              <tr key={s.ticker}>
                <td>
                  <a href={`/stocks/${s.ticker}`}>{s.ticker}</a>
                </td>
                <td>
                  <a href={`/stocks/${s.ticker}`}>{s.name_kr}</a>
                </td>
                <td>{s.sector}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {q && matches.length === 0 && !error && (
        <p className="muted">검색 결과가 없습니다.</p>
      )}
    </div>
  );
}
