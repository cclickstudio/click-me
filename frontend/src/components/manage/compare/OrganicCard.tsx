// 좌측 — 일반 게시물(오가닉) 마케팅 수치. CTR 없음 → 참여율로 표기.
import type { PostInsights } from './types';
import { rate } from './types';

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-[#F2F4F6] dark:border-[#2D3748] last:border-0">
      <span className="text-sm text-[#8B95A1]">{label}</span>
      <span className="text-lg font-bold text-[#191F28] dark:text-[#F2F4F6] tabular-nums">{value}</span>
    </div>
  );
}

export function OrganicCard({ insights }: { insights: PostInsights }) {
  const er = rate(insights.engagement, insights.impressions);
  return (
    <div className="flex-1 rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 bg-[#F9FAFB] dark:bg-[#1A202C]">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-sky-400" />
          <span className="font-bold text-[#191F28] dark:text-[#F2F4F6]">일반 게시물 (오가닉)</span>
        </div>
        <span className="text-xs text-[#8B95A1]">비용 ₩0</span>
      </div>
      <div className="px-5 py-3">
        <Row label="도달 (Reach)" value={insights.reach.toLocaleString()} />
        <Row label="노출 (Impressions)" value={insights.impressions.toLocaleString()} />
        <Row label="참여 (♥+댓글+저장)" value={insights.engagement.toLocaleString()} />
        <Row label="참여율" value={`${er.toFixed(1)}%`} />
        <p className="mt-3 text-[11px] text-[#B0B8C1]">출처 · instagram_manage_insights (media)</p>
      </div>
    </div>
  );
}
