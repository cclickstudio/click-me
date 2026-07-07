'use client';
// 시뮬 결과 화면 재사용 컴포넌트 — /simulation 실행 흐름과 /simulation/[id]/result 라우트가 공용.
// SimRunResult 한 건을 받아 4대 KPI·광고해석·루브릭·페르소나반응·DebatePanel·최종 ReportView를 그린다.

import { useEffect, useState } from 'react';
import { DebatePanel } from '@/components/simulator/DebatePanel';
import { SimulationReportView } from '@/components/simulator/SimulationReportView';
import { ExecuteFromSimulation } from '@/components/manage/ExecuteFromSimulation';
import { KpiCard } from '@/components/ui/KpiCard';
import { formatPercent } from '@/lib/utils';
import type { ReportView, SimRunResult } from '@/lib/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
// 광고 이미지 URL — 백엔드 프록시 상대경로(/api/...)면 API_BASE를 붙인다. http(s)는 그대로.
const assetSrc = (u?: string | null) =>
  u && u.startsWith('/') ? `${API_BASE}${u}` : (u ?? undefined);

/* ─── enum 한글 라벨(백엔드 contracts/enums.py 동기화) ─── */
const EMOTION_LABEL: Record<string, string> = {
  curiosity: '호기심',
  delight: '즐거움',
  empathy: '공감',
  trust: '신뢰',
  indifference: '무관심',
  annoyance: '거부감',
  distrust: '불신',
  other: '기타',
};
const REJECTION_LABEL: Record<string, string> = {
  irrelevant: '무관함',
  offensive: '불쾌함',
  overpriced: '비쌈',
  overpromise: '과장',
  distrust: '불신',
  ad_fatigue: '광고 피로',
  other: '기타',
};
const DROP_LABEL: Record<string, string> = {
  no_reason_to_explore: '탐색 동기 없음',
  price_concern: '가격 부담',
  low_relevance: '낮은 관련성',
  unclear_message: '메시지 불명확',
  distrust: '불신',
  other: '기타',
};
const GENDER_LABEL: Record<string, string> = { M: '남성', F: '여성' };
const OCEAN_LABEL: Record<string, string> = {
  openness: '개방성',
  conscientiousness: '성실성',
  extraversion: '외향성',
  agreeableness: '친화성',
  neuroticism: '신경성',
};

const cardCls =
  'bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 transition-colors';

function aisasFunnel(a: SimRunResult['reactions'][number]['aisas']): string {
  const stages: [keyof typeof a, string][] = [
    ['attention', 'A'],
    ['interest', 'I'],
    ['search', 'S'],
    ['action', 'A'],
    ['share', 'S'],
  ];
  return stages.map(([k, label]) => (a[k] ? label : '·')).join('');
}

interface Props {
  result: SimRunResult;
  adTitle?: string;
  adDescription?: string;
  // DB에 저장된 통합 리포트(콜드·새로고침·패널 진입 복원용). 없으면 null.
  initialReportView?: ReportView | null;
  // 실행 흐름에서만 '새 시뮬레이션' 버튼 노출(라우트 진입 시엔 숨김).
  onReset?: () => void;
  // 헤더 우측 액션 슬롯(상세 페이지의 삭제/복원 등) — 제목과 한 row로 정렬.
  headerAction?: React.ReactNode;
}

