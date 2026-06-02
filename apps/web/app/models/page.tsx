import { api } from "@/lib/api";

const f = (n: number | null, d = 3) => (n == null ? "-" : n.toFixed(d));

export default async function ModelsPage() {
  let models: any[] = [];
  let error: string | null = null;
  try {
    models = (await api.models()).data;
  } catch (e: any) {
    error = e.message;
  }

  if (error) return <p className="neg">API 오류: {error}</p>;

  return (
    <div>
      <h1>모델 성능</h1>
      {models.length === 0 ? (
        <p className="muted">등록된 모델이 없습니다. (train 실행 필요)</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>모델</th>
              <th>버전</th>
              <th>기간</th>
              <th>백엔드</th>
              <th>활성</th>
              <th>IC</th>
              <th>ICIR</th>
              <th>RMSE</th>
              <th>AUC</th>
              <th>표본수</th>
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={`${m.model_name}:${m.model_version}`}>
                <td>{m.model_name}</td>
                <td>{m.model_version}</td>
                <td>{m.horizon_days}일</td>
                <td>{m.backend}</td>
                <td>{m.is_active ? "✓" : ""}</td>
                <td className={m.mean_ic >= 0 ? "pos" : "neg"}>{f(m.mean_ic)}</td>
                <td>{f(m.icir, 2)}</td>
                <td>{f(m.rmse, 4)}</td>
                <td>{f(m.auc, 3)}</td>
                <td>{m.n_samples?.toLocaleString("ko-KR")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="note">
        IC = Daily Spearman 정보계수, ICIR = IC 안정성, 모두 워크-포워드 검증 기준.
      </p>
    </div>
  );
}
