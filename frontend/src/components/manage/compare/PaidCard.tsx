// 우측 — 광고 집행(Paid) 마케팅 수치. CTR·CPC는 광고에만 존재.
import type { PostInsights } from './types';
import { rate } from './types';

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-[#EEF2FF] dark:border-[#2D3748] last:border-0">
      <span className="text-sm text-[#8B95A1]">{label}</span>
      <span className="text-lg font-bold text-[#191F28] dark:text-[#F2F4F6] tabular-nums">{value}</span>
    </div>
  );
}

export function PaidCard({ insights }: { insights: PostInsights }) {
  const ctr = rate(insights.clicks, insights.impressions);
  const cpc = insights.clicks > 0 ? Math.round(insights.spend_krw / insights.clicks) : 0;
  return (
    <div className="flex-1 rounded-2xl border border-[#C7D2FE] dark:border-[#3730A3] overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 bg-[#EEF2FF] dark:bg-[#1E1B4B]">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#6366F1]" />
          <span className="font-bold text-[#191F28] dark:text-[#F2F4F6]">광고 집행 게시물 (Paid)</span>
        </div>
        <span className="text-xs font-semibold text-[#4F46E5] dark:text-[#A5B4FC]">
          지출 ₩{insights.spend_krw.toLocaleString()}
        </span>
      </div>
      <div className="px-5 py-3">
        <Row label="도달 (Reach)" value={insights.reach.toLocaleString()} />
        <Row label="노출 (Impressions)" value={insights.impressions.toLocaleString()} />
        <Row label="링크 클릭" value={insights.clicks.toLocaleString()} />
        <Row label="CTR" value={`${ctr.toFixed(1)}%`} />
        <Row label="CPC" value={`₩${cpc.toLocaleString()}`} />
        <p className="mt-3 text-[11px] text-[#B0B8C1]">출처 · ads_read (campaign insights)</p>
      </div>
    </div>
  );
}
