'use client';
// Persona Set 비교 결과 뷰 — 세그먼트별 4대 KPI를 나란히 비교(A-1 3-모드).
// 각 세그먼트의 SimRunResult에서 aggregate를 뽑아 표로 대조하고, DB 저장분은 상세 보기로 연결.

import { useEffect, useMemo } from 'react';
import Link from 'next/link';
import { KpiCard } from '@/components/ui/KpiCard';
import { formatPercent } from '@/lib/utils';
import { saveSimResult } from '@/lib/simResultStore';
import type { SegmentResult, SimComparisonResult } from '@/lib/types';

const cardCls =
  'bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 transition-colors';

const GENDER_LABEL: Record<string, string> = { M: '남성', F: '여성', '': '전체' };

// 세그먼트 타깃을 한 줄 라벨로 — "20~39세 · 여성" 등.
function targetLabel(t: SegmentResult['target_filter']): string {
  const age =
    t.age_min != null && t.age_max != null
      ? `${t.age_min}~${t.age_max}세`
      : '전 연령';
  const gender = GENDER_LABEL[t.gender ?? ''] ?? '전체';
  return `${age} · ${gender}`;
}

// 비교 지표 정의 — value는 세그먼트 aggregate에서 뽑고, higherIsBetter로 우세 세그먼트 강조.
type Metric = {
  key: string;
  label: string;
  higherIsBetter: boolean;
  value: (s: SegmentResult) => number | null;
  fmt: (v: number) => string;
};

const METRICS: Metric[] = [
  {
    key: 'click',
    label: '클릭 의향률',
    higherIsBetter: true,
    value: s => s.result.aggregate?.click_intent_rate ?? null,
    fmt: formatPercent,
  },
  {
    key: 'purchase',
    label: '구매의도 (1~5)',
    higherIsBetter: true,
    value: s => s.result.aggregate?.purchase_intent ?? null,
    fmt: v => v.toFixed(2),
  },
  {
    key: 'trust',
    label: '신뢰도 (1~5)',
    higherIsBetter: true,
    value: s => s.result.aggregate?.trust_avg ?? null,
    fmt: v => v.toFixed(2),
  },
  {
    key: 'rejection',
    label: '거부율',
    higherIsBetter: false,
    value: s => s.result.aggregate?.rejection_rate ?? null,
    fmt: formatPercent,
  },
];

interface Props {
  comparison: SimComparisonResult;
  adTitle?: string;
  adDescription?: string;
  headerAction?: React.ReactNode;
}

