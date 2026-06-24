// 캠페인 상세 — 일자별 지출 vs 일예산 차트 + KPI 타일 + 분해 탭(인구통계/플랫폼) + 대표 크리에이티브
'use client';

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api, type LeadRecord, type DeliveryStatusResponse, type DeliveryCause } from '@/lib/api';
import { setPendingActivation } from '@/lib/pendingActivation';
import type {
  AccountWallet,
  CampaignDetail as Detail,
  CampaignSource,
  CreativePreview,
  DemographicMetrics,
  ManualKpi,
  PlatformMetrics,
} from './types';
import { budgetLabel, fmtCvr, fmtRoas, metricsBlocked, pacingMeaningful } from './types';
import { StateBadge } from './StateBadge';
import { OriginLegend, OriginTag } from '../ValueOrigin';

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

const DemographicBars = dynamic(() => import('./DemographicBars'), {
  ssr: false,
  loading: () => <div className="h-32 animate-pulse rounded-xl bg-[#F2F4F6] dark:bg-[#2D3748]" />,
});

const AdPreviewCards = dynamic(() => import('./AdPreviewCards'), {
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

function Tile({
  label,
  value,
  origin,
}: {
  label: string;
  value: string;
  origin?: 'setting' | 'computed';
}) {
  return (
    <div className="rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] px-3 py-2.5">
      <p className="text-[12px] text-[#8B95A1]">
        {label}
        {origin && <OriginTag origin={origin} />}
      </p>
      <p className="text-base font-bold text-[#191F28] dark:text-[#F2F4F6] tabular-nums mt-0.5">{value}</p>
    </div>
  );
}

export function CampaignDetail({
  detail,
  source,
  platforms = [],
  demographics = [],
  creatives = [],
  account,
  manualKpi,
  endedAt,
  blockReason,
  onDelete,
  onChanged,
}: {
  detail: Detail;
  source?: CampaignSource;
  platforms?: PlatformMetrics[];
  demographics?: DemographicMetrics[];
  creatives?: CreativePreview[];
  account?: AccountWallet | null;
  manualKpi?: ManualKpi;
  endedAt?: string | null;
  blockReason?: string | null;
  onDelete?: (id: string, name: string) => void;
  onChanged?: () => void; // 게재시작/일시중지/정산 후 대시보드 목록·잔액 갱신
}) {
  const s = detail.summary;
  const dBlocked = metricsBlocked(detail); // 권한 거부로 상세 지표 못 불러옴
  const showPacing = pacingMeaningful(detail); // 소진율 퍼센트 의미 있는 캠페인만
  const live = source === 'live';
  // 종료/중단 사유 — 데이터(상태·종료일·잔액)로 조립. 충전해도 재개 안 되는 경우 구분.
  const endReason = (() => {
    if (detail.state !== 'ended') return null;
    const parts: string[] = [];
    if (endedAt) {
      const d = new Date(endedAt);
      if (!Number.isNaN(d.getTime())) parts.push(`게재 기간 종료(${d.getMonth() + 1}/${d.getDate()})`);
    }
    if ((account?.available_balance_krw ?? null) === 0 && (account?.amount_spent_krw ?? 0) > 0) {
      parts.push('선불 잔액 소진(₩0)');
    }
    return parts.length ? parts.join(' · ') : null;
  })();
  // 분해 탭 — 데이터 있는 것만 노출(둘 다 없으면 섹션 자체 숨김)
  const breakdownTabs = [
    { key: 'demographics' as const, label: '인구통계학적 특성', has: demographics.length > 0 },
    { key: 'platforms' as const, label: '플랫폼', has: platforms.length > 0 },
  ].filter((t) => t.has);
  const [activeTab, setActiveTab] = useState<'demographics' | 'platforms'>(
    breakdownTabs[0]?.key ?? 'demographics',
  );
  const tab = breakdownTabs.some((t) => t.key === activeTab) ? activeTab : breakdownTabs[0]?.key;

  // 받은 리드(잠재고객) — 펼칠 때 Meta leadgen에서 조회. 권한 없으면 note로 안내.
  const [leads, setLeads] = useState<LeadRecord[] | null>(null);
  const [leadsNote, setLeadsNote] = useState<string | null>(null);
  const [leadsBusy, setLeadsBusy] = useState(false);
  const loadLeads = async () => {
    setLeadsBusy(true);
    setLeadsNote(null);
    try {
      const r = await api.management.leads(detail.campaign_id);
      setLeads(r.leads);
      if (r.note) setLeadsNote(r.note);
    } catch (e) {
      setLeads([]);
      setLeadsNote(e instanceof Error ? e.message : '리드 조회 실패');
    } finally {
      setLeadsBusy(false);
    }
  };
  // 리드 명단의 컬럼(필드명) — 첫 레코드 기준
  const leadCols = leads && leads.length ? Object.keys(leads[0].fields) : [];

  // 게재 상태(원인·상한) + 관리 액션 — live 캠페인만
  const [dstatus, setDstatus] = useState<DeliveryStatusResponse | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  // 게재 실패 원인 + 배정액 — 예산 한도(크레딧)/실광고비(Meta) 충전 버튼 분기용.
  const [actionCauses, setActionCauses] = useState<DeliveryCause[]>([]);
  const [lastCommit, setLastCommit] = useState(0);

  const refreshStatus = () =>
    api.management.deliveryStatus(detail.campaign_id).then(setDstatus).catch(() => {});

  // 상세 펼침 시: 게재 상태 조회 + 소진→크레딧 정산(sync, 실패 무시) 1회.
  useEffect(() => {
    if (!live) return;
    refreshStatus();
    api.management
      .syncCampaign(detail.campaign_id)
      .then(() => onChanged?.())
      .catch(() => {}); // 마이그레이션 전/권한 등은 조용히 무시
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail.campaign_id, live]);

  const canPause = detail.state === 'active' || detail.state === 'active_pending_review';
  const canActivate = detail.state === 'paused' || detail.state === 'draft';

  const onActivate = async () => {
    const entered = window.prompt(
      '이 캠페인에 배정할 금액(원) — 이만큼만 집행되고 소진되면 자동 종료됩니다.',
      String(detail.daily_budget_krw || 0),
    );
    if (entered == null) return;
    const commit = Math.max(0, Math.floor(Number(entered)));
    if (!commit) return;
    setActionBusy(true);
    setActionMsg(null);
    setActionCauses([]);
    setLastCommit(commit);
    try {
      const r = await api.management.activate(detail.campaign_id, commit);
      if (!r.serving) {
        // 원인별 충전 분기 — 크레딧(예산 한도)=/payment, Meta 선불(실광고비)=Ads Manager.
        setActionMsg(r.causes[0]?.message ?? r.error_message ?? '게재 시작 실패');
        setActionCauses(r.causes);
      }
      await refreshStatus();
      onChanged?.();
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : '게재 시작 실패');
    } finally {
      setActionBusy(false);
    }
  };

  const onPause = async () => {
    if (!window.confirm('이 캠페인을 일시중지할까요? 게재·과금이 중단됩니다.')) return;
    setActionBusy(true);
    setActionMsg(null);
    try {
      const r = await api.management.pause(detail.campaign_id);
      if (!r.paused) setActionMsg(r.error_message ?? '일시중지 실패');
      await refreshStatus();
      onChanged?.();
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : '일시중지 실패');
    } finally {
      setActionBusy(false);
    }
  };

  return (
    <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] px-5 py-4">
      <div className="flex items-center justify-between mb-2">
        <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">
          {detail.name} — 일자별 지출 vs 일예산
        </p>
        <span className="inline-flex items-center gap-2">
          {live && canActivate && (
            <button
              onClick={onActivate}
              disabled={actionBusy}
              className="text-[11px] font-semibold text-white bg-[#191F28] hover:bg-black rounded-md px-2.5 py-1 disabled:opacity-50"
            >
              {actionBusy ? '처리 중…' : '게재 시작'}
            </button>
          )}
          {live && canPause && (
            <button
              onClick={onPause}
              disabled={actionBusy}
              className="text-[11px] font-medium text-[#4E5968] dark:text-[#9CA3AF] border border-[#E5E8EB] dark:border-[#2D3748] rounded-md px-2 py-1 disabled:opacity-50"
            >
              {actionBusy ? '처리 중…' : '일시중지'}
            </button>
          )}
          {onDelete && (
            <button
              onClick={() => onDelete(detail.campaign_id, detail.name)}
              className="text-[11px] font-medium text-red-500 hover:text-red-600 border border-red-200 dark:border-red-900/50 rounded-md px-2 py-1"
              title="Meta에서도 삭제됩니다"
            >
              캠페인 삭제
            </button>
          )}
          <StateBadge state={detail.state} />
        </span>
      </div>
      {/* 게재 불가 원인 + 충전 한도 대비 소진 진행률 (live) */}
      {actionMsg && (
        <p className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-[12px] text-red-600 dark:bg-red-900/20 dark:text-red-300">
          {actionMsg}
        </p>
      )}
      {/* 두 충전 구분 — 예산 한도(크레딧)=/payment, 실광고비(Meta 선불)=Ads Manager */}
      {actionCauses.some((c) => c.code === 'INSUFFICIENT_CREDIT') && (
        <Link
          href="/payment"
          onClick={() =>
            setPendingActivation({ campaignId: detail.campaign_id, commit: lastCommit })
          }
          className="mb-2 mr-2 inline-block rounded-lg bg-[#3182F6] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-[#1B6EEB]"
        >
          📊 예산 한도(크레딧) 충전하기
        </Link>
      )}
      {actionCauses.some((c) => c.code === 'INSUFFICIENT_META_BALANCE') && (
        <a
          href="https://business.facebook.com/billing_hub/accounts"
          target="_blank"
          rel="noreferrer"
          className="mb-2 inline-block rounded-lg bg-[#191F28] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-black"
        >
          💳 실광고비(Meta 선불) 충전 — Ads Manager
        </a>
      )}
      {dstatus && !dstatus.serving && dstatus.causes.length > 0 && (
        <div className="mb-2 rounded-lg bg-amber-50 px-3 py-2 dark:bg-amber-900/20">
          <p className="text-[12px] font-semibold text-amber-700 dark:text-amber-300">게재되지 않는 이유</p>
          <ul className="mt-1 space-y-0.5">
            {dstatus.causes.map((c) => (
              <li key={c.code} className="text-[12px] text-amber-700 dark:text-amber-300">
                • {c.message}
              </li>
            ))}
          </ul>
        </div>
      )}
      {dstatus?.spend_cap_krw ? (
        <div className="mb-2">
          <div className="flex items-center justify-between text-[11px] text-[#8B95A1]">
            <span>충전 한도 대비 소진</span>
            <span className="tabular-nums">
              ₩{s.spend_krw.toLocaleString()} / ₩{dstatus.spend_cap_krw.toLocaleString()} (
              {Math.min(100, Math.round((s.spend_krw / dstatus.spend_cap_krw) * 100))}%)
            </span>
          </div>
          <div className="mt-1 h-1.5 rounded-full bg-[#EEF1F4] dark:bg-[#2D3748]">
            <div
              className="h-1.5 rounded-full bg-[#3182F6]"
              style={{
                width: `${Math.min(100, (s.spend_krw / dstatus.spend_cap_krw) * 100)}%`,
              }}
            />
          </div>
        </div>
      ) : null}

      <DeliveryChart series={detail.series} dailyBudget={detail.daily_budget_krw} />
      <p className="mt-1 text-[12px] text-[#8B95A1]">
        {live ? '실 캠페인' : '데모'} · 전체 기간 일자별 지출(막대)과 일예산(점선).
        {blockReason ? ' 현재 게재 중단 — 선불 잔액 부족.' : ''}
      </p>
      {endReason && (
        <p className="mt-2 rounded-lg bg-[#F2F4F6] px-3 py-2 text-[12px] text-[#4E5968] dark:bg-[#2D3748] dark:text-[#C9CED6]">
          <span className="font-semibold">종료 사유</span> · {endReason}
          <span className="ml-1 text-[#8B95A1]">
            (일예산은 하루 상한이라 미사용분은 이월되지 않습니다)
          </span>
        </p>
      )}
      {detail.diagnosis && (
        <p className="mt-2 rounded-lg bg-[#FFF4E6] px-3 py-2 text-[12px] text-[#8A5A00] dark:bg-[#3A2E1A] dark:text-[#F2C77E]">
          <span className="font-semibold">목표 미달 진단</span> · {detail.diagnosis.hypothesis}
          <span className="ml-1 text-[#B0853A] dark:text-[#C9A86A]">
            (확신도 {Math.round(detail.diagnosis.confidence * 100)}% ·{' '}
            {detail.diagnosis.source === 'agent' ? 'AI 분석' : '규칙 진단'})
          </span>
        </p>
      )}

      {/* 전달 → 효율 → 전환·예산 순, 4×3 정렬 */}
      <OriginLegend className="mt-4" />
      {dBlocked && (
        <p className="mt-3 rounded-lg bg-[#F2F4F6] px-3 py-2 text-[12px] text-[#8B95A1] dark:bg-[#2D3748] dark:text-[#9CA3AF]">
          <span className="font-semibold">권한 없음</span> · Meta에서 이 캠페인의 지표를 불러올
          권한이 없어요. 토큰 권한(스코프)·광고계정 자산 권한을 확인해 주세요. (예산·상태는 표시됨)
        </p>
      )}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 mt-2">
        <Tile label="노출" value={dBlocked ? '—' : s.impressions.toLocaleString()} />
        <Tile label="클릭" value={dBlocked ? '—' : s.clicks.toLocaleString()} />
        <Tile label="도달" value={dBlocked ? '—' : s.reach.toLocaleString()} />
        <Tile label="지출" value={dBlocked ? '—' : `₩${s.spend_krw.toLocaleString()}`} />
        <Tile label="CTR(클릭률)" value={dBlocked ? '—' : `${(s.ctr * 100).toFixed(1)}%`} />
        <Tile label="CPC(클릭당비용)" value={dBlocked ? '—' : `₩${s.cpc_krw.toLocaleString()}`} />
        <Tile label="CPM(노출당비용)" value={dBlocked ? '—' : `₩${s.cpm_krw.toLocaleString()}`} />
        <Tile label="빈도" value={dBlocked ? '—' : s.frequency.toFixed(2)} />
        <Tile
          label="CVR(전환율)"
          value={
            dBlocked
              ? '—'
              : manualKpi?.cvr != null
                ? `${manualKpi.cvr}% (추정)`
                : fmtCvr(s.cvr, s.conversions)
          }
        />
        <Tile
          label="ROAS(투자수익률)"
          value={
            dBlocked
              ? '—'
              : manualKpi?.roas != null
                ? `${manualKpi.roas}x (추정)`
                : fmtRoas(s.roas, s.conversions, s.roas_estimated) +
                  (s.target_missed ? ' · 목표↓' : '')
          }
        />
        <Tile
          label={detail.budget_type === 'lifetime' ? '총예산' : '일예산(하루 상한)'}
          value={budgetLabel(detail)}
          origin="setting"
        />
        <div className="flex items-center gap-2.5 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] px-3 py-2.5">
          <PacingRing pct={showPacing ? s.pacing_pct : 0} />
          <div>
            <p className="text-[12px] text-[#8B95A1]">
              {showPacing ? '소진율' : '게재'}
              {showPacing && <OriginTag origin="computed" />}
            </p>
            <p className="text-base font-bold text-[#191F28] dark:text-[#F2F4F6] tabular-nums mt-0.5">
              {showPacing
                ? `${s.pacing_pct.toFixed(0)}%`
                : detail.state === 'ended'
                  ? '종료'
                  : dBlocked
                    ? '권한 없음'
                    : '—'}
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

      {breakdownTabs.length > 0 && (
        <div className="mt-4 flex flex-col gap-x-6 gap-y-3 lg:flex-row lg:items-stretch">
          {/* 왼쪽: 분해 탭 + 차트(카드 높이만큼 채움) */}
          <div className="flex w-full flex-col lg:flex-1">
            <div className="mb-3 flex h-[30px] shrink-0 items-center gap-1.5">
              {breakdownTabs.map((t) => {
                const on = t.key === tab;
                return (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => setActiveTab(t.key)}
                    className={`rounded-lg px-3 py-1.5 text-[12px] font-semibold transition-colors ${
                      on
                        ? 'bg-[#E8F3FF] text-[#3182F6] dark:bg-[#1E3A5F] dark:text-[#7BB4F5]'
                        : 'text-[#8B95A1] hover:bg-[#F2F4F6] dark:hover:bg-[#2D3748]'
                    }`}
                  >
                    {t.label}
                  </button>
                );
              })}
            </div>
            <div className="flex min-h-0 flex-1 items-center">
              {tab === 'demographics' ? (
                <DemographicBars rows={demographics} />
              ) : (
                <PlatformDonut rows={platforms} />
              )}
            </div>
          </div>
          {/* 오른쪽: 대표 광고 시안(헤더는 탭과 같은 라인, 높이는 차트와 동일) */}
          {creatives.length > 0 && (
            <div className="flex w-full flex-col lg:flex-1">
              <p className="mb-3 flex h-[30px] items-center text-[12px] font-semibold text-[#4E5968] dark:text-[#9CA3AF]">
                대표 광고 시안
              </p>
              <div className="min-h-0 flex-1">
                <AdPreviewCards items={creatives} />
              </div>
            </div>
          )}
        </div>
      )}

      {/* 받은 리드(잠재고객) — live 캠페인만. 데이터는 Meta에 저장되며 여기로 불러온다. */}
      {live && (
        <div className="mt-4 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] px-4 py-3">
          <div className="flex items-center justify-between">
            <p className="text-[12px] font-semibold text-[#4E5968] dark:text-[#9CA3AF]">
              받은 리드 (잠재고객)
            </p>
            <button
              type="button"
              onClick={loadLeads}
              disabled={leadsBusy}
              className="rounded-md border border-[#E5E8EB] dark:border-[#2D3748] px-2.5 py-1 text-[11px] font-medium text-[#4E5968] dark:text-[#9CA3AF] hover:bg-[#F2F4F6] dark:hover:bg-[#2D3748] disabled:opacity-40"
            >
              {leadsBusy ? '불러오는 중…' : leads === null ? '리드 불러오기' : '새로고침'}
            </button>
          </div>

          {leads !== null && leads.length > 0 && (
            <div className="mt-3 overflow-x-auto rounded-lg border border-[#E5E8EB] dark:border-[#2D3748]">
              <table className="w-full text-[12px] [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
                <thead className="border-b border-[#E5E8EB] text-[#8B95A1] dark:border-[#2D3748]">
                  <tr>
                    <th className="px-3 py-2 text-left font-semibold">제출 시각</th>
                    {leadCols.map((col) => (
                      <th key={col} className="px-3 py-2 text-left font-semibold">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="text-[#191F28] dark:text-[#F2F4F6]">
                  {leads.map((l, i) => (
                    <tr
                      key={`${l.created_time}-${i}`}
                      className="border-b border-[#F2F4F6] last:border-0 dark:border-[#252D3D]"
                    >
                      <td className="px-3 py-2 text-left text-[#4E5968] dark:text-[#9CA3AF]">
                        {l.created_time ? new Date(l.created_time).toLocaleString('ko-KR') : '-'}
                      </td>
                      {leadCols.map((col) => (
                        <td key={col} className="px-3 py-2 text-left">
                          {l.fields[col] ?? '-'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {leads !== null && leads.length === 0 && (
            <p className="mt-2 text-[12px] text-[#8B95A1]">
              {leadsNote ?? '아직 받은 리드가 없습니다.'}
            </p>
          )}
          {leads === null && leadsNote && (
            <p className="mt-2 text-[12px] text-[#8B95A1]">{leadsNote}</p>
          )}
        </div>
      )}
    </div>
  );
}
