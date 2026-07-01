'use client';
// 1명 심층 분석 뷰(A-1 individual 모드) — 단일 페르소나의 프로필 서사·반응 근거를 강조한 뒤,
// 아래에 기존 SimulationResultView(KPI·해석·리포트)를 그대로 재사용한다.

import { SimulationResultView } from '@/components/simulator/SimulationResultView';
import { formatPercent } from '@/lib/utils';
import type { ReportView, SimRunResult } from '@/lib/types';

const cardCls =
  'bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 transition-colors';

const GENDER_LABEL: Record<string, string> = { M: '남성', F: '여성' };
const OCEAN_LABEL: Record<string, string> = {
  openness: '개방성',
  conscientiousness: '성실성',
  extraversion: '외향성',
  agreeableness: '친화성',
  neuroticism: '신경성',
};
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

// AISAS 5단계 통과 배지 — 통과/이탈을 색으로 구분.
const AISAS_STAGES: [keyof SimRunResult['reactions'][number]['aisas'], string][] = [
  ['attention', '주목'],
  ['interest', '흥미'],
  ['search', '탐색'],
  ['action', '행동'],
  ['share', '공유'],
];

interface Props {
  result: SimRunResult;
  adTitle?: string;
  adDescription?: string;
  initialReportView?: ReportView | null;
  onReset?: () => void;
  headerAction?: React.ReactNode;
}

export function IndividualDeepView({
  result,
  adTitle,
  adDescription,
  initialReportView,
  onReset,
  headerAction,
}: Props) {
  const persona = result.personas?.[0] ?? null;
  const reaction = persona
    ? (result.reactions?.find(r => r.persona_id === persona.persona_id) ??
      result.reactions?.[0] ??
      null)
    : (result.reactions?.[0] ?? null);

  return (
    <div className='space-y-6'>
      {/* 심층 페르소나 히어로 — individual 모드의 핵심(프로필 서사 + 반응 근거) */}
      {persona && (
        <div className='px-8 pt-8 max-w-7xl mx-auto'>
          <div className={`${cardCls} space-y-5`}>
            <div className='flex items-center gap-2'>
              <span className='px-2 py-0.5 rounded-full text-[11px] font-semibold bg-[#EEF4FF] dark:bg-[#1E3A5F] text-[#3182F6]'>
                1명 심층 분석
              </span>
              <h2 className='text-lg font-bold text-[#191F28] dark:text-[#F2F4F6]'>
                {persona.age}세 {GENDER_LABEL[persona.gender] ?? persona.gender}
                {persona.region ? ` · ${persona.region}` : ''}
              </h2>
            </div>

            {/* 프로필 서사 */}
            {persona.profile_narrative && (
              <div>
                <p className='text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280] mb-1'>
                  프로필 서사
                </p>
                <p className='text-sm text-[#4E5968] dark:text-[#9CA3AF] leading-relaxed'>
                  {persona.profile_narrative}
                </p>
              </div>
            )}

            {/* OCEAN 성향 */}
            <div>
              <p className='text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280] mb-1.5'>
                OCEAN 성향
              </p>
              <div className='flex flex-wrap gap-2'>
                {Object.entries(persona.ocean).map(([dim, v]) => (
                  <span
                    key={dim}
                    className='text-[11px] px-2 py-1 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]'>
                    {OCEAN_LABEL[dim] ?? dim} {v.toFixed(2)}
                  </span>
                ))}
              </div>
            </div>

            {/* 반응 근거 — AISAS 퍼널 + 감정 + 발화 */}
            {reaction && (
              <div className='pt-2 border-t border-[#E5E8EB] dark:border-[#2D3748] space-y-3'>
                <div>
                  <p className='text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280] mb-1.5'>
                    반응 경로 (AISAS)
                  </p>
                  <div className='flex flex-wrap gap-1.5'>
                    {AISAS_STAGES.map(([k, lbl]) => {
                      const on = reaction.aisas[k];
                      return (
                        <span
                          key={k}
                          className={`text-[11px] px-2.5 py-1 rounded-lg font-medium ${
                            on
                              ? 'bg-[#EEF4FF] dark:bg-[#1E3A5F] text-[#3182F6]'
                              : 'bg-[#F2F4F6] dark:bg-[#252D3D] text-[#B0B8C1] dark:text-[#4B5563] line-through'
                          }`}>
                          {lbl}
                        </span>
                      );
                    })}
                  </div>
                  {reaction.drop_stage && (
                    <p className='text-[11px] text-[#F04452] mt-1.5'>
                      {reaction.drop_stage} 단계에서 이탈
                      {reaction.drop_reason_tag
                        ? ` · ${reaction.drop_reason_tag}`
                        : ''}
                    </p>
                  )}
                </div>

                <div className='flex flex-wrap items-center gap-2 text-xs'>
                  <span className='px-2 py-1 rounded-lg bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]'>
                    구매의도 {reaction.purchase_intent}/5
                  </span>
                  <span className='px-2 py-1 rounded-lg bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]'>
                    신뢰 {reaction.trust}/5
                  </span>
                  <span className='px-2 py-1 rounded-lg bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]'>
                    감정 {EMOTION_LABEL[reaction.emotion_tag] ?? reaction.emotion_tag}
                  </span>
                  {reaction.rejected && (
                    <span className='px-2 py-1 rounded-lg bg-[#FEF2F2] dark:bg-[#3B0D0D] text-[#DC2626]'>
                      거부
                      {reaction.rejection_reason_tag
                        ? ` · ${reaction.rejection_reason_tag}`
                        : ''}
                    </span>
                  )}
                </div>

                {reaction.utterance && (
                  <blockquote className='text-sm text-[#191F28] dark:text-[#F2F4F6] border-l-2 border-[#3182F6] pl-3 py-1 italic'>
                    “{reaction.utterance}”
                  </blockquote>
                )}
                {reaction.perceived_message && (
                  <p className='text-[11px] text-[#8B95A1] dark:text-[#6B7280]'>
                    인지한 메시지: {reaction.perceived_message}
                  </p>
                )}
              </div>
            )}

            {result.aggregate && (
              <p className='text-[11px] text-[#B0B8C1] dark:text-[#4B5563]'>
                1명 심층 분석은 표본이 1명이라 통계 신뢰구간이 넓습니다. 집계
                수치(클릭 의향률{' '}
                {formatPercent(result.aggregate.click_intent_rate)})보다 위
                반응 근거를 정성적으로 해석하세요.
              </p>
            )}
          </div>
        </div>
      )}

      {/* 기존 결과 뷰 재사용 — KPI·광고 해석·루브릭·토론·리포트 */}
      <SimulationResultView
        result={result}
        adTitle={adTitle}
        adDescription={adDescription}
        initialReportView={initialReportView}
        onReset={onReset}
        headerAction={headerAction}
      />
    </div>
  );
}