export function SegmentComparisonView({
  comparison,
  adTitle,
  adDescription,
  headerAction,
}: Props) {
  const segments = useMemo(
    () => comparison.segments ?? [],
    [comparison.segments]
  );

  // 각 세그먼트의 전체 결과를 store에 넣어 두면 '상세 보기'가 콜드 없이 열린다(DB 저장분).
  useEffect(() => {
    for (const s of segments) {
      const simId = s.result.simulation_id;
      if (simId) {
        saveSimResult(simId, {
          result: s.result,
          adTitle,
          adDescription,
        });
      }
    }
  }, [segments, adTitle, adDescription]);

  // 지표별 우세 세그먼트 인덱스 — 값이 있는 세그먼트 중 최댓값/최솟값.
  const bestIdx = (m: Metric): number | null => {
    let idx: number | null = null;
    let best = m.higherIsBetter ? -Infinity : Infinity;
    segments.forEach((s, i) => {
      const v = m.value(s);
      if (v == null) return;
      if (m.higherIsBetter ? v > best : v < best) {
        best = v;
        idx = i;
      }
    });
    return idx;
  };

  return (
    <div className='px-8 py-8 max-w-7xl mx-auto space-y-6'>
      <div className='flex items-center justify-between'>
        <div>
          <h1 className='text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]'>
            세그먼트 비교 결과
          </h1>
          <p className='text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1'>
            run_id {comparison.run_id.slice(0, 8)} · 세그먼트 {segments.length}개
            {adTitle ? ` · ${adTitle}` : ''}
          </p>
        </div>
        {headerAction}
      </div>

      {/* 세그먼트별 요약 카드 — 라벨·타깃·표본수 */}
      <div className='grid grid-cols-2 md:grid-cols-4 gap-4'>
        {segments.map(s => {
          const n = s.result.aggregate?.effective_n ?? s.sample_size;
          return (
            <KpiCard
              key={s.label}
              label={targetLabel(s.target_filter)}
              value={s.label}
              sub={`표본 ${s.sample_size}명 · 유효 ${n}`}
            />
          );
        })}
      </div>

      {/* 4대 KPI 대조표 — 행: 지표, 열: 세그먼트. 우세 세그먼트 강조. */}
      <div className={cardCls}>
        <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-4'>
          4대 KPI 비교
        </h2>
        <div className='overflow-x-auto'>
          <table className='w-full text-sm border-collapse'>
            <thead>
              <tr>
                <th className='text-left font-medium text-[#8B95A1] dark:text-[#6B7280] py-2 pr-4 whitespace-nowrap'>
                  지표
                </th>
                {segments.map(s => (
                  <th
                    key={s.label}
                    className='text-right font-semibold text-[#191F28] dark:text-[#F2F4F6] py-2 px-3 whitespace-nowrap'>
                    {s.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {METRICS.map(m => {
                const winner = bestIdx(m);
                return (
                  <tr
                    key={m.key}
                    className='border-t border-[#E5E8EB] dark:border-[#2D3748]'>
                    <td className='text-[#4E5968] dark:text-[#9CA3AF] py-3 pr-4 whitespace-nowrap'>
                      {m.label}
                    </td>
                    {segments.map((s, i) => {
                      const v = m.value(s);
                      const isWinner = winner === i && segments.length > 1;
                      return (
                        <td
                          key={s.label}
                          className={`text-right tabular-nums py-3 px-3 ${
                            isWinner
                              ? 'font-bold text-[#1B64DA] dark:text-[#7AB0FF]'
                              : 'text-[#191F28] dark:text-[#F2F4F6]'
                          }`}>
                          {v == null ? '—' : m.fmt(v)}
                          {isWinner && (
                            <span className='ml-1 text-[10px] font-medium text-[#1B64DA] dark:text-[#7AB0FF]'>
                              ▲
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className='text-[11px] text-[#B0B8C1] dark:text-[#4B5563] mt-3'>
          ▲는 해당 지표에서 가장 우세한 세그먼트입니다(거부율은 낮을수록 우세).
          절대 스케일이 아닌 세그먼트 간 상대 비교로 참고하세요.
        </p>
      </div>

      {/* 세그먼트별 상세 진입 — DB 저장분만 개별 결과 페이지로 연결 */}
      <div className={cardCls}>
        <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-3'>
          세그먼트별 상세
        </h2>
        <div className='space-y-2'>
          {segments.map(s => {
            const simId = s.result.simulation_id;
            return (
              <div
                key={s.label}
                className='flex items-center justify-between gap-3 px-4 py-3 rounded-xl bg-[#F9FAFB] dark:bg-[#252D3D] border border-[#E5E8EB] dark:border-[#2D3748]'>
                <div className='min-w-0'>
                  <p className='text-sm font-medium text-[#191F28] dark:text-[#F2F4F6] truncate'>
                    {s.label}
                  </p>
                  <p className='text-[11px] text-[#8B95A1] dark:text-[#6B7280]'>
                    {targetLabel(s.target_filter)} · 반응{' '}
                    {s.result.reactions?.length ?? 0}건
                  </p>
                </div>
                {simId ? (
                  <Link
                    href={`/simulation/${simId}`}
                    className='shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium text-[#3182F6] border border-[#3182F6]/30 hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors'>
                    상세 보기
                  </Link>
                ) : (
                  <span className='shrink-0 text-[11px] text-[#B0B8C1] dark:text-[#4B5563]'>
                    저장 안 됨
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <p className='text-xs text-[#B0B8C1] dark:text-[#4B5563] border-t border-[#E5E8EB] dark:border-[#2D3748] pt-4'>
        본 결과는 AI 시뮬레이션 기반 예측이며 의사결정 보조 근거입니다. 클릭
        의향률은 실측 CTR이 아닙니다(calibration 전).
      </p>
    </div>
  );
}
