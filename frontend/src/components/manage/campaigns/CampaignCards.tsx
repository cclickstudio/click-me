// 캠페인 목록 — 카드 그리드 뷰 (카드 클릭 = 선택, 그 아래로 상세 펼침)
import { Fragment } from 'react';
import type {
  AccountWallet,
  CampaignDetail as Detail,
  CampaignSource,
  CampaignSummary,
  CreativePreview,
  DemographicMetrics,
  ManualKpiMap,
  PlatformMetrics,
} from './types';
import { fmtCvr, fmtRoas } from './types';
import { StateBadge } from './StateBadge';
import { OriginTag } from '../ValueOrigin';
import { CampaignDetail } from './CampaignDetail';
import { KpiInput } from './KpiInput';

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[12px] text-[#8B95A1]">{label}</p>
      <p className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6] tabular-nums">{value}</p>
    </div>
  );
}

export function CampaignCards({
  campaigns,
  selected,
  onSelect,
  onPrefetch,
  onDelete,
  detail,
  platforms,
  demographics,
  creatives,
  account,
  manualKpi,
  onEditKpi,
  onChanged,
  source,
}: {
  campaigns: CampaignSummary[];
  selected: string | null;
  onSelect: (id: string) => void;
  onPrefetch?: (id: string) => void;
  onDelete?: (id: string, name: string) => void;
  onChanged?: () => void;
  detail?: Detail | null;
  platforms?: PlatformMetrics[];
  demographics?: DemographicMetrics[];
  creatives?: CreativePreview[];
  account?: AccountWallet | null;
  manualKpi?: ManualKpiMap;
  onEditKpi?: (id: string, field: 'cvr' | 'roas', raw: string) => void;
  source?: CampaignSource;
}) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {campaigns.map((c) => {
        const pColor = c.pacing_pct >= 95 ? 'bg-red-500' : c.pacing_pct >= 80 ? 'bg-amber-500' : 'bg-[#3182F6]';
        const manual = manualKpi?.[c.campaign_id];
        return (
          <Fragment key={c.campaign_id}>
          <button
            onClick={() => onSelect(c.campaign_id)}
            onMouseEnter={() => onPrefetch?.(c.campaign_id)}
            className={`text-left rounded-2xl border p-4 transition-colors ${
              selected === c.campaign_id
                ? 'border-[#3182F6] bg-[#EAF3FF] dark:bg-[#1E293B]'
                : 'border-[#E5E8EB] dark:border-[#2D3748] hover:border-[#3182F6]/50'
            }`}
          >
            <div className="flex items-center justify-between mb-3">
              <span className="font-bold text-[#191F28] dark:text-[#F2F4F6] truncate pr-2">{c.name}</span>
              <span className="inline-flex items-center gap-1.5 shrink-0">
                {c.delivery_blocked && (
                  <span className="rounded-md bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-700 dark:bg-red-900/30 dark:text-red-400">
                    게재 중단
                  </span>
                )}
                {c.target_missed && (
                  <span
                    title={`목표 ROAS ${c.target_roas?.toFixed(2)}x 대비 미달`}
                    className="rounded-md bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                  >
                    목표 미달
                  </span>
                )}
                <StateBadge state={c.state} />
              </span>
            </div>
            <div className="grid grid-cols-2 gap-y-2.5 gap-x-3">
              <Metric label="노출" value={c.impressions.toLocaleString()} />
              <Metric label="클릭" value={c.clicks.toLocaleString()} />
              <Metric label="지출" value={`₩${c.spend_krw.toLocaleString()}`} />
              <Metric label="CTR(클릭률)" value={`${(c.ctr * 100).toFixed(1)}%`} />
              <Metric label="CPC(클릭당비용)" value={`₩${c.cpc_krw.toLocaleString()}`} />
              <Metric label="CPM(노출당비용)" value={`₩${c.cpm_krw.toLocaleString()}`} />
              {/* 실측 있으면 읽기전용, 미설정이면 직접 입력(추정) */}
              {c.conversions == null ? (
                <div>
                  <p className="text-[12px] text-[#8B95A1]">CVR(전환율)</p>
                  <KpiInput
                    manual={manual?.cvr}
                    unit="%"
                    onCommit={(raw) => onEditKpi?.(c.campaign_id, 'cvr', raw)}
                  />
                </div>
              ) : (
                <Metric label="CVR(전환율)" value={fmtCvr(c.cvr, c.conversions)} />
              )}
              {c.conversions == null ? (
                <div>
                  <p className="text-[12px] text-[#8B95A1]">ROAS(투자수익률)</p>
                  <KpiInput
                    manual={manual?.roas}
                    unit="x"
                    onCommit={(raw) => onEditKpi?.(c.campaign_id, 'roas', raw)}
                  />
                </div>
              ) : (
                <Metric
                  label="ROAS(투자수익률)"
                  value={
                    fmtRoas(c.roas, c.conversions, c.roas_estimated) +
                    (c.target_missed ? ' · 목표↓' : '')
                  }
                />
              )}
            </div>
            <div className="mt-3">
              <div className="flex items-center justify-between text-[12px] text-[#8B95A1] mb-1">
                <span title="하루 상한(일예산) 대비 지출 — 총액 아님">
                  소진율(하루 상한)
                  <OriginTag origin="computed" />
                </span>
                {c.state === 'ended' ? (
                  <span className="tabular-nums">종료</span>
                ) : (
                  <span className="tabular-nums">
                    ₩{c.spend_krw.toLocaleString()} / {c.daily_budget_krw.toLocaleString()} (
                    {c.pacing_pct.toFixed(0)}%)
                  </span>
                )}
              </div>
              <div className="w-full h-1.5 rounded-full bg-[#F2F4F6] dark:bg-[#2D3748] overflow-hidden">
                <div
                  className={`h-full ${c.state === 'ended' ? 'bg-[#D1D6DB]' : pColor}`}
                  style={{ width: `${Math.min(100, c.pacing_pct)}%` }}
                />
              </div>
            </div>
          </button>
          {selected === c.campaign_id && detail && (
            <div className="col-span-full">
              <CampaignDetail
                detail={detail}
                source={source}
                platforms={platforms}
                demographics={demographics}
                creatives={creatives}
                account={account}
                manualKpi={manual}
                endedAt={c.ended_at}
                blockReason={c.block_reason}
                onDelete={onDelete}
                onChanged={onChanged}
              />
            </div>
          )}
          </Fragment>
        );
      })}
    </div>
  );
}
