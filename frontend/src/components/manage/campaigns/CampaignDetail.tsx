// 캠페인 상세 — 일자별 지출 vs 일예산 차트 + KPI 타일 + 플랫폼별(FB/IG) 분해
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

// 일예산 대비 지출 게이지 링(SVG) — 누적지출÷일예산(중립색, 누적이라 초과 가능)
function PacingRing({ pct }: { pct: number }) {
  const r = 14;
  const c = 2 * Math.PI * r;
  const stroke = '#3182F6';
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
          {detail.name} — 일자별 지출 vs 일예산
        </p>
        <StateBadge state={detail.state} />
      </div>
      <DeliveryChart series={detail.series} dailyBudget={detail.daily_budget_krw} />
      <p className="mt-1 text-[11px] text-[#8B95A1]">
        {live ? '실 캠페인' : '데모'} · 전체 기간 일자별 지출(막대)과 일예산(점선).
        {blockReason ? ' 현재 게재 중단 — 선불 잔액 부족.' : ''}
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
        <Tile label="CVR(전환율)" value={fmtCvr(s.cvr, s.conversions)} />
        <Tile label="ROAS(투자수익률)" value={fmtRoas(s.roas, s.conversions)} />
        <Tile label="일예산" value={`₩${detail.daily_budget_krw.toLocaleString()}`} />
        <div className="flex items-center gap-2.5 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] px-3 py-2.5">
          <PacingRing pct={s.pacing_pct} />
          <div>
            <p className="text-[11px] text-[#8B95A1]">일예산 대비</p>
            <p className="text-base font-bold text-[#191F28] dark:text-[#F2F4F6] tabular-nums mt-0.5">
              {s.pacing_pct.toFixed(0)}%
            </p>
          </div>
        </div>
      </div>

      {detail.series.length > 0 && (
        <div className="mt-4">
          <p className="mb-2 text-[12px] font-semibold text-[#4E5968] dark:text-[#9CA3AF]">
            일자별 지표
          </p>
          <div className="overflow-x-auto rounded-xl border border-[#E5E8EB] dark:border-[#2D3748]">
            <table className="w-full text-[12px] [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
              <thead className="border-b border-[#E5E8EB] text-[#8B95A1] dark:border-[#2D3748]">
                <tr>
                  <th className="px-3 py-2 text-left font-semibold">날짜</th>
                  <th className="px-3 py-2 text-right font-semibold">노출</th>
                  <th className="px-3 py-2 text-right font-semibold">클릭</th>
                  <th className="px-3 py-2 text-right font-semibold">도달</th>
                  <th className="px-3 py-2 text-right font-semibold">지출</th>
                  <th className="px-3 py-2 text-right font-semibold">
                    CTR
                    <span className="block text-[10px] font-normal text-[#B0B8C1]">클릭률</span>
                  </th>
                  <th className="px-3 py-2 text-right font-semibold">
                    CPC
                    <span className="block text-[10px] font-normal text-[#B0B8C1]">클릭당비용</span>
                  </th>
                  <th className="px-3 py-2 text-right font-semibold">
                    CPM
                    <span className="block text-[10px] font-normal text-[#B0B8C1]">노출당비용</span>
                  </th>
                  <th className="px-3 py-2 text-right font-semibold">
                    CVR
                    <span className="block text-[10px] font-normal text-[#B0B8C1]">전환율</span>
                  </th>
                  <th className="px-3 py-2 text-right font-semibold">
                    ROAS
                    <span className="block text-[10px] font-normal text-[#B0B8C1]">투자수익률</span>
                  </th>
                </tr>
              </thead>
              <tbody className="text-[#191F28] dark:text-[#F2F4F6]">
                {detail.series.map((d) => (
                  <tr
                    key={d.label}
                    className="border-b border-[#F2F4F6] last:border-0 dark:border-[#252D3D]"
                  >
                    <td className="px-3 py-2 text-left text-[#4E5968] dark:text-[#9CA3AF]">
                      {d.label}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {d.impressions.toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {d.clicks.toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {d.reach.toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      ₩{d.spend_krw.toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {(d.ctr * 100).toFixed(1)}%
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      ₩{d.cpc_krw.toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      ₩{d.cpm_krw.toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {fmtCvr(d.cvr, d.conversions)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {fmtRoas(d.roas, d.conversions)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

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
