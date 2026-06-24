// 페이싱(소진 속도) 추정 — 현재까지 소진율 + 하루 경과분으로 종일 소진을 추정. 모두 '추정'.
import type { AccountWallet, CampaignSummary } from '@/components/manage/campaigns/types';

// 하루 경과 비율(0~1) — now 기준. 자정 직후 과민 추정을 막으려 하한을 둔다.
export function elapsedDayFraction(now: Date): number {
  const secs = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();
  return Math.min(Math.max(secs / 86400, 0.0001), 1);
}

export type PacingStatus = 'exhausted' | 'overpacing' | 'on_track' | 'underpacing' | 'unknown';

export type PacingProjection = {
  status: PacingStatus;
  projectedEodPct: number; // 이 속도면 종일 소진 추정(%)
  exhaustHour: number | null; // 일예산 소진 추정 시각(시) — 과속일 때만
};

// 현재 소진율 + 경과분 → 종일 소진 추정. 경과가 너무 작으면(이른 새벽) unknown으로 보류.
export function pacingProjection(pacingPct: number, now: Date): PacingProjection {
  if (pacingPct >= 100) {
    return { status: 'exhausted', projectedEodPct: 100, exhaustHour: now.getHours() };
  }
  const elapsed = elapsedDayFraction(now);
  if (elapsed < 0.08) {
    return { status: 'unknown', projectedEodPct: pacingPct, exhaustHour: null };
  }
  const projectedEodPct = Math.round(pacingPct / elapsed);
  let exhaustHour: number | null = null;
  if (projectedEodPct > 100) {
    // 누적 소진이 100%에 닿는 하루 경과 비율 → 시각.
    exhaustHour = Math.min(Math.round((elapsed * (100 / pacingPct)) * 24), 23);
  }
  let status: PacingStatus = 'on_track';
  if (projectedEodPct >= 120) status = 'overpacing';
  else if (projectedEodPct <= 70) status = 'underpacing';
  return { status, projectedEodPct, exhaustHour };
}

export const PACING_LABEL: Record<PacingStatus, string> = {
  exhausted: '일예산 소진',
  overpacing: '과속 추정',
  on_track: '적정',
  underpacing: '미소진 추정',
  unknown: '추정 보류',
};

// 최근 실 일평균 소진 — 일별 지출 시계열의 최근 7일(진행 중인 오늘은 제외) 평균.
// 시계열이 없으면 계획 일예산으로 폴백(Meta는 일예산에 맞춰 페이싱 → 합리적 추정).
function recentDailySpend(series: number[], dailyBudgetKrw: number): number {
  const v = series.filter((x) => Number.isFinite(x));
  if (v.length === 0) return dailyBudgetKrw;
  const completed = v.length >= 2 ? v.slice(0, -1) : v; // 마지막=오늘(진행 중) → 평균서 제외
  const window = completed.slice(-7);
  const avg = window.reduce((a, b) => a + b, 0) / window.length;
  return avg > 0 ? avg : dailyBudgetKrw;
}

// 계정 잔액 런웨이 — 최근 실 일평균 소진 기준 며칠치 잔액인지(추정). 데이터 부족 시 null.
export function runwayDays(
  account: AccountWallet | null,
  campaigns: CampaignSummary[],
  spendSeries: Record<string, number[]>,
): number | null {
  const balance = account?.available_balance_krw;
  if (balance == null || balance <= 0) return null;
  const dailySpend = campaigns
    .filter((c) => c.state === 'active')
    .reduce((a, c) => a + recentDailySpend(spendSeries[c.campaign_id] ?? [], c.daily_budget_krw), 0);
  if (dailySpend <= 0) return null;
  return balance / dailySpend;
}
