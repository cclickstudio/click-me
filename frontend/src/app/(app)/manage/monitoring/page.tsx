'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { api, type DatePreset } from '@/lib/api';
import { MonitorKpis } from '@/components/manage/monitoring/MonitorKpis';
import { HealthList } from '@/components/manage/monitoring/HealthList';
import { runwayDays } from '@/components/manage/monitoring/pacing';
import { OriginLegend } from '@/components/manage/ValueOrigin';
import { WeeklyReportModal } from '@/components/manage/monitoring/WeeklyReportModal';
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
  // 전 캠페인 일자별 합산 지출 — KPI '총 지출' 스파크라인·델타용(실측 합산, 날짜 기준 병합).
  const [accountSeries, setAccountSeries] = useState<number[]>([]);
  const [now, setNow] = useState<Date>(() => new Date());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [datePreset, setDatePreset] = useState<DatePreset>('maximum'); // 조회 기간 토글
  const [reportOpen, setReportOpen] = useState(false); // 주간 리포트 모달

  // 캠페인별 일별 지출 시계열 — 목록 응답의 series에서 추출(스파크라인·델타용).
  // 배치 1콜이라 폴링에도 부담이 없지만, 기존 동작 유지차 withSeries일 때만 갱신한다.
  const applySeries = useCallback((list: CampaignSummary[]) => {
    const entries = list.map((c) => [c.campaign_id, c.series ?? []] as const);
    setSpendSeries(
      Object.fromEntries(entries.map(([id, s]) => [id, s.map((p) => p.spend_krw)])),
    );
    // 날짜 기준 병합 합산 — 캠페인별 기간이 달라 인덱스가 아닌 날짜 라벨로 맞춘다.
    const byDate = new Map<string, number>();
    for (const [, s] of entries)
      for (const p of s) byDate.set(p.label, (byDate.get(p.label) ?? 0) + p.spend_krw);
    setAccountSeries(
      [...byDate.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, v]) => v),
    );
  }, []);

  // silent=true면 폴링 갱신(스피너 없이 값만 교체). withSeries=true면 시계열도 다시 가져온다.
  const load = useCallback(
    async (silent = false, withSeries = true) => {
      if (!silent) setBusy(true);
      setError(null);
      try {
        // withSeries일 때만 include_series로 일별 지출을 함께 받는다(폴링은 series 생략).
        const r = await api.management.campaigns(
          undefined,
          undefined,
          datePreset,
          undefined,
          undefined,
          withSeries,
        );
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
        if (withSeries) applySeries(r.campaigns);
      } catch (e) {
        setError(e instanceof Error ? e.message : '불러오기 실패');
      } finally {
        if (!silent) setBusy(false);
      }
    },
    [applySeries, datePreset],
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
              <h1 className="text-2xl font-bold text-ink">모니터링</h1>
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
            <p className="text-sm text-ink-tertiary mt-1">
              {source === 'live'
                ? '실 Meta 연동 · 전 캠페인 게재 건강 상태를 한눈에'
                : '전 캠페인 게재 건강 상태를 한눈에 (Mock 기반 데모)'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {source === 'live' && (
              <div className="flex rounded-lg border border-line overflow-hidden text-[12px]">
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
                        ? 'bg-primary text-primary-foreground'
                        : 'text-ink-tertiary hover:bg-[#F2F4F6] dark:hover:bg-[#2D3748]'
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
                className="flex items-center gap-1.5 text-[12px] text-ink-tertiary hover:text-ink dark:hover:text-[#F2F4F6] px-2 py-1.5"
              >
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                {lastUpdated ? `갱신 ${lastUpdated}` : '실시간'} ↻
              </button>
            )}
            {source === 'live' && (
              <button
                onClick={() => setReportOpen(true)}
                className="text-sm text-ink-secondary font-medium px-3 py-1.5 rounded-lg border border-line hover:bg-[#F2F4F6] dark:hover:bg-[#2D3748]"
              >
                성과 리포트
              </button>
            )}
            <Link
              href="/manage/anomaly"
              className="text-sm text-primary font-medium px-3 py-1.5 rounded-lg border border-line hover:bg-primary-subtle"
            >
              이상 감지 시연 →
            </Link>
          </div>
        </div>

        {reportOpen && (
          <WeeklyReportModal onClose={() => setReportOpen(false)} initialPeriod={datePreset} />
        )}

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
          <div className="mb-4 rounded-xl border border-line bg-[#F9FAFB] px-4 py-3 dark:bg-[#1A1F28]">
            <p className="text-sm text-ink-secondary">
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

        {busy && <p className="text-sm text-ink-tertiary py-20 text-center">불러오는 중…</p>}
        {error && (
          <p className="text-sm text-red-500 py-20 text-center" role="alert">
            {error}
          </p>
        )}

        {!busy && !error && campaigns.length > 0 && (
          <>
            <OriginLegend className="mb-4" />
            {/* 지갑 상세는 예산 관리 탭이 정식 집 — 여기선 파생 건강신호(잔액 런웨이)만 KPI로. */}
            <MonitorKpis
              campaigns={campaigns}
              accountSeries={accountSeries}
              runway={account ? runwayDays(account, campaigns, spendSeries) : null}
            />

            {/* 계정 지갑 권한 없음 — 잔액·한도 조회 권한이 없을 때 자리 표시(빈 0과 구분). */}
            {source === 'live' && !account && accountUnavailable && (
              <div className="mb-6 rounded-xl border border-line bg-[#F9FAFB] px-4 py-3.5 dark:bg-[#1A1F28]">
                <span className="text-[14px] font-semibold text-ink-secondary">
                  계정 지갑
                </span>
                <span className="ml-3 text-[14px] text-ink-tertiary">{accountUnavailable}</span>
              </div>
            )}

            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-bold text-ink">
                캠페인 건강 신호
              </h2>
              <span className="text-[11px] text-ink-tertiary">
                심각도순 · 지출 추세(7일)·페이싱·피로 추정 · 행 클릭 시 캠페인 관리로
              </span>
            </div>
            <HealthList campaigns={campaigns} spendSeries={spendSeries} now={now} />
          </>
        )}

        {!busy && !error && campaigns.length === 0 && (
          <div className="rounded-2xl border border-line py-20 text-center text-sm text-ink-tertiary">
            모니터링할 캠페인이 없어요. 캠페인을 먼저 만들어 보세요.
          </div>
        )}

        <p className="mt-6 text-[12px] text-ink-muted">
          {source === 'live'
            ? `실데이터 · Meta 라이브 · 기간=${
                datePreset === 'last_30d' ? '최근 30일' : datePreset === 'this_month' ? '이번 달' : '전체 누적'
              } · 소진율=오늘 지출÷일예산(기간 토글 무관) · 금액 KRW`
            : '⚠ Mock 기반 데모 · 노출/지출은 일중 곡선 모델 기반 · "예측 CTR" 등 실측 환산 없음 · 금액 KRW'}
        </p>
      </div>
  );
}
