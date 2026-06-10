import { api } from "@/lib/api";
import PriceChart from "@/components/charts/PriceChart";
import FlowChart from "@/components/charts/FlowChart";
import ForeignChart from "@/components/charts/ForeignChart";
import CorrelationHeatmap from "@/components/charts/CorrelationHeatmap";
import QuintileChart from "@/components/charts/QuintileChart";
import EventStudy from "@/components/charts/EventStudy";
import PredictionAccuracyChart from "@/components/charts/PredictionAccuracyChart";
import AddToWatchlist from "@/components/AddToWatchlist";

const pct = (n: number | null) => (n == null ? "-" : (n * 100).toFixed(2) + "%");
const won = (n: number | null) =>
  n == null ? "-" : Math.round(n).toLocaleString("ko-KR") + "원";

const GROUP_KR: Record<string, string> = {
  foreign: "외국인",
  institution: "기관",
  retail: "개인",
};

/** Plain-language takeaway from the 5d-window / 5d-horizon Spearman per group. */
function takeaways(correlations: any[]): string[] {
  const out: string[] = [];
  for (const g of ["foreign", "institution", "retail"]) {
    const row = correlations.find(
      (r) => r.investor_group === g && r.flow_window === 5 && r.horizon === 5
    );
    const s = row?.spearman;
    if (s == null) continue;
    const dir = s > 0.05 ? "상승" : s < -0.05 ? "하락" : "뚜렷한 방향성 없음";
    const strength = Math.abs(s) > 0.15 ? "뚜렷하게" : Math.abs(s) > 0.05 ? "약하게" : "";
    if (dir === "뚜렷한 방향성 없음") {
      out.push(`${GROUP_KR[g]} 매수세와 향후 5일 수익률의 관계는 뚜렷하지 않음 (ρ=${s.toFixed(2)}).`);
    } else {
      out.push(
        `${GROUP_KR[g]} 매수세가 강할수록 향후 5일 수익률이 ${strength} ${dir}하는 경향 (ρ=${s.toFixed(2)}).`
      );
    }
  }
  return out;
}

