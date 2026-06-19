'use client';
// 시뮬 결과 화면 재사용 컴포넌트 — /simulation 실행 흐름과 /simulation/[id]/result 라우트가 공용.
// SimRunResult 한 건을 받아 4대 KPI·광고해석·루브릭·페르소나반응·DebatePanel·최종 ReportView를 그린다.

import { useState } from 'react';
import { DebatePanel } from '@/components/simulator/DebatePanel';
import { SimulationReportView } from '@/components/simulator/SimulationReportView';
import { KpiCard } from '@/components/ui/KpiCard';
import { formatPercent } from '@/lib/utils';
import type { ObjectiveFit, ReportView, SimRunResult } from '@/lib/types';

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
}

export function SimulationResultView({
  result,
  adTitle,
  adDescription,
  initialReportView,
  onReset,
}: Props) {
  const [showFailed, setShowFailed] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  // 통합 리포트('최종 결과' 영역 단일 소스) — 저장본을 먼저 보여주고, 새 토론 완료 시 DebatePanel이 덮어쓴다.
  const [reportView, setReportView] = useState<ReportView | null>(
    initialReportView ?? null
  );

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
  const failed = reactions.filter(r => !r.qa_passed);
  const ad = result.ad_analysis;
  const fit = result.objective_fit ?? null;
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
        {onReset && (
          <button
            onClick={onReset}
            className='px-4 py-2 border border-[#E5E8EB] dark:border-[#2D3748] rounded-lg text-sm text-[#8B95A1] dark:text-[#6B7280] hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors'>
            새 시뮬레이션
          </button>
        )}
      </div>

      {/* 캠페인 목표 달성 가능성 (결정론 룰 — 상대 지표, exploratory) */}
      {fit &&
        ((f: ObjectiveFit) => {
          const tone =
            f.grade === '높음'
              ? {
                  text: 'text-[#15803D] dark:text-[#4ADE80]',
                  bar: 'bg-[#22C55E]',
                  bg: 'bg-[#F0FDF4] dark:bg-[#0B2E13]',
                  border: 'border-[#BBF7D0] dark:border-[#14532D]',
                }
              : f.grade === '보통'
                ? {
                    text: 'text-[#B45309] dark:text-[#F4A100]',
                    bar: 'bg-[#F4A100]',
                    bg: 'bg-[#FFF8E6] dark:bg-[#2D2000]',
                    border: 'border-[#FDE68A] dark:border-[#78350F]',
                  }
                : {
                    text: 'text-[#DC2626] dark:text-[#FCA5A5]',
                    bar: 'bg-[#F04452]',
                    bg: 'bg-[#FEF2F2] dark:bg-[#3B0D0D]',
                    border: 'border-[#FECACA] dark:border-[#7F1D1D]',
                  };
          return (
            <div className={`rounded-2xl border p-6 ${tone.bg} ${tone.border}`}>
              <div className='flex items-start justify-between gap-4 flex-wrap'>
                <div>
                  <p className='text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280]'>
                    캠페인 목표 달성 가능성
                  </p>
                  <p className='text-sm text-[#4E5968] dark:text-[#9CA3AF] mt-0.5'>
                    목표: {f.objective}
                  </p>
                </div>
                <div className='flex items-baseline gap-2'>
                  <span className={`text-3xl font-bold ${tone.text}`}>
                    {f.grade}
                  </span>
                  <span className='text-sm text-[#8B95A1] dark:text-[#6B7280]'>
                    지수 {f.score}/100
                  </span>
                </div>
              </div>
              <div className='mt-3 h-2 rounded-full bg-white/60 dark:bg-black/30 overflow-hidden'>
                <div
                  className={`h-full rounded-full ${tone.bar}`}
                  style={{ width: `${f.score}%` }}
                />
              </div>
              <p className='text-sm text-[#4E5968] dark:text-[#9CA3AF] mt-3'>
                {f.rationale}
              </p>
              <div className='flex flex-wrap gap-2 mt-3'>
                {f.contributions.map(c => (
                  <span
                    key={c.label}
                    className='text-[11px] px-2 py-1 rounded-full bg-white/70 dark:bg-black/20 text-[#4E5968] dark:text-[#9CA3AF]'>
                    {c.label} {Math.round(c.value * 100)}%
                    <span className='opacity-60'>
                      {' '}
                      ·가중 {Math.round(c.weight * 100)}%
                    </span>
                  </span>
                ))}
              </div>
              <p className='text-[11px] text-[#B0B8C1] dark:text-[#4B5563] mt-2'>
                {f.low_confidence && '⚠ 표본이 적어 신뢰가 낮습니다. '}
                실측이 아닌 시뮬 신호 기반 상대 지표입니다(exploratory).
              </p>
            </div>
          );
        })(fit)}

      {/* 4대 KPI */}
      {agg && (
        <>
          <div className='grid grid-cols-2 md:grid-cols-4 gap-4'>
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
            <KpiCard
              label='신뢰도 (1~5 평균)'
              value={agg.trust_avg.toFixed(2)}
            />
            <KpiCard
              label='거부율'
              value={formatPercent(agg.rejection_rate)}
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
              <span className='px-3 py-1 rounded-full bg-[#FFF8E6] dark:bg-[#2D2000] text-[#F4A100]'>
                ⚠ 의도-반응 불일치 감지
              </span>
            )}
          </div>
        </>
      )}

      {/* 분석 데이터(왼쪽) + 토론(오른쪽) 가로 배치 — stretch로 좌열이 우열 높이까지 확장 */}
      <div className='grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch'>
        {/* 왼쪽: 분석 데이터 — 래퍼는 row 높이를 우열(토론)에 맡기고, 내부는 그 높이를 채움 */}
        <div className='relative min-h-0'>
          <div className='flex flex-col gap-6 lg:absolute lg:inset-0'>
            {/* 광고 해석 */}
            {ad && (
              <div className={cardCls}>
                <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-3'>
                  광고 해석 (VLM/LLM 감지)
                </h2>
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