export function SimulationResultView({
  result,
  adTitle,
  adDescription,
  initialReportView,
  onReset,
  headerAction,
}: Props) {
  const [showFailed, setShowFailed] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  type ResultTab = 'overview' | 'personas' | 'debate';
  const [tab, setTab] = useState<ResultTab>('overview');
  const [showDetails, setShowDetails] = useState(false); // 개요 탭 '더보기' 접이식
  // 통합 리포트('최종 결과' 영역 단일 소스) — 저장본을 먼저 보여주고, 새 토론 완료 시 DebatePanel이 덮어쓴다.
  const [reportView, setReportView] = useState<ReportView | null>(
    initialReportView ?? null
  );

  // 콜드 진입 시 savedReport(initialReportView)는 비동기로 늦게 도착 — 도착하면 반영한다.
  // (useState 초기값만으론 늦은 prop을 놓쳐 최종 결과가 안 뜬다. 토론을 새로 돌리면 onReportView가 덮어씀.)
  useEffect(() => {
    if (initialReportView) setReportView(initialReportView);
  }, [initialReportView]);

  const toggleExpand = (id: string) =>
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const agg = result.aggregate;
  const reactions = result.reactions ?? [];
  const passed = reactions.filter(r => r.qa_passed);

  // 구매의도 1~5 분포(F7) — 평균만 단언하지 말고 분포 전체를 보여준다. QA 통과 반응 우선.
  // SSR 분포(purchase_intent_dist)가 있으면 페르소나별 확률분포의 가중 평균(비율)을 우선 사용.
  const purchaseDist = (() => {
    const source = passed.length ? passed : reactions;
    const probs = [0, 0, 0, 0, 0];
    let wsum = 0;
    for (const r of source) {
      const rp = r.purchase_intent_dist?.raw_probs;
      if (rp && rp.length === 5) {
        const w = r.weight ?? 1;
        rp.forEach((p, i) => (probs[i] += p * w));
        wsum += w;
      }
    }
    if (wsum > 0) {
      return {
        ratios: probs.map(p => p / wsum),
        counts: null as number[] | null,
        total: source.length,
        ssr: true,
      };
    }
    const counts = [0, 0, 0, 0, 0];
    let total = 0;
    for (const r of source) {
      const pi = Math.round(r.purchase_intent);
      if (pi >= 1 && pi <= 5) {
        counts[pi - 1] += 1;
        total += 1;
      }
    }
    return {
      ratios: counts.map(c => (total ? c / total : 0)),
      counts: counts as number[] | null,
      total,
      ssr: false,
    };
  })();
  // 거부율 사유 분해(F8) — 비율만 보지 말고 사유별로 분해해서 처방까지 이어지게(§4대 KPI 원칙).
  const rejectionDist = (() => {
    const source = passed.length ? passed : reactions;
    const counts = new Map<string, number>();
    let total = 0;
    for (const r of source) {
      if (!r.rejected) continue;
      const tag = r.rejection_reason_tag ?? 'other';
      counts.set(tag, (counts.get(tag) ?? 0) + 1);
      total += 1;
    }
    return {
      total,
      entries: [...counts.entries()].sort((a, b) => b[1] - a[1]),
    };
  })();
  // KOBACO(2019 MCR) 참고치(A-2) — 조회만, 우리 KPI와 척도가 달라 절대 비교·환산 없이 원문 병기.
  const kobaco = agg?.payload?.kobaco_reference as
    | {
        declared_category: string;
        kobaco_category: string;
        purchase_intent_pct: number | null;
        tv_ad_influence_pct: number | null;
        note: string;
      }
    | undefined;
  const failed = reactions.filter(r => !r.qa_passed);
  const ad = result.ad_analysis;
  const fit = result.objective_fit ?? null;
  const ocean = result.ocean_segments ?? null;
  const shown = showFailed ? reactions : passed;
  const personaMap = new Map(
    (result.personas ?? []).map(p => [p.persona_id, p])
  );

  return (
    <div className='px-8 py-8 max-w-7xl mx-auto space-y-6'>
      <div className='flex items-center justify-between'>
        <div>
          <h1 className='text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]'>
            시뮬레이터 결과
          </h1>
          <p className='text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1'>
            run_id {result.run_id.slice(0, 8)} · 반응 {reactions.length}건 (QA
            통과 {passed.length}){result.simulation_id && ' · DB 저장됨'}
          </p>
        </div>
        {(headerAction || onReset || result.simulation_id) && (
          <div className='flex items-center gap-2'>
            {/* DB 저장된 시뮬만 집행 가능 — created_campaigns.simulation_id로 성과비교 연결. */}
            {result.simulation_id && agg && (
              <ExecuteFromSimulation
                simulationId={result.simulation_id}
                defaultName={adTitle}
                clickIntentRate={agg.click_intent_rate}
                rejectionRate={agg.rejection_rate}
              />
            )}
            {headerAction}
            {onReset && (
              <button
                onClick={onReset}
                className='px-4 py-2 border border-[#E5E8EB] dark:border-[#2D3748] rounded-lg text-sm text-[#8B95A1] dark:text-[#6B7280] hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors'>
                새 시뮬레이션
              </button>
            )}
          </div>
        )}
      </div>

      {/* 히어로 — 목표달성 카드 + 4대 KPI 한 줄 (블루 모노크롬, 전면 배경 없음) */}
      {agg && (
        <>
          <div className='grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4'>
            {fit && (
              <div className='lg:col-span-2 col-span-2 bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-5'>
                <p className='text-xs text-[#8B95A1] dark:text-[#6B7280]'>
                  목표 달성 가능성 · {fit.objective}
                </p>
                <div className='flex items-baseline gap-2 mt-1'>
                  <span className='text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]'>
                    {fit.grade}
                  </span>
                  <span className='text-xs text-[#8B95A1] dark:text-[#6B7280]'>
                    지수 {fit.score}/100
                  </span>
                </div>
                <div className='mt-2.5 h-1.5 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] overflow-hidden'>
                  <div
                    className='h-full rounded-full bg-[#3182F6] dark:bg-[#5B9DF9]'
                    style={{ width: `${fit.score}%` }}
                  />
                </div>
              </div>
            )}
            <KpiCard
              label='클릭 의향률 (AISAS Action)'
              value={formatPercent(agg.click_intent_rate)}
              sub={`95% CI ${formatPercent(agg.ci_low)} ~ ${formatPercent(agg.ci_high)}`}
            />
            <KpiCard
              label='구매의도 (1~5 평균)'
              value={agg.purchase_intent.toFixed(2)}
              sub={agg.variance_warning ? '⚠ 응답 집중 경고' : undefined}
              trend={agg.variance_warning ? 'down' : 'neutral'}
            />
            <KpiCard label='신뢰도 (1~5 평균)' value={agg.trust_avg.toFixed(2)} />
            <KpiCard
              label='거부율'
              value={formatPercent(agg.rejection_rate)}
              sub={agg.rejection_rate > 0.3 ? '▲ 30% 초과 주의' : undefined}
              trend={agg.rejection_rate > 0.3 ? 'down' : 'neutral'}
            />
          </div>
          <div className='flex flex-wrap gap-2 text-xs'>
            <span className='px-3 py-1 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]'>
              유효표본수(effective_n) {agg.effective_n}
            </span>
            <span className='px-3 py-1 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]'>
              집계 엔진 {agg.engine_version}
            </span>
            {ad?.intent_mismatch && (
              <span className='px-3 py-1 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[#D97706]'>
                ⚠ 의도-반응 불일치 감지
              </span>
            )}
          </div>
        </>
      )}

      {/* 탭 바 */}
      <div className='flex gap-6 border-b border-[#E5E8EB] dark:border-[#2D3748]'>
        {(
          [
            ['overview', '개요'],
            ['personas', `페르소나 반응 (${reactions.length})`],
            ['debate', '토론·리포트'],
          ] as [ResultTab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`pb-2.5 text-sm font-medium -mb-px border-b-2 transition-colors ${
              tab === key
                ? 'border-[#3182F6] text-[#3182F6]'
                : 'border-transparent text-[#8B95A1] dark:text-[#6B7280] hover:text-[#4E5968]'
            }`}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className='space-y-6'>
          <div className='grid grid-cols-1 md:grid-cols-2 gap-6'>
            {/* 구매의도 분포(F7) — 평균 옆에 1~5점 분포 전체를 막대로. 평균 단언 방지 */}
            {agg && purchaseDist.total > 0 && (
              <div className={cardCls}>
                <div className='flex items-center justify-between mb-1'>
                  <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]'>
                    구매의도 분포 (1~5점)
                    {purchaseDist.ssr && (
                      <span className='ml-1.5 px-1.5 py-0.5 rounded bg-[#EBF4FF] dark:bg-[#1E3A5F] text-[10px] font-medium text-[#3182F6] dark:text-[#5B9DF9]'>
                        SSR 분포
                      </span>
                    )}
                  </h2>
                  <span className='text-[11px] text-[#8B95A1] dark:text-[#6B7280]'>
                    평균 {agg.purchase_intent.toFixed(2)}점 · 표본{' '}
                    {purchaseDist.total}명
                  </span>
                </div>
                <p className='text-[11px] text-[#8B95A1] dark:text-[#6B7280] mb-3'>
                  {purchaseDist.ssr
                    ? '임베딩 유사도(SSR)로 산출한 확률분포의 가중 평균입니다. 평균값 하나로 단정하지 말고 퍼짐을 함께 보세요.'
                    : '평균값 하나로 단정하지 말고, 점수가 어떻게 퍼져 있는지 함께 보세요.'}
                </p>
                <div className='space-y-1.5'>
                  {[5, 4, 3, 2, 1].map(score => {
                    const ratio = purchaseDist.ratios[score - 1] * 100;
                    const c = purchaseDist.counts?.[score - 1];
                    return (
                      <div key={score} className='flex items-center gap-2 text-xs'>
                        <span className='w-7 shrink-0 text-right text-[#4E5968] dark:text-[#9CA3AF]'>
                          {score}점
                        </span>
                        <div className='flex-1 h-3.5 rounded bg-[#F2F4F6] dark:bg-[#252D3D] overflow-hidden'>
                          <div
                            className='h-full rounded bg-[#3182F6] dark:bg-[#5B9DF9] transition-all'
                            style={{ width: `${ratio}%` }}
                          />
                        </div>
                        <span className='w-16 shrink-0 text-right tabular-nums text-[#8B95A1] dark:text-[#6B7280]'>
                          {c != null
                            ? `${c}명 (${ratio.toFixed(0)}%)`
                            : `${ratio.toFixed(1)}%`}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* 거부율 사유 분해(F8) — 비율만 보지 말고 왜 거부했는지 사유별로. 처방까지 이어지게 */}
            {agg && rejectionDist.total > 0 && (
              <div className={cardCls}>
                <div className='flex items-center justify-between mb-1'>
                  <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]'>
                    거부 사유 분해
                  </h2>
                  <span className='text-[11px] text-[#8B95A1] dark:text-[#6B7280]'>
                    거부율 {formatPercent(agg.rejection_rate)} · 거부 {rejectionDist.total}명
                  </span>
                </div>
                <p className='text-[11px] text-[#8B95A1] dark:text-[#6B7280] mb-3'>
                  거부 비율만 보지 말고, 어떤 사유가 몰려 있는지로 개선 방향을 잡으세요.
                </p>
                <div className='space-y-1.5'>
                  {rejectionDist.entries.map(([tag, c]) => {
                    const ratio = rejectionDist.total ? (c / rejectionDist.total) * 100 : 0;
                    return (
                      <div key={tag} className='flex items-center gap-2 text-xs'>
                        <span className='w-20 shrink-0 text-right text-[#4E5968] dark:text-[#9CA3AF]'>
                          {REJECTION_LABEL[tag] ?? tag}
                        </span>
                        <div className='flex-1 h-3.5 rounded bg-[#F2F4F6] dark:bg-[#252D3D] overflow-hidden'>
                          <div
                            className='h-full rounded bg-[#1B64DA] dark:bg-[#5B9DF9] transition-all'
                            style={{ width: `${ratio}%` }}
                          />
                        </div>
                        <span className='w-16 shrink-0 text-right tabular-nums text-[#8B95A1] dark:text-[#6B7280]'>
                          {c}명 ({ratio.toFixed(0)}%)
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          <div className='grid grid-cols-1 md:grid-cols-2 gap-6'>
            {/* 성향별 반응(OCEAN) — 연령·성별로는 못 주는 성격 기반 분해. 비교 가능한 차원이 있을 때만 */}
            {ocean && ocean.by_dimension.some(d => d.click_gap !== null) && (
              <div className={cardCls}>
                <div className='flex items-center justify-between mb-3'>
                  <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]'>
                    성향별 반응 (OCEAN)
                  </h2>
                  <span className='text-[11px] text-[#8B95A1] dark:text-[#6B7280]'>
                    성격 z-score 높음(≥+0.4)·낮음(≤−0.4) 비교
                  </span>
                </div>
                {ocean.top_driver && (
                  <div className='mb-4 px-4 py-3 rounded-xl bg-[#EBF3FF] dark:bg-[#1A2436] text-sm text-[#1B64DA] dark:text-[#7AB0FF]'>
                    가장 반응을 가르는 성향: <b>{ocean.top_driver.dimension_ko}</b> —{' '}
                    {ocean.top_driver.direction} (클릭의향 격차{' '}
                    {formatPercent(Math.abs(ocean.top_driver.click_gap))})
                  </div>
                )}
                <div className='space-y-2'>
                  <div className='grid grid-cols-[1fr_4rem_4rem_4rem] gap-3 text-[11px] text-[#8B95A1] dark:text-[#6B7280] px-1'>
                    <span>성향</span>
                    <span className='text-right'>높음 클릭</span>
                    <span className='text-right'>낮음 클릭</span>
                    <span className='text-right'>격차</span>
                  </div>
                  {ocean.by_dimension
                    .filter(d => d.click_gap !== null && d.high && d.low)
                    .map(d => (
                      <div
                        key={d.dimension}
                        className='grid grid-cols-[1fr_4rem_4rem_4rem] gap-3 items-center text-sm px-1'>
                        <span className='text-[#191F28] dark:text-[#F2F4F6]'>
                          {d.dimension_ko}
                          {d.low_confidence && (
                            <span className='ml-1 text-[11px] text-[#F4A100]'>⚠</span>
                          )}
                        </span>
                        <span className='text-right tabular-nums text-[#4E5968] dark:text-[#9CA3AF]'>
                          {formatPercent(d.high!.click_intent_rate)}
                        </span>
                        <span className='text-right tabular-nums text-[#4E5968] dark:text-[#9CA3AF]'>
                          {formatPercent(d.low!.click_intent_rate)}
                        </span>
                        <span
                          className={`text-right tabular-nums font-semibold ${
                            (d.click_gap ?? 0) >= 0
                              ? 'text-[#1B64DA]'
                              : 'text-[#191F28] dark:text-[#F2F4F6]'
                          }`}>
                          {(d.click_gap ?? 0) >= 0 ? '+' : ''}
                          {formatPercent(d.click_gap ?? 0)}
                        </span>
                      </div>
                    ))}
                </div>
                <p className='text-[11px] text-[#B0B8C1] dark:text-[#4B5563] mt-3'>
                  ⚠는 표본이 적어 신뢰가 낮은 성향입니다. 절대값이 아닌 성향 간 상대
                  비교로 참고하세요.
                </p>
              </div>
            )}

            {/* 광고 해석 */}
            {ad && (
              <div className={cardCls}>
                <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-3'>
                  광고 해석 (VLM/LLM 감지)
                </h2>
                {result.ad_asset_url && (
                  // 업로드된 광고 크리에이티브 — presigned URL(~1h). 텍스트 시뮬이면 미표시.
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={assetSrc(result.ad_asset_url)}
                    alt='광고 크리에이티브'
                    className='mb-4 h-auto max-h-56 w-full object-contain rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#11151F]'
                  />
                )}
                <div className='grid grid-cols-2 md:grid-cols-4 gap-3 text-sm'>
                  {[
                    ['감지 업종', ad.detected_industry],
                    ['감지 목표', ad.detected_objective],
                    ['감지 타깃', ad.detected_target],
                    ['감지 메시지', ad.detected_message],
                  ].map(([k, v]) => (
                    <div key={k}>
                      <p className='text-xs text-[#8B95A1] dark:text-[#6B7280]'>
                        {k}
                      </p>
                      <p className='text-[#191F28] dark:text-[#F2F4F6] mt-0.5'>
                        {v || '—'}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* 더보기 — 루브릭·KOBACO·목표달성 근거 (기본 접힘) */}
          <div>
            <button
              onClick={() => setShowDetails(v => !v)}
              className='text-xs text-[#8B95A1] dark:text-[#6B7280] hover:text-[#3182F6]'>
              {showDetails ? '▴ 상세 접기' : '▸ 더보기 (루브릭 · KOBACO 참고치 · 목표달성 근거)'}
            </button>
            {showDetails && (
              <div className='mt-4 space-y-6'>
                {/* 루브릭 */}
                {result.rubric_scores.length > 0 && (
                  <div className={cardCls}>
                    <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-3'>
                      루브릭 평가 (차원별 점수)
                    </h2>
                    <div className='space-y-2.5'>
                      {result.rubric_scores.map(s => (
                        <div key={s.dimension} className='flex items-center gap-3'>
                          <span className='w-40 text-xs text-[#4E5968] dark:text-[#9CA3AF] truncate'>
                            {s.dimension}
                          </span>
                          <div className='flex-1 h-2 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] overflow-hidden'>
                            <div
                              className='h-full bg-[#3182F6] rounded-full'
                              style={{ width: `${s.score}%` }}
                            />
                          </div>
                          <span className='w-10 text-right text-xs font-semibold text-[#191F28] dark:text-[#F2F4F6]'>
                            {s.score}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* KOBACO(2019 MCR) 참고치(A-2) — 절대 비교 아님, 카테고리 근사 매핑 방향·상대크기 참고용 */}
                {kobaco && (
                  <div className={cardCls}>
                    <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-1'>
                      KOBACO 참고치
                    </h2>
                    <p className='text-[11px] text-[#8B95A1] dark:text-[#6B7280] mb-3'>
                      {kobaco.declared_category} → {kobaco.kobaco_category} 카테고리 근사 매핑.
                      우리 KPI와 척도가 달라 절대 비교가 아니라 방향·상대크기 참고용입니다.
                    </p>
                    <div className='grid grid-cols-2 gap-3'>
                      {kobaco.purchase_intent_pct != null && (
                        <div className='rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D] px-3 py-2'>
                          <p className='text-[10px] text-[#8B95A1]'>구매/교체 의향 비율</p>
                          <p className='font-bold text-[#191F28] dark:text-[#F2F4F6]'>
                            {formatPercent(kobaco.purchase_intent_pct)}
                          </p>
                        </div>
                      )}
                      {kobaco.tv_ad_influence_pct != null && (
                        <div className='rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D] px-3 py-2'>
                          <p className='text-[10px] text-[#8B95A1]'>TV광고 영향력</p>
                          <p className='font-bold text-[#191F28] dark:text-[#F2F4F6]'>
                            {formatPercent(kobaco.tv_ad_influence_pct)}
                          </p>
                        </div>
                      )}
                    </div>
                    <p className='text-[10px] text-[#B0B8C1] dark:text-[#4B5563] mt-2'>
                      출처: 2019 KOBACO MCR(소비자행태조사)
                    </p>
                  </div>
                )}

                {fit && (
                  <div className={cardCls}>
                    <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-2'>
                      목표달성 판단 근거
                    </h2>
                    <p className='text-sm text-[#4E5968] dark:text-[#9CA3AF]'>{fit.rationale}</p>
                    <div className='flex flex-wrap gap-2 mt-3'>
                      {fit.contributions.map(c => (
                        <span
                          key={c.label}
                          className='text-[11px] px-2 py-1 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]'>
                          {c.label} {Math.round(c.value * 100)}%
                          <span className='opacity-60'> ·가중 {Math.round(c.weight * 100)}%</span>
                        </span>
                      ))}
                    </div>
                    <p className='text-[11px] text-[#B0B8C1] dark:text-[#4B5563] mt-2'>
                      {fit.low_confidence && '⚠ 표본이 적어 신뢰가 낮습니다. '}
                      실측이 아닌 시뮬 신호 기반 상대 지표입니다(exploratory).
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 분석 데이터(왼쪽) + 토론(오른쪽) 가로 배치 — stretch로 좌열이 우열 높이까지 확장 */}
      <div className='grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch'>
        {/* 왼쪽: 분석 데이터 — 래퍼는 row 높이를 우열(토론)에 맡기고, 내부는 그 높이를 채움 */}
        <div className='relative min-h-0'>
          <div className='flex flex-col gap-6 lg:absolute lg:inset-0'>
            {/* 페르소나 반응 — flex-1로 좌열 남은 높이를 채우고, 내부 영역 스크롤 */}
            <div className={`${cardCls} flex-1 flex flex-col min-h-0`}>
              <div className='flex items-center justify-between mb-3'>
                <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]'>
                  페르소나 반응 ({shown.length})
                </h2>
                {failed.length > 0 && (
                  <button
                    onClick={() => setShowFailed(v => !v)}
                    className='text-xs text-[#8B95A1] dark:text-[#6B7280] hover:text-[#3182F6]'>
                    {showFailed
                      ? 'QA 통과분만 보기'
                      : `QA 탈락 ${failed.length}건 포함`}
                  </button>
                )}
              </div>
              <div className='space-y-3 flex-1 min-h-0 overflow-y-auto'>
                {shown.map(r => {
                  const p = personaMap.get(r.persona_id);
                  const isOpen = expanded.has(r.persona_id);
                  return (
                    <div
                      key={r.persona_id}
                      className={`border-l-2 pl-3 py-1 ${
                        r.qa_passed
                          ? 'border-[#3182F6]'
                          : 'border-[#F04452] opacity-60'
                      }`}>
                      {/* 페르소나 기본 정보 */}
                      <div className='flex flex-wrap items-center gap-2 text-[11px] mb-1'>
                        <button
                          type='button'
                          onClick={() => p && toggleExpand(r.persona_id)}
                          className='font-medium text-[#191F28] dark:text-[#F2F4F6] hover:text-[#3182F6]'>
                          {p ? (
                            <>
                              {p.age}세 {GENDER_LABEL[p.gender] ?? p.gender} ·{' '}
                              {p.region}
                              <span className='ml-1 text-[#B0B8C1] dark:text-[#4B5563]'>
                                {isOpen ? '▲' : '▼'}
                              </span>
                            </>
                          ) : (
                            r.persona_id
                          )}
                        </button>
                        <span className='text-[10px] text-[#B0B8C1] dark:text-[#4B5563]'>
                          {r.persona_id}
                        </span>
                      </div>

                      {/* 반응 요약 */}
                      <div className='flex flex-wrap items-center gap-2 text-[11px] mb-1'>
                        <span className='font-mono text-[#3182F6]'>
                          {aisasFunnel(r.aisas)}
                        </span>
                        <span className='text-[#4E5968] dark:text-[#9CA3AF]'>
                          구매 {r.purchase_intent}·신뢰 {r.trust}
                        </span>
                        <span className='px-1.5 py-0.5 rounded bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]'>
                          {EMOTION_LABEL[r.emotion_tag] ?? r.emotion_tag}
                        </span>
                        {r.rejected && (
                          <span className='px-1.5 py-0.5 rounded bg-[#FEF2F2] dark:bg-[#3B0D0D] text-[#DC2626]'>
                            거부
                            {r.rejection_reason_tag
                              ? `·${REJECTION_LABEL[r.rejection_reason_tag] ?? r.rejection_reason_tag}`
                              : ''}
                          </span>
                        )}
                        {r.drop_stage && (
                          <span className='text-[#B0B8C1] dark:text-[#4B5563]'>
                            이탈 {r.drop_stage}
                            {r.drop_reason_tag
                              ? `·${DROP_LABEL[r.drop_reason_tag] ?? r.drop_reason_tag}`
                              : ''}
                          </span>
                        )}
                        {r.exposure_context && (
                          <span className='text-[#B0B8C1] dark:text-[#4B5563]'>
                            노출 {r.exposure_context}
                          </span>
                        )}
                        {!r.qa_passed && (
                          <span className='text-[#F04452]'>
                            QA 탈락
                            {r.qa_fail_reason ? `·${r.qa_fail_reason}` : ''}
                          </span>
                        )}
                      </div>

                      {r.utterance && (
                        <p className='text-sm text-[#4E5968] dark:text-[#9CA3AF]'>
                          {r.utterance}
                        </p>
                      )}

                      {/* 페르소나 상세 (펼침) */}
                      {isOpen && p && (
                        <div className='mt-2 p-3 rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D] text-[11px] space-y-2'>
                          <div>
                            <span className='text-[#8B95A1] dark:text-[#6B7280]'>
                              OCEAN
                            </span>
                            <div className='flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5 text-[#4E5968] dark:text-[#9CA3AF]'>
                              {Object.entries(p.ocean).map(([dim, v]) => (
                                <span key={dim}>
                                  {OCEAN_LABEL[dim] ?? dim} {v.toFixed(2)}
                                </span>
                              ))}
                            </div>
                          </div>
                          {Object.keys(p.consumption_values).length > 0 && (
                            <div>
                              <span className='text-[#8B95A1] dark:text-[#6B7280]'>
                                소비가치
                              </span>
                              <p className='mt-0.5 text-[#4E5968] dark:text-[#9CA3AF] break-all'>
                                {JSON.stringify(p.consumption_values)}
                              </p>
                            </div>
                          )}
                          {Object.keys(p.media_behavior).length > 0 && (
                            <div>
                              <span className='text-[#8B95A1] dark:text-[#6B7280]'>
                                미디어 행동
                              </span>
                              <p className='mt-0.5 text-[#4E5968] dark:text-[#9CA3AF] break-all'>
                                {JSON.stringify(p.media_behavior)}
                              </p>
                            </div>
                          )}
                          {Object.keys(p.socioeconomic).length > 0 && (
                            <div>
                              <span className='text-[#8B95A1] dark:text-[#6B7280]'>
                                사회경제
                              </span>
                              <p className='mt-0.5 text-[#4E5968] dark:text-[#9CA3AF] break-all'>
                                {JSON.stringify(p.socioeconomic)}
                              </p>
                            </div>
                          )}
                          {p.profile_narrative && (
                            <div>
                              <span className='text-[#8B95A1] dark:text-[#6B7280]'>
                                프로필 서사
                              </span>
                              <p className='mt-0.5 text-[#4E5968] dark:text-[#9CA3AF]'>
                                {p.profile_narrative}
                              </p>
                            </div>
                          )}
                          <span className='inline-block text-[10px] text-[#B0B8C1] dark:text-[#4B5563]'>
                            가중치 {p.weight}
                          </span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {/* 오른쪽: 토론 (채팅 + 결과 박스) */}
        <div>
          <DebatePanel
            reactions={reactions}
            adAnalysis={ad ?? null}
            personas={result.personas ?? []}
            simulationId={result.simulation_id}
            objectiveFit={fit}
            rubricScores={result.rubric_scores}
            adTitle={adTitle || undefined}
            adDescription={adDescription || undefined}
            onReportView={setReportView}
          />
        </div>
      </div>

      {/* 최종 결과 — 통합 리포트(화면 = PDF 단일 소스). 토론 완료 후 채워짐. */}
      <div className={cardCls}>
        {reportView ? (
          <SimulationReportView rv={reportView} />
        ) : (
          <>
            <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-2'>
              최종 결과
            </h2>
            <p className='text-xs text-[#8B95A1] dark:text-[#6B7280]'>
              토론이 끝나면 종합 리포트가 여기에 표시됩니다 (PDF 다운로드 포함).
            </p>
          </>
        )}
      </div>

      <p className='text-xs text-[#B0B8C1] dark:text-[#4B5563] border-t border-[#E5E8EB] dark:border-[#2D3748] pt-4'>
        본 결과는 AI 시뮬레이션 기반 예측이며 의사결정 보조 근거입니다. 클릭
        의향률은 실측 CTR이 아닙니다(calibration 전).
      </p>
    </div>
  );
}
