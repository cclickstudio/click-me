// 캠페인 목록 — 테이블 뷰 (행 클릭 = 선택)
import type { CampaignSummary } from './types';
import { fmtCvr, fmtRoas } from './types';
import { StateBadge } from './StateBadge';

export function CampaignTable({
  campaigns,
  selected,
  onSelect,
}: {
  campaigns: CampaignSummary[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-[#F9FAFB] dark:bg-[#1A202C] text-[#8B95A1] text-xs">
            <th className="text-left font-semibold px-4 py-2.5">캠페인</th>
            <th className="text-left font-semibold px-3 py-2.5">상태</th>
            <th className="text-right font-semibold px-3 py-2.5">일예산</th>
            <th className="text-right font-semibold px-3 py-2.5">노출</th>
            <th className="text-right font-semibold px-3 py-2.5 hidden sm:table-cell">클릭</th>
            <th className="text-right font-semibold px-3 py-2.5">지출</th>
            <th className="text-right font-semibold px-3 py-2.5 hidden md:table-cell">CTR<span className="block font-normal text-[9px] text-[#B0B8C1] leading-tight">클릭률</span></th>
            <th className="text-right font-semibold px-3 py-2.5 hidden md:table-cell">CPC<span className="block font-normal text-[9px] text-[#B0B8C1] leading-tight">클릭당비용</span></th>
            <th className="text-right font-semibold px-3 py-2.5 hidden lg:table-cell">CPM<span className="block font-normal text-[9px] text-[#B0B8C1] leading-tight">노출당비용</span></th>
            <th className="text-right font-semibold px-3 py-2.5 hidden lg:table-cell">CVR<span className="block font-normal text-[9px] text-[#B0B8C1] leading-tight">전환율</span></th>
            <th className="text-right font-semibold px-3 py-2.5 hidden lg:table-cell">ROAS<span className="block font-normal text-[9px] text-[#B0B8C1] leading-tight">투자수익률</span></th>
            <th className="text-right font-semibold px-4 py-2.5">소진율</th>
          </tr>
        </thead>
        <tbody>
          {campaigns.map((c) => (
            <tr
              key={c.campaign_id}
              onClick={() => onSelect(c.campaign_id)}
              className={`cursor-pointer border-t border-[#F2F4F6] dark:border-[#2D3748] ${
                selected === c.campaign_id
                  ? 'bg-[#EAF3FF] dark:bg-[#1E293B]'
                  : 'hover:bg-[#F9FAFB] dark:hover:bg-[#1A202C]'
              }`}
            >
              <td className="px-4 py-3 font-medium text-[#191F28] dark:text-[#F2F4F6]">{c.name}</td>
              <td className="px-3 py-3"><StateBadge state={c.state} /></td>
              <td className="px-3 py-3 text-right tabular-nums text-[#4E5968] dark:text-[#C9CED6]">
                ₩{c.daily_budget_krw.toLocaleString()}
              </td>
              <td className="px-3 py-3 text-right tabular-nums text-[#191F28] dark:text-[#F2F4F6]">
                {c.impressions.toLocaleString()}
              </td>
              <td className="px-3 py-3 text-right tabular-nums text-[#191F28] dark:text-[#F2F4F6] hidden sm:table-cell">
                {c.clicks.toLocaleString()}
              </td>
              <td className="px-3 py-3 text-right tabular-nums text-[#4E5968] dark:text-[#C9CED6]">
                ₩{c.spend_krw.toLocaleString()}
              </td>
              <td className="px-3 py-3 text-right tabular-nums text-[#4E5968] dark:text-[#C9CED6] hidden md:table-cell">
                {(c.ctr * 100).toFixed(1)}%
              </td>
              <td className="px-3 py-3 text-right tabular-nums text-[#4E5968] dark:text-[#C9CED6] hidden md:table-cell">
                ₩{c.cpc_krw.toLocaleString()}
              </td>
              <td className="px-3 py-3 text-right tabular-nums text-[#4E5968] dark:text-[#C9CED6] hidden lg:table-cell">
                ₩{c.cpm_krw.toLocaleString()}
              </td>
              <td className="px-3 py-3 text-right tabular-nums text-[#4E5968] dark:text-[#C9CED6] hidden lg:table-cell">
                {fmtCvr(c.cvr)}
              </td>
              <td className="px-3 py-3 text-right tabular-nums text-[#4E5968] dark:text-[#C9CED6] hidden lg:table-cell">
                {fmtRoas(c.roas)}
              </td>
              <td className="px-4 py-3 text-right">
                <PacingCell pct={c.pacing_pct} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PacingCell({ pct }: { pct: number }) {
  const color = pct >= 95 ? 'bg-red-500' : pct >= 80 ? 'bg-amber-500' : 'bg-[#3182F6]';
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="w-16 h-1.5 rounded-full bg-[#F2F4F6] dark:bg-[#2D3748] overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
      <span className="tabular-nums text-xs text-[#4E5968] dark:text-[#C9CED6] w-10 text-right">
        {pct.toFixed(0)}%
      </span>
    </div>
  );
}
