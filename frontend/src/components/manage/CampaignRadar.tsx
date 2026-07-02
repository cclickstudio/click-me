// 캠페인 KPI 프로필 레이더 — 지출 상위 캠페인(최대 3개)의 5축 상대 비교(각 축 최고=100).
// 실측 기반 정규화만 사용(합성 금지) — 절대값이 아닌 캠페인 간 상대 성격 비교용.
'use client';

import {
  Legend,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from 'recharts';
import type { CampaignSummary } from '@/components/manage/campaigns/types';
import { metricsBlocked } from '@/components/manage/campaigns/types';

const PALETTE = ['#3182F6', '#F04452', '#22C55E'];

// 축 정의 — raw 추출 후 축별 최대=100 정규화. CPC는 낮을수록 좋아 최저=100(효율).
const AXES: { label: string; raw: (c: CampaignSummary) => number; invert?: boolean }[] = [
  { label: 'CTR', raw: (c) => c.ctr },
  { label: 'CVR', raw: (c) => c.cvr ?? 0 },
  { label: '소진율', raw: (c) => c.pacing_pct },
  { label: '빈도', raw: (c) => c.frequency },
  { label: 'CPC 효율', raw: (c) => c.cpc_krw, invert: true },
];

export function CampaignRadar({ campaigns }: { campaigns: CampaignSummary[] }) {
  // 권한 있는 캠페인 중 지출 상위 3개 — 2개 미만이면 비교 의미가 없어 렌더하지 않는다.
  const rows = campaigns
    .filter((c) => !metricsBlocked(c))
    .sort((a, b) => b.spend_krw - a.spend_krw)
    .slice(0, 3);
  if (rows.length < 2) return null;

  const data = AXES.map((axis) => {
    const raws = rows.map((c) => axis.raw(c));
    const entry: Record<string, string | number> = { axis: axis.label };
    if (axis.invert) {
      // 낮을수록 좋음(CPC) — 유효 최솟값=100. 0(클릭 없음)은 효율 판단 불가라 0점.
      const valid = raws.filter((v) => v > 0);
      const min = valid.length ? Math.min(...valid) : 0;
      rows.forEach((c, i) => {
        entry[c.name] = raws[i] > 0 && min > 0 ? Math.round((min / raws[i]) * 100) : 0;
      });
    } else {
      const max = Math.max(...raws, 0);
      rows.forEach((c, i) => {
        entry[c.name] = max > 0 ? Math.round((raws[i] / max) * 100) : 0;
      });
    }
    return entry;
  });

  return (
    <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-5">
      <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">캠페인 성격 비교</p>
      <p className="text-[11px] text-[#8B95A1] mb-1">
        지출 상위 {rows.length}개 · 각 축은 캠페인 중 최고를 100으로 한 상대 비교(실측 기반) · CPC
        효율은 낮은 CPC가 100 · CVR 미설정은 0
      </p>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={data} outerRadius="72%">
            <PolarGrid stroke="#E5E8EB" />
            <PolarAngleAxis dataKey="axis" tick={{ fontSize: 11, fill: '#8B95A1' }} />
            {rows.map((c, i) => (
              <Radar
                key={c.campaign_id}
                name={c.name}
                dataKey={c.name}
                stroke={PALETTE[i]}
                fill={PALETTE[i]}
                fillOpacity={0.12}
                strokeWidth={2}
              />
            ))}
            <Legend wrapperStyle={{ fontSize: 12 }} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
