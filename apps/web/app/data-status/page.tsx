import { api } from "@/lib/api";

export default async function DataStatusPage() {
  let status: any = null;
  let freshness: any = null;
  let error: string | null = null;
  try {
    [status, freshness] = await Promise.all([
      api.dataStatus().then((r) => r.data),
      api.dataFreshness().then((r) => r.data).catch(() => null),
    ]);
  } catch (e: any) {
    error = e.message;
  }

  if (error) return <p className="neg">API 오류: {error}</p>;

  return (
    <div>
      <h1>데이터 상태</h1>

      <div className="card">
        <div>
          검증:{" "}
          <span className={status.ok ? "pos" : "neg"}>
            {status.ok ? "정상 (errors=0)" : `오류 ${status.errors?.length ?? 0}건`}
          </span>
        </div>
        <table>
          <thead>
            <tr>
              <th>테이블</th>
              <th>행 수</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(status.counts ?? {}).map(([k, v]: any) => (
              <tr key={k}>
                <td>{k}</td>
                <td>{Number(v).toLocaleString("ko-KR")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {freshness && (
        <div className="card">
          <h2>데이터 신선도</h2>
          <table>
            <thead>
              <tr>
                <th>테이블</th>
                <th>최신일</th>
                <th>상태</th>
                <th>소스</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(freshness).map(([k, v]: any) => (
                <tr key={k}>
                  <td>{k}</td>
                  <td>{v.latest_data_date ?? "-"}</td>
                  <td>{v.freshness_state ?? "-"}</td>
                  <td>{v.source ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {status.warnings?.length > 0 && (
        <div className="card">
          <h2>경고 ({status.warnings.length})</h2>
          <p className="muted">
            커버리지 경고는 정상입니다 (ETF/우선주/거래정지/신규상장 등 일부 종목의
            투자자 데이터 누락). errors=0 이면 사용에 문제 없습니다.
          </p>
        </div>
      )}
    </div>
  );
}