function ProjectionTable({ projections }: { projections: any[] }) {
  return (
    <table>
      <thead>
        <tr>
          <th>기간</th>
          <th>기대수익률</th>
          <th>예측 밴드 (Bear ~ Bull)</th>
          <th>KOSPI 초과확률</th>
        </tr>
      </thead>
      <tbody>
        {projections.map((p: any) => (
          <tr key={p.horizon_days}>
            <td>{p.horizon_days}일</td>
            <td className={p.expected_return >= 0 ? "pos" : "neg"}>
              {pct(p.expected_return)}
            </td>
            <td>
              {won(p.prediction_band?.bear_price)} ~ {won(p.prediction_band?.bull_price)}
            </td>
            <td>{pct(p.prob_outperform_kospi)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default async function StockPage({
  params,
}: {
  params: { ticker: string };
}) {
  const t = params.ticker;
  let overview: any = null;
  let price: any[] = [];
  let flows: any = { by_group: {} };
  let foreign: any[] = [];
  let projection: any = null;
  let accuracy: any = null;
  let error: string | null = null;

  try {
    overview = (await api.stock(t)).data;
    [price, flows, foreign] = await Promise.all([
      api.price(t).then((r) => r.data).catch(() => []),
      api.flows(t).then((r) => r.data).catch(() => ({ by_group: {} })),
      api.foreign(t).then((r) => r.data).catch(() => []),
    ]);
    [projection, accuracy] = await Promise.all([
      api.projection(t).then((r) => r.data).catch(() => null),
      api.predictionAccuracy(t, 5).then((r) => r.data).catch(() => null),
    ]);
  } catch (e: any) {
    error = e.message;
  }

  if (error) return <p className="neg">API 오류: {error}</p>;

  const [correlations, profile, eventResult] = await Promise.all([
    api.correlations(t).then((r) => r.data).catch(() => []),
    api.flowReturnProfile(t, 5).then((r) => r.data).catch(() => ({ groups: {}, horizons: [] })),
    api.events(t, "foreign_accumulation").then((r) => r.data).catch(() => null),
  ]);

  const latestForeign = foreign[foreign.length - 1];
  const tips = takeaways(correlations);
  // Per-model projection groups (internal first; external models follow).
  const modelGroups: any[] =
    projection?.models?.length
      ? projection.models
      : projection?.projections?.length
      ? [{ model: projection.model ?? "gbm_return", source: "internal", projections: projection.projections }]
      : [];

  return (
    <div>
      <h1>
        {overview.name_kr} <span className="muted">{t}</span>
      </h1>

      <div className="grid2">
        <div className="card">
          <div>섹터: {overview.sector ?? "-"}</div>
          <div>종가: {won(overview.close)}</div>
          <div>
            1일 <span className={overview.return_1d >= 0 ? "pos" : "neg"}>{pct(overview.return_1d)}</span>
            {" · "}5일 <span className={overview.return_5d >= 0 ? "pos" : "neg"}>{pct(overview.return_5d)}</span>
            {" · "}20일 <span className={overview.return_20d >= 0 ? "pos" : "neg"}>{pct(overview.return_20d)}</span>
          </div>
          <div className="muted">
            데이터: {overview.as_of} ({overview.freshness_state})
          </div>
          <div style={{ marginTop: 10 }}>
            <AddToWatchlist ticker={t} />
          </div>
        </div>

        <div className="card">
          <h2>ML 예측</h2>
          {modelGroups.length ? (
            modelGroups.map((g: any) => (
              <div key={g.model}>
                {modelGroups.length > 1 && (
                  <h3>
                    {g.source === "internal" ? "기본 모델 (투자자 수급)" : `외부 모델: ${g.model}`}
                  </h3>
                )}
                <ProjectionTable projections={g.projections} />
              </div>
            ))
          ) : (
            <p className="muted">아직 학습된 모델 예측이 없습니다. (train → predict)</p>
          )}
          <p className="note">예측치는 불확실성을 포함하며 확정 가격이 아닙니다.</p>
        </div>

        <div className="card">
          <h2>가격 · 거래량</h2>
          {price.length ? <PriceChart rows={price} /> : <p className="muted">가격 데이터 없음</p>}
        </div>

        <div className="card">
          <h2>투자자 순매수 (개인 · 기관 · 외국인)</h2>
          {Object.keys(flows.by_group ?? {}).length ? (
            <FlowChart byGroup={flows.by_group} />
          ) : (
            <p className="muted">투자자 순매수 데이터 없음</p>
          )}
          <p className="note">
            누적 순매수는 실제 보유량이 아닌 기준일 이후 순매수 누적값입니다.
          </p>
        </div>

        <div className="card">
          <h2>ML 예측 정확도 기록</h2>
          <PredictionAccuracyChart ticker={t} initialHorizon={5} initialData={accuracy} />
        </div>

        {foreign.length > 0 && (
          <div className="card">
            <h2>외국인 보유 (실제 보유)</h2>
            <ForeignChart rows={foreign} />
            {latestForeign && (
              <div className="muted">
                최신 보유비율 {pct(latestForeign.foreign_ownership_pct)} · 보유주식수{" "}
                {Math.round(latestForeign.foreign_held_shares).toLocaleString("ko-KR")}
              </div>
            )}
          </div>
        )}

        <div className="card span2">
          <h2>매수세 → 향후 수익률 관계</h2>
          {tips.length > 0 && (
            <ul className="muted" style={{ marginTop: 0 }}>
              {tips.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          )}

          <div className="grid3">
            <div>
              <h3>① 상관관계 (투자자 × 향후 기간, Spearman)</h3>
              {correlations.length ? (
                <CorrelationHeatmap rows={correlations} flowWindow={5} />
              ) : (
                <p className="muted">상관 데이터 없음</p>
              )}
            </div>

            <div>
              <h3>② 매수세 강도별 평균 수익률 (분위 분석)</h3>
              <QuintileChart profile={profile} />
            </div>

            <div>
              <h3>③ 신호 발생 후 수익률 (이벤트 스터디)</h3>
              {eventResult ? (
                <EventStudy ticker={t} initialType="foreign_accumulation" initialResult={eventResult} />
              ) : (
                <p className="muted">이벤트 데이터 없음</p>
              )}
            </div>
          </div>
          <p className="note">
            상관·이벤트 분석은 인과관계가 아닌 과거 통계적 경향이며, 표본 수가 적을수록
            신뢰도가 낮습니다.
          </p>
        </div>
      </div>
    </div>
  );
}
