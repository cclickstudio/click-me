// 캠페인 건강신호 리스트 — 심각도순 + 지출 추세 스파크라인·7일 델타·페이싱 추정·노출 피로.
import { memo, useMemo } from 'react';
import Link from 'next/link';
import type { CampaignSummary } from '@/components/manage/campaigns/types';
import { metricsBlocked, pacingMeaningful } from '@/components/manage/campaigns/types';
import { StateBadge } from '@/components/manage/campaigns/StateBadge';
import { campaignHealth, frequencyFatigue, LEVEL_STYLE, SEVERITY } from './health';
import { pacingProjection, PACING_LABEL } from './pacing';
import { Sparkline } from './Sparkline';
import { trendDelta } from '@/components/manage/trend';

function PacingBar({ pct, alert }: { pct: number; alert: boolean }) {
  const w = Math.min(pct, 100);
  return (
    <div className="h-1.5 w-full rounded-full bg-[#F2F4F6] dark:bg-[#2D3748] overflow-hidden">
      <div className={`h-full ${alert ? 'bg-amber-500' : 'bg-[#3182F6]'}`} style={{ width: `${w}%` }} />
    </div>
  );
}

function DeltaTag({ delta }: { delta: number | null }) {
  if (delta == null) return null;
  const pct = Math.round(delta * 100);
  if (pct === 0) return <span className="text-[10px] text-[#8B95A1]">7일 →0%</span>;
  const up = pct > 0;
  return (
    <span className={`text-[10px] ${up ? 'text-green-600 dark:text-green-400' : 'text-red-500 dark:text-red-400'}`}>
      7일 {up ? '▲' : '▼'}
      {Math.abs(pct)}%
    </span>
  );
}

// memo — 부모(모니터링 페이지)가 리포트 모달 토글 등 무관한 상태로 리렌더돼도, 프롭이 그대로면 스킵.
export const HealthList = memo(function HealthList({
  campaigns,
  spendSeries,
  now,
  compact = false,
}: {
  campaigns: CampaignSummary[];
  spendSeries: Record<string, number[]>; // campaign_id → 일별 지출
  now: Date;
  // 홈 반폭 타일처럼 좁은 컨테이너용 — 뷰포트 기준 고정폭 대신 축소폭을 써 지표칸 찌부러짐/겹침 방지.
  compact?: boolean;
}) {
  // 심각도 높은 순 → 동순위면 소진율 높은 순. 건강신호는 캠페인당 1회만 계산(정렬 비교자 중복 호출 제거).
  const rows = useMemo(() => {
    const withHealth = campaigns.map((c) => ({ c, h: campaignHealth(c) }));
    withHealth.sort((x, y) => {
      const d = SEVERITY[y.h.level] - SEVERITY[x.h.level];
      return d !== 0 ? d : y.c.pacing_pct - x.c.pacing_pct;
    });
    return withHealth;
  }, [campaigns]);

  return (
    <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] divide-y divide-[#E5E8EB] dark:divide-[#2D3748] overflow-hidden">
      {rows.map(({ c, h }) => {
        const s = LEVEL_STYLE[h.level];
        const fatigue = frequencyFatigue(c);
        const blocked = metricsBlocked(c);
        const showPacing = pacingMeaningful(c); // 종료·권한없음·총예산은 소진율 의미 없음
        const pacing = c.state === 'active' && showPacing ? pacingProjection(c.pacing_pct, now) : null;
        const series = spendSeries[c.campaign_id] ?? [];
        // 진행 중(active)일 때만 마지막 점=오늘(부분치)이라 제외(오전 허위 하락 방지).
        // 종료·일시정지·삭제는 마지막도 완료일이라 그대로 둬야 추세가 빈다고 오인되지 않는다.
        const isDelivering = c.state === 'active' || c.state === 'active_pending_review';
        const trend = isDelivering && series.length >= 2 ? series.slice(0, -1) : series;
        const delta = trendDelta(trend);
        return (
          <Link
            key={c.campaign_id}
            href={`/manage/campaigns?open=${c.campaign_id}`}
            className="flex items-center gap-4 px-4 py-3.5 hover:bg-[#F9FAFB] dark:hover:bg-[#1A202C] transition-colors"
          >
            <span className={`shrink-0 w-2 h-2 rounded-full ${s.dot}`} />
            {/* 이름 칸 — 좁은 컨테이너(홈 반폭 타일)에선 줄여 우측 지표 줄바꿈 깨짐을 막는다 */}
            <div className={`shrink-0 ${compact ? 'w-24' : 'w-24 lg:w-40'}`}>
              <p className="text-sm font-medium text-[#191F28] dark:text-[#F2F4F6] truncate">{c.name}</p>
              <div className="mt-1">
                <StateBadge state={c.state} />
              </div>
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-center justify-between gap-x-3 text-[11px] text-[#8B95A1] mb-1">
                <span className="whitespace-nowrap">
                  소진율 {showPacing ? `${c.pacing_pct.toFixed(0)}%` : blocked ? '권한 없음' : '—'}
                </span>
                <span className="tabular-nums whitespace-nowrap">
                  {blocked
                    ? '권한 없음'
                    : `노출 ${c.impressions.toLocaleString()} · ₩${c.spend_krw.toLocaleString()}`}
                </span>
              </div>
              <PacingBar pct={showPacing ? c.pacing_pct : 0} alert={showPacing && c.pacing_pct >= 90} />
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                {pacing && pacing.status !== 'unknown' && (
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                      pacing.status === 'overpacing' || pacing.status === 'exhausted'
                        ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
                        : pacing.status === 'underpacing'
                          ? 'bg-[#EBF3FF] text-[#3182F6] dark:bg-[#1E3A5F] dark:text-[#73A9FF]'
                          : 'bg-[#F2F4F6] text-[#8B95A1] dark:bg-[#2D3748] dark:text-[#9CA3AF]'
                    }`}
                    title={`이 속도면 종일 ${pacing.projectedEodPct}% 소진 추정`}
                  >
                    {PACING_LABEL[pacing.status]}
                    {pacing.exhaustHour != null && ` ~${pacing.exhaustHour}시`}
                  </span>
                )}
                {fatigue && (
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                      fatigue.level === 'warn'
                        ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
                        : 'bg-[#F2F4F6] text-[#8B95A1] dark:bg-[#2D3748] dark:text-[#9CA3AF]'
                    }`}
                    title={fatigue.hint}
                  >
                    {fatigue.label}
                  </span>
                )}
              </div>
            </div>
            {/* 스파크라인 — compact는 폭·overflow를 좁혀 옆 칸으로 선이 새는 것을 막는다 */}
            <div
              className={`shrink-0 flex flex-col items-end gap-0.5 overflow-hidden ${
                compact ? 'w-16' : 'w-28'
              }`}
            >
              <Sparkline values={trend} width={compact ? 60 : 96} />
              <DeltaTag delta={delta} />
            </div>
            {/* 상태 — compact는 힌트 문장을 접어 폭을 내용에 맞춰 지표칸에 자리를 돌려준다 */}
            <div className={`shrink-0 text-right ${compact ? '' : 'w-52'}`}>
              <span className={`inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold ${s.chip}`}>
                {h.label}
              </span>
              {!compact && <p className="mt-1 text-[11px] text-[#8B95A1] truncate">{h.hint}</p>}
            </div>
          </Link>
        );
      })}
    </div>
  );
});
