// 전사 집계 KPI — 활성 캠페인·총 노출·총 지출(스파크라인)·가중 소진율·주의 신호. /campaigns 목록 합산.
import type { CampaignSummary } from '@/components/manage/campaigns/types';
import { StatCard } from '@/components/manage/StatCard';
import { trendDelta } from '@/components/manage/trend';
import { campaignHealth, frequencyFatigue, needsAttention } from './health';

export function MonitorKpis({
  campaigns,
  accountSeries = [],
  runway,
}: {
  campaigns: CampaignSummary[];
  accountSeries?: number[]; // 전 캠페인 일자별 합산 지출(실측) — 총 지출 스파크라인·델타
  runway?: number | null; // 잔액 런웨이(일) — 최근 일평균 소진 가정 추정. null이면 카드 숨김
}) {
  const active = campaigns.filter((c) => c.state === 'active').length;
  const impressions = campaigns.reduce((a, c) => a + c.impressions, 0);
  const spend = campaigns.reduce((a, c) => a + c.spend_krw, 0); // 총 지출=조회기간 누적
  // 가중 소진율 — 일예산 합 대비 '오늘' 지출 합(예산가중). 일예산은 하루 단위라 분자도 오늘 지출.
  // 일예산형(daily)·권한있음 캠페인만 — 총예산·권한없음은 하루 소진율 의미가 없어 제외.
  const dailyOnly = campaigns.filter(
    (c) => (c.budget_type ?? 'daily') === 'daily' && c.metrics_status !== 'permission',
  );
  const spendToday = dailyOnly.reduce((a, c) => a + (c.spend_today_krw ?? 0), 0);
  const totalBudget = dailyOnly.reduce((a, c) => a + c.daily_budget_krw, 0);
  const pacing = totalBudget > 0 ? Math.round((spendToday / totalBudget) * 100) : 0;
  // 주의 = 시급 건강신호(게재중단·소진·목표미달) 또는 노출 피로 경고.
  const attention = campaigns.filter(
    (c) => needsAttention(campaignHealth(c).level) || frequencyFatigue(c)?.level === 'warn',
  ).length;

  // 총 지출 추세 — 마지막 점(오늘 부분치)은 활성 캠페인이 있으면 제외(오전 허위 하락 방지).
  const delivering = campaigns.some(
    (c) => c.state === 'active' || c.state === 'active_pending_review',
  );
  const spendTrend =
    delivering && accountSeries.length >= 3 ? accountSeries.slice(0, -1) : accountSeries;

  return (
    <div className={`grid grid-cols-2 gap-4 mb-6 ${runway != null ? 'md:grid-cols-6' : 'md:grid-cols-5'}`}>
      <StatCard label="활성 캠페인" value={String(active)} />
      <StatCard label="총 노출" value={impressions.toLocaleString()} />
      <StatCard
        label="총 지출"
        value={`₩${spend.toLocaleString()}`}
        series={spendTrend}
        delta={trendDelta(spendTrend)}
      />
      <StatCard
        label="평균 소진율"
        value={`${pacing}%`}
        alert={pacing >= 90}
        origin="computed"
      />
      <StatCard
        label="주의 신호"
        value={String(attention)}
        alert={attention > 0}
        origin="computed"
        sub={attention > 0 ? '아래 건강 신호에서 확인' : '모두 정상'}
      />
      {runway != null && (
        <StatCard
          label="잔액 런웨이"
          value={`약 ${runway.toFixed(1)}일`}
          alert={runway < 3}
          origin="computed"
          sub="최근 일평균 소진 가정 추정"
        />
      )}
    </div>
  );
}
