'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { api, type DatePreset } from '@/lib/api';
import { MonitorKpis } from '@/components/manage/monitoring/MonitorKpis';
import { HealthList } from '@/components/manage/monitoring/HealthList';
import { runwayDays } from '@/components/manage/monitoring/pacing';
import { OriginLegend, OriginTag } from '@/components/manage/ValueOrigin';
import type {
  AccountWallet,
  CampaignSource,
  CampaignSummary,
} from '@/components/manage/campaigns/types';

export default function Page() {
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [source, setSource] = useState<CampaignSource>('mock');
  const [account, setAccount] = useState<AccountWallet | null>(null);
  const [accountBlock, setAccountBlock] = useState<string | null>(null);
  const [accountUnavailable, setAccountUnavailable] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [permissionError, setPermissionError] = useState<string | null>(null);
  const [rateLimited, setRateLimited] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [spendSeries, setSpendSeries] = useState<Record<string, number[]>>({});
  const [now, setNow] = useState<Date>(() => new Date());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [datePreset, setDatePreset] = useState<DatePreset>('maximum'); // 조회 기간 토글

  // 캠페인별 일별 지출 시계열 — /campaigns/{id}.series에서 추출(스파크라인·델타용).
  // 호출이 N건이라 폴링(silent)에선 생략하고 최초·수동 새로고침에서만 갱신.
  const loadSeries = useCallback(async (list: CampaignSummary[]) => {
    const entries = await Promise.all(
      list.map(async (c) => {
        try {
          const d = await api.management.campaign(c.campaign_id);
          return [c.campaign_id, d.series.map((p) => p.spend_krw)] as const;
        } catch {
          return [c.campaign_id, [] as number[]] as const;
        }
      }),
    );
    setSpendSeries(Object.fromEntries(entries));
  }, []);

  // silent=true면 폴링 갱신(스피너 없이 값만 교체). withSeries=true면 시계열도 다시 가져온다.
  const load = useCallback(
    async (silent = false, withSeries = true) => {
      if (!silent) setBusy(true);
      setError(null);
      try {
        const r = await api.management.campaigns(undefined, undefined, datePreset);
        // Meta 요청 한도(일시) — 빈 목록으로 덮지 말고 기존 유지 + 배너만.
        if (r.rate_limited) {
          setRateLimited(r.rate_limited);
          return;
        }
        setRateLimited(null);
        setCampaigns(r.campaigns);
        setSource(r.source ?? 'mock');
        setAccount(r.account ?? null);
        setAccountBlock(r.account_block_reason ?? null);
        setAccountUnavailable(r.account_unavailable ?? null);
        setAuthError(r.auth_error ?? null);
        setPermissionError(r.permission_error ?? r.not_connected ?? null);
        setNow(new Date());
        setLastUpdated(new Date().toLocaleTimeString('ko-KR'));
        if (withSeries) await loadSeries(r.campaigns);
      } catch (e) {
        setError(e instanceof Error ? e.message : '불러오기 실패');
      } finally {
        if (!silent) setBusy(false);
      }
    },
    [loadSeries, datePreset],
  );

  useEffect(() => {
    load();
  }, [load]);

  // 실데이터일 때만 120초 폴링 (Meta 분 단위 갱신, rate limit 절감). 숨겨진 탭이면 건너뜀.
  useEffect(() => {
    if (source !== 'live') return;
    const id = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      load(true, false); // 폴링은 요약·신호만 갱신, 시계열(N콜)은 건너뜀
    }, 120000);
    return () => clearInterval(id);
  }, [source, load]);

  return (
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">모니터링</h1>
              {source === 'live' ? (
                <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                  실데이터
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-300">
                  데모
                </span>
              )}
            </div>
            <p className="text-sm text-[#8B95A1] mt-1">
              {source === 'live'
                ? '실 Meta 연동 · 전 캠페인 게재 건강 상태를 한눈에'
                : '전 캠페인 게재 건강 상태를 한눈에 (Mock 기반 데모)'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {source === 'live' && (
              <div className="flex rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] overflow-hidden text-[12px]">
                {(
                  [
                    ['maximum', '전체'],
                    ['last_30d', '최근 30일'],
                    ['this_month', '이번 달'],
                  ] as [DatePreset, string][]
                ).map(([key, label]) => (
                  <button
                    key={key}
                    onClick={() => setDatePreset(key)}
                    className={`px-2.5 py-1.5 ${
                      datePreset === key
                        ? 'bg-[#3182F6] text-white'
                        : 'text-[#8B95A1] hover:bg-[#F2F4F6] dark:hover:bg-[#2D3748]'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
            {source === 'live' && (
              <button
                onClick={() => load(true)}
                title="새로고침"
                className="flex items-center gap-1.5 text-[12px] text-[#8B95A1] hover:text-[#191F28] dark:hover:text-[#F2F4F6] px-2 py-1.5"
              >
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                {lastUpdated ? `갱신 ${lastUpdated}` : '실시간'} ↻
              </button>
            )}
            <Link
              href="/manage/anomaly"
              className="text-sm text-[#3182F6] font-medium px-3 py-1.5 rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F]"
            >
              이상 감지 시연 →
            </Link>
          </div>
        </div>

        {authError && (
          <div className="mb-4 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 dark:border-amber-900/50 dark:bg-amber-900/20">
            <p className="text-sm text-amber-800 dark:text-amber-300">
              <span className="font-semibold">⚠ Meta 연결 만료</span> · {authError} 실데이터를 불러올
              수 없어요. 관리자가 Meta 액세스 토큰을 갱신하면 다시 표시됩니다.
            </p>
          </div>
        )}

        {rateLimited && (
          <div className="mb-4 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 dark:border-amber-900/50 dark:bg-amber-900/20">
            <p className="text-sm text-amber-800 dark:text-amber-300">
              <span className="font-semibold">⏳ Meta 요청 한도(일시)</span> · {rateLimited} 아래
              지표는 마지막으로 불러온 값이에요.
            </p>
          </div>
        )}

        {permissionError && (
          <div className="mb-4 rounded-xl border border-[#E5E8EB] bg-[#F9FAFB] px-4 py-3 dark:border-[#2D3748] dark:bg-[#1A1F28]">
            <p className="text-sm text-[#4E5968] dark:text-[#9CA3AF]">
              <span className="font-semibold">🔒 권한 없음</span> · {permissionError}
            </p>
          </div>
        )}

        {accountBlock && (
          <div className="mb-4 rounded-xl border border-red-300 bg-red-50 px-4 py-3 dark:border-red-900/50 dark:bg-red-900/20">
            <p className="text-sm text-red-700 dark:text-red-400">
              <span className="font-semibold">⚠ 게재 중단</span> · {accountBlock} — 광고가 게재되지
              않고 있어요. Meta Ads Manager에서 충전이 필요합니다.
            </p>
          </div>
        )}

        {busy && <p className="text-sm text-[#8B95A1] py-20 text-center">불러오는 중…</p>}
        {error && (
          <p className="text-sm text-red-500 py-20 text-center" role="alert">
            {error}
          </p>
        )}

        {!busy && !error && campaigns.length > 0 && (
          <>
            <OriginLegend className="mb-4" />
            <MonitorKpis campaigns={campaigns} />

            {/* 계정 지갑 권한 없음 — 잔액·한도 조회 권한이 없을 때 자리 표시(빈 0과 구분). */}
            {source === 'live' && !account && accountUnavailable && (
              <div className="mb-6 rounded-xl border border-[#E5E8EB] bg-[#F9FAFB] px-4 py-3.5 dark:border-[#2D3748] dark:bg-[#1A1F28]">
                <span className="text-[14px] font-semibold text-[#4E5968] dark:text-[#9CA3AF]">
                  계정 지갑
                </span>
                <span className="ml-3 text-[14px] text-[#8B95A1]">{accountUnavailable}</span>
              </div>
            )}

            {/* 계정 지갑 — 실데이터일 때만. 일예산과 다른 '실제 충전·지출·잔액'. */}
            {source === 'live' && account && (
              <div className="mb-6 rounded-xl border border-[#E5E8EB] bg-white px-4 py-3.5 dark:border-[#2D3748] dark:bg-[#1A1F28]">
                <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
                  <span className="text-[14px] font-semibold text-[#4E5968] dark:text-[#9CA3AF]">
                    계정 지갑
                  </span>
                  <span className="text-[15px] text-[#191F28] dark:text-[#F2F4F6]">
                    선불 잔액{' '}
                    <b className="tabular-nums">
                      ₩{(account.available_balance_krw ?? 0).toLocaleString()}
                    </b>
                  </span>
                  <span className="text-[15px] text-[#191F28] dark:text-[#F2F4F6]">
                    누적 지출{' '}
                    <b className="tabular-nums">₩{(account.amount_spent_krw ?? 0).toLocaleString()}</b>
                  </span>
                  {account.spend_cap_krw != null && account.spend_cap_krw > 0 && (
                    <span className="text-[15px] text-[#191F28] dark:text-[#F2F4F6]">
                      충전 한도
                      <OriginTag origin="setting" />{' '}
                      <b className="tabular-nums">₩{account.spend_cap_krw.toLocaleString()}</b>
                      <span className="ml-1 text-[#8B95A1]">
                        ({Math.round(((account.amount_spent_krw ?? 0) / account.spend_cap_krw) * 100)}%
                        소진)
                      </span>
                    </span>
                  )}
                  {(() => {
                    const days = runwayDays(account, campaigns, spendSeries);
                    if (days == null) return null;
                    return (
                      <span
                        className={`text-[15px] ${days < 3 ? 'text-[#E5484D]' : 'text-[#191F28] dark:text-[#F2F4F6]'}`}
                        title="최근 일평균 소진이 이어진다는 가정의 추정값"
                      >
                        잔액 런웨이
                        <OriginTag origin="computed" /> <b className="tabular-nums">약 {days.toFixed(1)}일</b>
                        <span className="ml-1 text-[#8B95A1]">(추정)</span>
                      </span>
                    );
                  })()}
                </div>
              </div>
            )}

            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6]">
                캠페인 건강 신호
              </h2>
              <span className="text-[11px] text-[#8B95A1]">
                심각도순 · 지출 추세(7일)·페이싱·피로 추정 · 행 클릭 시 캠페인 관리로
              </span>
            </div>
            <HealthList campaigns={campaigns} spendSeries={spendSeries} now={now} />
          </>
        )}

        {!busy && !error && campaigns.length === 0 && (
          <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] py-20 text-center text-sm text-[#8B95A1]">
            모니터링할 캠페인이 없어요. 캠페인을 먼저 만들어 보세요.
          </div>
        )}

        <p className="mt-6 text-[12px] text-[#B0B8C1]">
          {source === 'live'
            ? `실데이터 · Meta 라이브 · 기간=${
                datePreset === 'last_30d' ? '최근 30일' : datePreset === 'this_month' ? '이번 달' : '전체 누적'
              } · 소진율=오늘 지출÷일예산(기간 토글 무관) · 금액 KRW`
            : '⚠ Mock 기반 데모 · 노출/지출은 일중 곡선 모델 기반 · "예측 CTR" 등 실측 환산 없음 · 금액 KRW'}
        </p>
      </div>
  );
}
