// 캠페인 목록 — 카드 그리드 뷰 (카드 클릭 = 선택)
import type { CampaignSummary } from './types';
import { fmtCvr, fmtRoas } from './types';
import { StateBadge } from './StateBadge';

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] text-[#8B95A1]">{label}</p>
      <p className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6] tabular-nums">{value}</p>
    </div>
  );
}

export function CampaignCards({
  campaigns,
  selected,
  onSelect,
}: {
  campaigns: CampaignSummary[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {campaigns.map((c) => {
        const pColor = c.pacing_pct >= 95 ? 'bg-red-500' : c.pacing_pct >= 80 ? 'bg-amber-500' : 'bg-[#3182F6]';
        return (
          <button
            key={c.campaign_id}
            onClick={() => onSelect(c.campaign_id)}
            className={`text-left rounded-2xl border p-4 transition-colors ${
              selected === c.campaign_id
                ? 'border-[#3182F6] bg-[#EAF3FF] dark:bg-[#1E293B]'
                : 'border-[#E5E8EB] dark:border-[#2D3748] hover:border-[#3182F6]/50'
            }`}
          >
            <div className="flex items-center justify-between mb-3">
              <span className="font-bold text-[#191F28] dark:text-[#F2F4F6] truncate pr-2">{c.name}</span>
              <StateBadge state={c.state} />
            </div>
            <div className="grid grid-cols-2 gap-y-2.5 gap-x-3">
              <Metric label="노출" value={c.impressions.toLocaleString()} />
              <Metric label="클릭" value={c.clicks.toLocaleString()} />
              <Metric label="지출" value={`₩${c.spend_krw.toLocaleString()}`} />
              <Metric label="CTR" value={`${(c.ctr * 100).toFixed(1)}%`} />
              <Metric label="CPC" value={`₩${c.cpc_krw.toLocaleString()}`} />
              <Metric label="CPM" value={`₩${c.cpm_krw.toLocaleString()}`} />
              <Metric label="CVR" value={fmtCvr(c.cvr)} />
              <Metric label="ROAS" value={fmtRoas(c.roas)} />
            </div>
            <div className="mt-3">
              <div className="flex items-center justify-between text-[11px] text-[#8B95A1] mb-1">
                <span>예산 소진</span>
                <span className="tabular-nums">
                  ₩{c.spend_krw.toLocaleString()} / {c.daily_budget_krw.toLocaleString()} ({c.pacing_pct.toFixed(0)}%)
                </span>
              </div>
              <div className="w-full h-1.5 rounded-full bg-[#F2F4F6] dark:bg-[#2D3748] overflow-hidden">
                <div className={`h-full ${pColor}`} style={{ width: `${Math.min(100, c.pacing_pct)}%` }} />
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
