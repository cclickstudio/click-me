'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import AppLayout from '@/components/AppLayout';
import { api } from '@/lib/api';
import { CampaignTable } from '@/components/manage/campaigns/CampaignTable';
import { CampaignCards } from '@/components/manage/campaigns/CampaignCards';
import type {
  CampaignDetail as Detail,
  CampaignSource,
  CampaignSummary,
  CampaignView,
  PlatformMetrics,
} from '@/components/manage/campaigns/types';

export default function Page() {
  const [view, setView] = useState<CampaignView>('table');
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [source, setSource] = useState<CampaignSource>('mock');
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [platforms, setPlatforms] = useState<PlatformMetrics[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [accountBlock, setAccountBlock] = useState<string | null>(null);
  const [blockDetailOpen, setBlockDetailOpen] = useState(false);

  // silent=true면 폴링 갱신 — 로딩 스피너 없이 값만 교체.
  const load = useCallback(async (silent = false) => {
    if (!silent) setBusy(true);
    setError(null);
    try {
      const r = await api.management.campaigns();
      setCampaigns(r.campaigns);
      setSource(r.source ?? 'mock');
      setAccountBlock(r.account_block_reason ?? null);
      setLastUpdated(new Date().toLocaleTimeString('ko-KR'));
    } catch (e) {
      setError(e instanceof Error ? e.message : '불러오기 실패');
    } finally {
      if (!silent) setBusy(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // 실데이터일 때만 45초 폴링 — Meta가 분 단위로 갱신하므로 그 이상 잦게 안 함(rate limit).
  useEffect(() => {
    if (source !== 'live') return;
    const id = setInterval(() => load(true), 45000);
    return () => clearInterval(id);
  }, [source, load]);

  // 캠페인별 {상세, 플랫폼} 캐시 — 재토글·재방문 시 즉시 표시(재요청 0).
  type DetailEntry = { detail: Detail; platforms: PlatformMetrics[] };
  const detailCache = useRef<Map<string, DetailEntry>>(new Map());
  const inflight = useRef<Map<string, Promise<DetailEntry>>>(new Map());

  const fetchDetail = useCallback((id: string): Promise<DetailEntry> => {
    const hit = detailCache.current.get(id);
    if (hit) return Promise.resolve(hit);
    const pending = inflight.current.get(id);
    if (pending) return pending; // 호버로 시작한 요청을 클릭이 이어받음(중복 호출 0)
    const promise = Promise.all([
      api.management.campaign(id),
      api.management.campaignPlatforms(id),
    ])
      .then(([d, p]): DetailEntry => {
        const entry = { detail: d, platforms: p.platforms };
        detailCache.current.set(id, entry);
        inflight.current.delete(id);
        return entry;
      })
      .catch((e) => {
        inflight.current.delete(id);
        throw e;
      });
    inflight.current.set(id, promise);
    return promise;
  }, []);

  // 행/카드에 마우스 올리면 미리 가져옴 → 토글 누를 땐 이미 준비됨(체감 즉시).
  const prefetch = useCallback(
    (id: string) => {
      if (!detailCache.current.has(id)) fetchDetail(id).catch(() => {});
    },
    [fetchDetail],
  );

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      setPlatforms([]);
      return;
    }
    const hit = detailCache.current.get(selected);
    if (hit) {
      setDetail(hit.detail);
      setPlatforms(hit.platforms);
      return;
    }
    let alive = true;
    setDetail(null);
    setPlatforms([]);
    fetchDetail(selected)
      .then((e) => {
        if (!alive) return;
        setDetail(e.detail);
        setPlatforms(e.platforms);
      })
      .catch(() => {
        if (alive) {
          setDetail(null);
          setPlatforms([]);
        }
      });
    return () => {
      alive = false;
    };
  }, [selected, fetchDetail]);

  return (
    <AppLayout>
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">캠페인</h1>
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
                ? '실 Meta 연동 · 라이브 지표'
                : '목표·예산·성과를 한 창구에서 (Mock 기반 데모)'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {source === 'live' && (
              <button
                onClick={() => load(true)}
                title="새로고침"
                className="flex items-center gap-1.5 text-[11px] text-[#8B95A1] hover:text-[#191F28] dark:hover:text-[#F2F4F6] px-2 py-1.5"
              >
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                {lastUpdated ? `갱신 ${lastUpdated}` : '실시간'} ↻
              </button>
            )}
            <div className="flex rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] overflow-hidden text-sm">
              <button
                onClick={() => setView('table')}
                className={`px-3 py-1.5 ${view === 'table' ? 'bg-[#3182F6] text-white' : 'text-[#8B95A1]'}`}
              >
                테이블
              </button>
              <button
                onClick={() => setView('cards')}
                className={`px-3 py-1.5 ${view === 'cards' ? 'bg-[#3182F6] text-white' : 'text-[#8B95A1]'}`}
              >
                카드
              </button>
            </div>
            <Link
              href="/manage/campaigns/new"
              className="px-3 py-1.5 bg-[#3182F6] text-white text-sm font-medium rounded-lg hover:bg-[#1B6EEB]"
            >
              + 새 캠페인
            </Link>
          </div>
        </div>

        {accountBlock && (
          <div className="mb-4 rounded-xl border border-red-300 bg-red-50 px-4 py-3 dark:border-red-900/50 dark:bg-red-900/20">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm text-red-700 dark:text-red-400">
                <span className="font-semibold">⚠ 게재 중단</span> · {accountBlock} — 광고가 게재되지
                않고 있어요. Meta Ads Manager에서 충전이 필요합니다.
              </p>
              <button
                type="button"
                onClick={() => setBlockDetailOpen((o) => !o)}
                className="shrink-0 whitespace-nowrap text-[11px] font-medium text-red-700 underline underline-offset-2 hover:text-red-800 dark:text-red-400"
              >
                왜 중단됐나요? {blockDetailOpen ? '▲' : '▾'}
              </button>
            </div>
            {blockDetailOpen && (
              <div className="mt-2 space-y-1 border-t border-red-200 pt-2 text-[12px] text-red-700/90 dark:border-red-900/40 dark:text-red-400/90">
                <p>
                  <b>소진율(일예산)</b>과 <b>선불 잔액</b>은 다른 개념이에요.
                </p>
                <p>· <b>일예산</b> — 캠페인이 하루 쓸 수 있는 <b>한도</b> (남아 있어도 됨)</p>
                <p>· <b>선불 잔액</b> — 계정에 충전된 <b>실제 돈</b> (지금 ₩0 = 결제 재원 없음)</p>
                <p>
                  한도(일예산)가 남았어도 충전액이 0이면 Meta가 광고비를 차감할 수 없어 게재가 멈춰요.
                  Ads Manager에서 충전하면 재개됩니다.
                </p>
              </div>
            )}
          </div>
        )}

        {busy && <p className="text-sm text-[#8B95A1] py-20 text-center">불러오는 중…</p>}
        {error && (
          <p className="text-sm text-red-500 py-20 text-center" role="alert">
            {error}
          </p>
        )}

        {!busy && !error && campaigns.length > 0 && (
          <div className="space-y-4">
            {view === 'table' ? (
              <CampaignTable
                campaigns={campaigns}
                selected={selected}
                onSelect={(id) => setSelected((p) => (p === id ? null : id))}
                onPrefetch={prefetch}
                detail={detail}
                platforms={platforms}
                source={source}
              />
            ) : (
              <CampaignCards
                campaigns={campaigns}
                selected={selected}
                onSelect={(id) => setSelected((p) => (p === id ? null : id))}
                onPrefetch={prefetch}
                detail={detail}
                platforms={platforms}
                source={source}
              />
            )}
          </div>
        )}

        <p className="mt-6 text-[11px] text-[#B0B8C1]">
          {source === 'live'
            ? '실데이터 · Meta 라이브 · CVR/ROAS는 전환 추적 전이라 미측정 · 금액 KRW'
            : '⚠ Mock 기반 데모 · 노출/지출은 일중 곡선 모델 기반 · "예측 CTR" 등 실측 환산 없음 · 금액 KRW'}
        </p>
      </div>
    </AppLayout>
  );
}
