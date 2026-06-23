// 전사 집계 KPI — 활성 캠페인·총 노출·총 지출·가중 소진율·주의 신호. /campaigns 목록 합산.
import type { CampaignSummary } from '@/components/manage/campaigns/types';
import { OriginTag } from '@/components/manage/ValueOrigin';
import { campaignHealth, frequencyFatigue, needsAttention } from './health';

export function MonitorKpis({ campaigns }: { campaigns: CampaignSummary[] }) {
  const active = campaigns.filter((c) => c.state === 'active').length;
  const impressions = campaigns.reduce((a, c) => a + c.impressions, 0);
  const spend = campaigns.reduce((a, c) => a + c.spend_krw, 0); // 총 지출=조회기간 누적
  // 가중 소진율 — 일예산 합 대비 '오늘' 지출 합(예산가중). 일예산은 하루 단위라 분자도 오늘 지출.
  const spendToday = campaigns.reduce((a, c) => a + (c.spend_today_krw ?? 0), 0);
  const totalBudget = campaigns.reduce((a, c) => a + c.daily_budget_krw, 0);
  const pacing = totalBudget > 0 ? Math.round((spendToday / totalBudget) * 100) : 0;
  // 주의 = 시급 건강신호(게재중단·소진·목표미달) 또는 노출 피로 경고.
  const attention = campaigns.filter(
    (c) => needsAttention(campaignHealth(c).level) || frequencyFatigue(c)?.level === 'warn',
  ).length;

  const cards: {
    label: string;
    value: string;
    alert: boolean;
    origin?: 'setting' | 'computed';
  }[] = [
    { label: '활성 캠페인', value: String(active), alert: false },
    { label: '총 노출', value: impressions.toLocaleString(), alert: false },
    { label: '총 지출', value: `₩${spend.toLocaleString()}`, alert: false },
    { label: '평균 소진율', value: `${pacing}%`, alert: pacing >= 90, origin: 'computed' },
    { label: '주의 신호', value: String(attention), alert: attention > 0, origin: 'computed' },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
      {cards.map((c) => (
        <div
          key={c.label}
          className={`bg-white dark:bg-[#1C2333] border rounded-2xl p-5 ${
            c.alert ? 'border-[#E5484D]' : 'border-[#E5E8EB] dark:border-[#2D3748]'
          }`}
        >
          <p className="text-xs text-[#8B95A1] mb-1">
            {c.label}
            {c.origin && <OriginTag origin={c.origin} />}
          </p>
          <p
            className={`text-2xl font-bold tabular-nums ${
              c.alert ? 'text-[#E5484D]' : 'text-[#191F28] dark:text-[#F2F4F6]'
            }`}
          >
            {c.value}
          </p>
        </div>
      ))}
    </div>
  );
}
