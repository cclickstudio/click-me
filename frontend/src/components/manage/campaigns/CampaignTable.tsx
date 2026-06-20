// 캠페인 목록 — 테이블 뷰 (행 클릭 = 선택, 그 아래로 상세 펼침)
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
import { StateBadge } from './StateBadge';
import { CampaignDetail } from './CampaignDetail';
import { KpiInput } from './KpiInput';

export function CampaignTable({
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
  source,
}: {
  campaigns: CampaignSummary[];
  selected: string | null;
  onSelect: (id: string) => void;
  onPrefetch?: (id: string) => void;
  onDelete?: (id: string, name: string) => void;
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
    <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] overflow-hidden">
      <table className="w-full text-sm [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
        <thead>
          <tr className="bg-[#F9FAFB] dark:bg-[#1A202C] text-[#4E5968] dark:text-[#9CA3AF] text-xs">
            <th className="text-left font-semibold px-4 py-2.5 w-full">캠페인</th>
            <th className="text-left font-semibold px-3 py-2.5">상태</th>
            <th className="text-right font-semibold px-3 py-2.5" title="하루 최대 한도 (총액 아님)">일일예산</th>
            <th className="text-right font-semibold px-3 py-2.5">노출</th>
            <th className="text-right font-semibold px-3 py-2.5 hidden sm:table-cell">클릭</th>
            <th className="text-right font-semibold px-3 py-2.5">지출</th>
            <th className="text-right font-semibold px-3 py-2.5 hidden md:table-cell">CTR<span className="block font-normal text-[11px] text-[#8B95A1] leading-tight">클릭률</span></th>
            <th className="text-right font-semibold px-3 py-2.5 hidden md:table-cell">CPC<span className="block font-normal text-[11px] text-[#8B95A1] leading-tight">클릭당비용</span></th>
            <th className="text-right font-semibold px-3 py-2.5 hidden lg:table-cell">CPM<span className="block font-normal text-[11px] text-[#8B95A1] leading-tight">노출당비용</span></th>
            <th className="text-right font-semibold px-3 py-2.5 hidden lg:table-cell" title="전환율 = 전환수 ÷ 클릭수 (광고가 클릭을 전환으로 얼마나 잘 바꿨나). 전환 추적 전이면 셀에 직접 입력(추정)">CVR<span className="block font-normal text-[11px] text-[#8B95A1] leading-tight">전환율</span></th>
            <th className="text-right font-semibold px-3 py-2.5 hidden lg:table-cell" title="투자수익률 = (전환가치 × 전환수) ÷ 지출. 전환가치를 모르면 셀에 직접 입력(추정)">ROAS<span className="block font-normal text-[11px] text-[#8B95A1] leading-tight">투자수익률</span></th>
            <th className="text-right font-semibold px-4 py-2.5" title="당일 일일예산(하루 상한) 대비 지출. 종료 캠페인은 의미 없어 '종료'로 표시">일예산 대비</th>
            <th className="px-2 py-2.5 w-8" aria-label="상세 토글"></th>
          </tr>
        </thead>
        <tbody>
          {campaigns.map((c) => (
            <Fragment key={c.campaign_id}>
            <tr
              onMouseEnter={() => onPrefetch?.(c.campaign_id)}
              className={`border-t border-[#F2F4F6] dark:border-[#2D3748] ${
                selected === c.campaign_id
                  ? 'bg-[#EAF3FF] dark:bg-[#1E293B]'
                  : 'hover:bg-[#F9FAFB] dark:hover:bg-[#1A202C]'
              }`}
            >
              <td className="px-4 py-3 font-medium text-[#191F28] dark:text-[#F2F4F6]">{c.name}</td>
              <td className="px-3 py-3">
                <span className="inline-flex items-center gap-1.5">
                  <StateBadge state={c.state} />
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
                </span>
              </td>
              <td className="px-3 py-3 text-right tabular-nums text-[#191F28] dark:text-[#F2F4F6]">
                ₩{c.daily_budget_krw.toLocaleString()}
              </td>
              <td className="px-3 py-3 text-right tabular-nums text-[#191F28] dark:text-[#F2F4F6]">
                {c.impressions.toLocaleString()}
              </td>
              <td className="px-3 py-3 text-right tabular-nums text-[#191F28] dark:text-[#F2F4F6] hidden sm:table-cell">
                {c.clicks.toLocaleString()}
              </td>
              <td className="px-3 py-3 text-right tabular-nums text-[#191F28] dark:text-[#F2F4F6]">
                ₩{c.spend_krw.toLocaleString()}
              </td>
              <td className="px-3 py-3 text-right tabular-nums text-[#191F28] dark:text-[#F2F4F6] hidden md:table-cell">
                {(c.ctr * 100).toFixed(1)}%
              </td>
              <td className="px-3 py-3 text-right tabular-nums text-[#191F28] dark:text-[#F2F4F6] hidden md:table-cell">
                ₩{c.cpc_krw.toLocaleString()}
              </td>
              <td className="px-3 py-3 text-right tabular-nums text-[#191F28] dark:text-[#F2F4F6] hidden lg:table-cell">
                ₩{c.cpm_krw.toLocaleString()}
              </td>
              <td className="px-3 py-3 text-right hidden lg:table-cell">
                <KpiInput
                  manual={manualKpi?.[c.campaign_id]?.cvr}
                  measured={c.conversions == null ? null : (c.cvr ?? 0) * 100}
                  unit="%"
                  onCommit={(raw) => onEditKpi?.(c.campaign_id, 'cvr', raw)}
                />
              </td>
              <td className="px-3 py-3 text-right hidden lg:table-cell">
                <KpiInput
                  manual={manualKpi?.[c.campaign_id]?.roas}
                  measured={c.conversions == null ? null : (c.roas ?? 0)}
                  unit="x"
                  onCommit={(raw) => onEditKpi?.(c.campaign_id, 'roas', raw)}
                />
              </td>
              <td className="px-4 py-3 text-right">
                {c.state === 'ended' ? (
                  <span className="text-xs text-[#8B95A1]">종료</span>
                ) : (
                  <PacingCell pct={c.pacing_pct} />
                )}
              </td>
              <td className="px-2 py-3 text-center whitespace-nowrap">
                {onDelete && (
                  <button
                    onClick={() => onDelete(c.campaign_id, c.name)}
                    aria-label="캠페인 삭제"
                    title="삭제 (Meta에서도 삭제)"
                    className="text-[#B0B8C1] hover:text-red-500 p-1 align-middle"
                  >
                    <svg
                      width="15"
                      height="15"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                  </button>
                )}
                <button
                  onClick={() => onSelect(c.campaign_id)}
                  aria-label="상세 펼치기"
                  aria-expanded={selected === c.campaign_id}
                  className="text-[#8B95A1] hover:text-[#3182F6] p-1 align-middle"
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className={`transition-transform ${selected === c.campaign_id ? 'rotate-180' : ''}`}
                  >
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </button>
              </td>
            </tr>
            {selected === c.campaign_id && detail && (
              <tr>
                <td colSpan={13} className="p-0 border-t border-[#F2F4F6] dark:border-[#2D3748]">
                  <div className="px-4 py-4 bg-[#F9FAFB] dark:bg-[#161B26]">
                    <CampaignDetail
                      detail={detail}
                      source={source}
                      platforms={platforms}
                      demographics={demographics}
                      creatives={creatives}
                      account={account}
                      manualKpi={manualKpi?.[c.campaign_id]}
                      endedAt={c.ended_at}
                      blockReason={c.block_reason}
                      onDelete={onDelete}
                    />
                  </div>
                </td>
              </tr>
            )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PacingCell({ pct }: { pct: number }) {
  const color = 'bg-[#3182F6]'; // 누적지출/일예산 — 누적이라 초과 정상, 경보색 제거
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="w-16 h-1.5 rounded-full bg-[#F2F4F6] dark:bg-[#2D3748] overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
      <span className="tabular-nums text-xs text-[#191F28] dark:text-[#F2F4F6] w-10 text-right">
        {pct.toFixed(0)}%
      </span>
    </div>
  );
}
