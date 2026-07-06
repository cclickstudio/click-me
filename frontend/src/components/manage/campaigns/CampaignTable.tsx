// 캠페인 목록 — 테이블 뷰 (행 클릭 = 선택, 그 아래로 상세 펼침) + 헤더 클릭 정렬 + 간단/전체 지표 토글
import { Fragment, memo, useMemo, useState } from 'react';
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
import { budgetLabel, fmtCvr, fmtRoas, metricsBlocked, pacingMeaningful } from './types';
import { StateBadge } from './StateBadge';
import { CampaignDetail } from './CampaignDetail';
import { KpiInput } from './KpiInput';
import { Blocked } from './MetricGuard';
import { OriginTag } from '../ValueOrigin';

// 정렬 가능한 실측 숫자 컬럼 — CVR·ROAS는 수동 추정이 섞여 정렬 대상에서 제외.
type SortKey =
  | 'daily_budget_krw'
  | 'impressions'
  | 'clicks'
  | 'spend_krw'
  | 'ctr'
  | 'cpc_krw'
  | 'cpm_krw'
  | 'pacing_pct';

type ColumnMode = 'core' | 'all'; // core=핵심 7컬럼(스캔용) / all=전체 12컬럼

// memo — 프롭(campaigns·selected·manualKpi·안정 핸들러)이 그대로면 스킵.
// 상위에서 전환가치·ROAS 타이핑 중 20행 표가 매 키 입력마다 재조정되던 것을 막는다.
export const CampaignTable = memo(function CampaignTable({
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
  detail?: Detail | null;
  platforms?: PlatformMetrics[];
  demographics?: DemographicMetrics[];
  creatives?: CreativePreview[];
  account?: AccountWallet | null;
  manualKpi?: ManualKpiMap;
  onEditKpi?: (id: string, field: 'cvr' | 'roas', raw: string) => void;
  onChanged?: () => void;
  source?: CampaignSource;
}) {
  const [mode, setMode] = useState<ColumnMode>('core');
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortDesc, setSortDesc] = useState(true);

  // 같은 헤더 재클릭 = 방향 토글, 세 번째 클릭 = 정렬 해제(서버 최근순 복귀).
  const toggleSort = (key: SortKey) => {
    if (sortKey !== key) {
      setSortKey(key);
      setSortDesc(true);
    } else if (sortDesc) {
      setSortDesc(false);
    } else {
      setSortKey(null);
    }
  };

  const rows = useMemo(() => {
    if (!sortKey) return campaigns;
    return [...campaigns].sort((a, b) => {
      // 권한 없음 행은 값이 없으므로 항상 아래로.
      const av = metricsBlocked(a) ? -Infinity : (a[sortKey] ?? -Infinity);
      const bv = metricsBlocked(b) ? -Infinity : (b[sortKey] ?? -Infinity);
      return sortDesc ? bv - av : av - bv;
    });
  }, [campaigns, sortKey, sortDesc]);

  const all = mode === 'all';
  // 상세 펼침 colSpan — 표시 중인 컬럼 수와 일치시킨다.
  const colCount = all ? 13 : 8;

  const arrow = (key: SortKey) =>
    sortKey === key ? (
      <span className="ml-0.5 text-[#3182F6]">{sortDesc ? '▼' : '▲'}</span>
    ) : null;

  const thSort = (key: SortKey, label: string, sub?: string, title?: string, cls = '') => (
    <th
      className={`text-right font-semibold px-3 py-2.5 cursor-pointer select-none hover:text-[#3182F6] ${cls}`}
      title={title ?? '클릭하면 정렬'}
      onClick={() => toggleSort(key)}
    >
      {label}
      {arrow(key)}
      {sub && (
        <span className="block font-normal text-[11px] text-[#8B95A1] leading-tight">{sub}</span>
      )}
    </th>
  );

  return (
    <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] overflow-hidden">
      {/* 툴바 — 컬럼 밀도 토글(핵심만 훑기 vs 전체 지표) */}
      <div className="flex items-center justify-end gap-2 px-3 py-2 bg-[#F9FAFB] dark:bg-[#1A202C] border-b border-[#F2F4F6] dark:border-[#2D3748]">
        <span className="text-[11px] text-[#8B95A1]">
          {sortKey ? '정렬 적용 중 — 헤더 재클릭으로 해제' : '헤더 클릭으로 정렬'}
        </span>
        <div className="flex rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] overflow-hidden text-[11px]">
          {(
            [
              ['core', '핵심 지표'],
              ['all', '전체 지표'],
            ] as [ColumnMode, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setMode(key)}
              className={`px-2.5 py-1 ${
                mode === key
                  ? 'bg-[#3182F6] text-white'
                  : 'text-[#8B95A1] hover:bg-[#F2F4F6] dark:hover:bg-[#2D3748]'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <table className="w-full text-sm [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
        <thead>
          <tr className="bg-[#F9FAFB] dark:bg-[#1A202C] text-[#4E5968] dark:text-[#9CA3AF] text-xs">
            <th className="text-left font-semibold px-4 py-2.5 w-full">캠페인</th>
            <th className="text-left font-semibold px-3 py-2.5">상태</th>
            {all && (
              <th
                className="text-right font-semibold px-3 py-2.5 cursor-pointer select-none hover:text-[#3182F6]"
                title="하루 최대 한도 (총액 아님) · 클릭하면 정렬"
                onClick={() => toggleSort('daily_budget_krw')}
              >
                일예산{arrow('daily_budget_krw')}
                <OriginTag origin="setting" />
              </th>
            )}
            {all && thSort('impressions', '노출')}
            {all && thSort('clicks', '클릭', undefined, undefined, 'hidden sm:table-cell')}
            {thSort('spend_krw', '지출')}
            {thSort('ctr', 'CTR', '클릭률', undefined, all ? 'hidden md:table-cell' : '')}
            {all && thSort('cpc_krw', 'CPC', '클릭당비용', undefined, 'hidden md:table-cell')}
            {all &&
              thSort(
                'cpm_krw',
                'CPM',
                '노출당비용',
                '노출 1,000회당 평균 비용 = 지출 ÷ 노출 × 1,000 (합산되는 금액 아님) · 클릭하면 정렬',
                'hidden lg:table-cell',
              )}
            <th
              className={`text-right font-semibold px-3 py-2.5 ${all ? 'hidden lg:table-cell' : ''}`}
              title="전환율 = 전환수 ÷ 링크 클릭수 (광고가 클릭을 전환으로 얼마나 잘 바꿨나). CTR의 전체 클릭과 분모가 달라요. 전환 추적 전이면 셀에 직접 입력(추정)"
            >
              CVR
              <span className="block font-normal text-[11px] text-[#8B95A1] leading-tight">전환율</span>
            </th>
            <th
              className={`text-right font-semibold px-3 py-2.5 ${all ? 'hidden lg:table-cell' : ''}`}
              title="투자수익률 = (전환가치 × 전환수) ÷ 지출. 전환가치를 모르면 셀에 직접 입력(추정)"
            >
              ROAS
              <span className="block font-normal text-[11px] text-[#8B95A1] leading-tight">투자수익률</span>
            </th>
            <th
              className="text-right font-semibold px-4 py-2.5 cursor-pointer select-none hover:text-[#3182F6]"
              title="당일 일예산(하루 상한) 대비 지출(=지출÷일예산). 종료 캠페인은 의미 없어 '종료'로 표시 · 클릭하면 정렬"
              onClick={() => toggleSort('pacing_pct')}
            >
              소진율{arrow('pacing_pct')}
              <OriginTag origin="computed" />
            </th>
            <th className="px-2 py-2.5 w-8" aria-label="상세 토글"></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
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
                  {metricsBlocked(c) && (
                    <span
                      title="권한 없음 — Meta에서 이 캠페인 지표를 불러올 권한이 없어요."
                      className="rounded-md bg-[#F2F4F6] px-1.5 py-0.5 text-[10px] font-semibold text-[#8B95A1] dark:bg-[#2D3748] dark:text-[#9CA3AF]"
                    >
                      권한 없음
                    </span>
                  )}
                </span>
              </td>
              {all && (
                <td className="px-3 py-3 text-right tabular-nums text-[#191F28] dark:text-[#F2F4F6]">
                  {budgetLabel(c)}
                </td>
              )}
              {all && (
                <td className="px-3 py-3 text-right tabular-nums text-[#191F28] dark:text-[#F2F4F6]">
                  {metricsBlocked(c) ? <Blocked label="—" /> : c.impressions.toLocaleString()}
                </td>
              )}
              {all && (
                <td className="px-3 py-3 text-right tabular-nums text-[#191F28] dark:text-[#F2F4F6] hidden sm:table-cell">
                  {metricsBlocked(c) ? <Blocked label="—" /> : c.clicks.toLocaleString()}
                </td>
              )}
              <td className="px-3 py-3 text-right tabular-nums text-[#191F28] dark:text-[#F2F4F6]">
                {metricsBlocked(c) ? <Blocked label="—" /> : `₩${c.spend_krw.toLocaleString()}`}
              </td>
              <td
                className={`px-3 py-3 text-right tabular-nums text-[#191F28] dark:text-[#F2F4F6] ${all ? 'hidden md:table-cell' : ''}`}
              >
                {metricsBlocked(c) ? <Blocked label="—" /> : `${(c.ctr * 100).toFixed(1)}%`}
              </td>
              {all && (
                <td className="px-3 py-3 text-right tabular-nums text-[#191F28] dark:text-[#F2F4F6] hidden md:table-cell">
                  {metricsBlocked(c) ? <Blocked label="—" /> : `₩${c.cpc_krw.toLocaleString()}`}
                </td>
              )}
              {all && (
                <td className="px-3 py-3 text-right tabular-nums text-[#191F28] dark:text-[#F2F4F6] hidden lg:table-cell">
                  {metricsBlocked(c) ? <Blocked label="—" /> : `₩${c.cpm_krw.toLocaleString()}`}
                </td>
              )}
              <td
                className={`px-3 py-3 text-right tabular-nums text-[#191F28] dark:text-[#F2F4F6] ${all ? 'hidden lg:table-cell' : ''}`}
              >
                {/* 권한 없음 > 실측 있으면 읽기전용 > 미설정이면 직접 입력(추정) */}
                {metricsBlocked(c) ? (
                  <Blocked label="—" />
                ) : c.conversions == null ? (
                  <KpiInput
                    manual={manualKpi?.[c.campaign_id]?.cvr}
                    unit="%"
                    onCommit={(raw) => onEditKpi?.(c.campaign_id, 'cvr', raw)}
                  />
                ) : (
                  fmtCvr(c.cvr, c.conversions)
                )}
              </td>
              <td className={`px-3 py-3 text-right tabular-nums ${all ? 'hidden lg:table-cell' : ''}`}>
                {metricsBlocked(c) ? (
                  <Blocked label="—" />
                ) : c.conversions == null ? (
                  <KpiInput
                    manual={manualKpi?.[c.campaign_id]?.roas}
                    unit="x"
                    onCommit={(raw) => onEditKpi?.(c.campaign_id, 'roas', raw)}
                  />
                ) : (
                  <span className="inline-flex items-center justify-end gap-1">
                    <span className="text-[#191F28] dark:text-[#F2F4F6]">
                      {fmtRoas(c.roas, c.conversions, c.roas_estimated)}
                    </span>
                    {c.target_missed && (
                      <span className="text-[10px] font-medium text-red-500">목표↓</span>
                    )}
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-right">
                {pacingMeaningful(c) ? (
                  <PacingCell pct={c.pacing_pct} />
                ) : (
                  <span className="text-xs text-[#8B95A1]">
                    {c.state === 'ended'
                      ? '종료'
                      : metricsBlocked(c)
                        ? '권한 없음'
                        : '—'}
                  </span>
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
                <td colSpan={colCount} className="p-0 border-t border-[#F2F4F6] dark:border-[#2D3748]">
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
                      onChanged={onChanged}
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
});

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
