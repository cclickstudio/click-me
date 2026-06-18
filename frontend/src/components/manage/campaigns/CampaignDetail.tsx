// 캠페인 상세 — 누적 지출 vs 일예산 차트 + KPI 타일 + 플랫폼별(FB/IG) 분해
'use client';

import dynamic from 'next/dynamic';
import type { CampaignDetail as Detail, CampaignSource, PlatformMetrics } from './types';
import { fmtCvr, fmtRoas } from './types';
import { StateBadge } from './StateBadge';

// 차트는 펼칠 때만 로드(번들 분리, SSR 끄기 — Recharts는 DOM 측정형)
const DeliveryChart = dynamic(() => import('./DeliveryChart'), {
  ssr: false,
  loading: () => (
    <div className="h-[190px] animate-pulse rounded-xl bg-[#F2F4F6] dark:bg-[#2D3748]" />
  ),
});

const PlatformDonut = dynamic(() => import('./PlatformDonut'), {
  ssr: false,
  loading: () => <div className="h-32 animate-pulse rounded-xl bg-[#F2F4F6] dark:bg-[#2D3748]" />,
});

// 소진율 게이지 링(SVG) — 단일 비율 시각화
function PacingRing({ pct }: { pct: number }) {
  const r = 14;
  const c = 2 * Math.PI * r;
  const stroke = pct >= 95 ? '#E5484D' : pct >= 80 ? '#F59E0B' : '#3182F6';
  return (
    <svg width="38" height="38" viewBox="0 0 38 38" className="shrink-0">
      <circle cx="19" cy="19" r={r} fill="none" stroke="#EEF1F4" strokeWidth="4" />
      <circle
        cx="19"
        cy="19"
        r={r}
        fill="none"
        stroke={stroke}
        strokeWidth="4"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - Math.min(100, pct) / 100)}
        transform="rotate(-90 19 19)"
      />
    </svg>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] px-3 py-2.5">
      <p className="text-[11px] text-[#8B95A1]">{label}</p>
      <p className="text-base font-bold text-[#191F28] dark:text-[#F2F4F6] tabular-nums mt-0.5">{value}</p>
    </div>
  );
}

export function CampaignDetail({
  detail,
  source,
  platforms = [],
  blockReason,
}: {
  detail: Detail;
  source?: CampaignSource;
  platforms?: PlatformMetrics[];
  blockReason?: string | null;
}) {
  const s = detail.summary;
  const live = source === 'live';
  return (
    <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] px-5 py-4">
      <div className="flex items-center justify-between mb-2">
        <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">
          {detail.name} — 누적 지출 vs 일예산
        </p>
        <StateBadge state={detail.state} />
      </div>
      <DeliveryChart
        series={detail.series}
        dailyBudget={detail.daily_budget_krw}
        blockReason={blockReason}
      />
      <p className="mt-1 text-[11px] text-[#8B95A1]">
        {live ? '실 캠페인' : '데모'} · 시간 따라 누적 지출이 일예산에 다가가는 추이.
        {blockReason ? ' 빨간 점 = 게재 중단 시점.' : ''}
      </p>

      {/* 전달 → 효율 → 전환·예산 순, 4×3 정렬 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 mt-4">
        <Tile label="노출" value={s.impressions.toLocaleString()} />
        <Tile label="클릭" value={s.clicks.toLocaleString()} />
        <Tile label="도달" value={s.reach.toLocaleString()} />
        <Tile label="지출" value={`₩${s.spend_krw.toLocaleString()}`} />
        <Tile label="CTR(클릭률)" value={`${(s.ctr * 100).toFixed(1)}%`} />
        <Tile label="CPC(클릭당비용)" value={`₩${s.cpc_krw.toLocaleString()}`} />
        <Tile label="CPM(노출당비용)" value={`₩${s.cpm_krw.toLocaleString()}`} />
        <Tile label="빈도" value={s.frequency.toFixed(2)} />
        <Tile label="CVR(전환율)" value={fmtCvr(s.cvr)} />
        <Tile label="ROAS(투자수익률)" value={fmtRoas(s.roas)} />
        <Tile label="일예산" value={`₩${detail.daily_budget_krw.toLocaleString()}`} />
        <div className="flex items-center gap-2.5 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] px-3 py-2.5">
          <PacingRing pct={s.pacing_pct} />
          <div>
            <p className="text-[11px] text-[#8B95A1]">소진율</p>
            <p className="text-base font-bold text-[#191F28] dark:text-[#F2F4F6] tabular-nums mt-0.5">
              {s.pacing_pct.toFixed(0)}%
            </p>
          </div>
        </div>
      </div>

      {platforms.length > 0 && (
        <div className="mt-4">
          <p className="mb-2 text-center text-[12px] font-semibold text-[#4E5968] dark:text-[#9CA3AF]">
            플랫폼별 노출
          </p>
          <PlatformDonut rows={platforms} />
        </div>
      )}
    </div>
  );
}
