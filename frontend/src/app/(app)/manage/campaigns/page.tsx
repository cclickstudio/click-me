'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { api, getAdminOrgId } from '@/lib/api';
import { useAuth } from '@/components/AuthProvider';
import { CampaignTable } from '@/components/manage/campaigns/CampaignTable';
import { CampaignCards } from '@/components/manage/campaigns/CampaignCards';
import { OriginLegend } from '@/components/manage/ValueOrigin';
import { CampaignRadar } from '@/components/manage/CampaignRadar';
import type {
  AccountWallet,
  CampaignDetail as Detail,
  CampaignSource,
  CampaignSummary,
  CampaignView,
  CreativePreview,
  DemographicMetrics,
  ManualKpiMap,
  PlatformMetrics,
} from '@/components/manage/campaigns/types';

export default function Page() {
  const [view, setView] = useState<CampaignView>('table');
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [source, setSource] = useState<CampaignSource>('mock');
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [platforms, setPlatforms] = useState<PlatformMetrics[]>([]);
  const [demographics, setDemographics] = useState<DemographicMetrics[]>([]);
  const [creatives, setCreatives] = useState<CreativePreview[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [accountBlock, setAccountBlock] = useState<string | null>(null);
  const [blockDetailOpen, setBlockDetailOpen] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null); // Meta 토큰 만료 안내
  const [rateLimited, setRateLimited] = useState<string | null>(null); // Meta 요청 한도(일시)
  const [permissionError, setPermissionError] = useState<string | null>(null); // 목록/자금 권한 없음
  const [includeArchived, setIncludeArchived] = useState(false); // 삭제됨(보관) 캠페인 포함 보기
  const [account, setAccount] = useState<AccountWallet | null>(null); // 계정 지갑(잔액·한도·지출)
  // 전환 1건 가치(₩)·목표 ROAS — 고객이 입력하는 사업 통계. CVR·ROAS는 이 값으로 '계산'된다
  // (직접 입력 아님 — CVR=전환÷클릭 실측, ROAS=(전환×가치)÷지출 추정). 스펙: CVR·ROAS 재정의.
  const [convValue, setConvValue] = useState<number | null>(null);
  const [targetRoas, setTargetRoas] = useState<number | null>(null);
  const [showKpiHelp, setShowKpiHelp] = useState(false); // CVR·ROAS 계산 방식 접이식 설명
  // 수동 추정 CVR·ROAS — 전환 데이터가 없는(미설정) 캠페인에만 직접 입력(하이브리드).
  // 실측이 있으면 그 값을 읽기전용으로 쓰고, 여기 값은 무시된다. 조직 단위 DB 영속.
  const [manualKpi, setManualKpi] = useState<ManualKpiMap>({});
  // admin이 '전체(all orgs)'로 볼 때 — kpi-override는 impersonate 전용이라 빈 응답. '조직 선택' 안내로 대체.
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';
  const [noOrgSelected, setNoOrgSelected] = useState(false);
  useEffect(() => {
    setNoOrgSelected(getAdminOrgId() == null);
  }, []);
  const kpiHidden = isAdmin && noOrgSelected;

  useEffect(() => {
    if (kpiHidden) return; // 전체 스코프에선 조회하지 않는다(빈 값으로 덮지 않도록).
    let alive = true;
    api.management
      .kpiOverrides()
      .then((r) => {
        if (alive) setManualKpi(r.overrides ?? {});
      })
      .catch(() => {}); // 미인증 등 — 무시
    return () => {
      alive = false;
    };
  }, [kpiHidden]);

  // 미설정 셀 직접 입력 → 낙관적 갱신 + DB 저장(PUT). 빈 값이면 필드 제거(둘 다 비면 행 삭제).
  const editKpi = useCallback((id: string, field: 'cvr' | 'roas', raw: string) => {
    setManualKpi((prev) => {
      const v = raw.trim() === '' ? undefined : Number(raw);
      const entry = { ...prev[id] };
      if (v == null || !Number.isFinite(v)) delete entry[field];
      else entry[field] = v;
      const next = { ...prev, [id]: entry };
      if (Object.keys(entry).length === 0) delete next[id];
      api.management
        .putKpiOverride(id, { cvr: entry.cvr ?? null, roas: entry.roas ?? null })
        .catch(() => {});
      return next;
    });
  }, []);

  // 무한스크롤 — 최근순 20개씩. 폴링/새로고침은 현재까지 로드한 만큼(loadedCount) 다시 채워 스크롤 유지.
  const PAGE_SIZE = 20;
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [total, setTotal] = useState<number | null>(null);
  const loadedCountRef = useRef(0);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  // silent=true면 폴링 갱신 — 로딩 스피너 없이 값만 교체. 첫 페이지부터 현재 로드분까지 재조회.
  const load = useCallback(async (silent = false) => {
    if (!silent) setBusy(true);
    setError(null);
    try {
      const limit = Math.max(PAGE_SIZE, loadedCountRef.current);
      const r = await api.management.campaigns(convValue, targetRoas, undefined, includeArchived, {
        limit,
        offset: 0,
      });
      // Meta 요청 한도(일시) — 빈 목록으로 덮지 말고 기존 데이터 유지 + 배너만(폴링이 곧 복구).
      if (r.rate_limited) {
        setRateLimited(r.rate_limited);
        return;
      }
      setRateLimited(null);
      setCampaigns(r.campaigns);
      loadedCountRef.current = r.campaigns.length;
      setHasMore(r.has_more ?? false);
      setTotal(r.total ?? r.campaigns.length);
      setSource(r.source ?? 'mock');
      setAccountBlock(r.account_block_reason ?? null);
      setAuthError(r.auth_error ?? null);
      setPermissionError(
        r.permission_error ?? r.not_connected ?? r.account_unavailable ?? r.select_org ?? null,
      );
      setAccount(r.account ?? null);
      setLastUpdated(new Date().toLocaleTimeString('ko-KR'));
    } catch (e) {
      setError(e instanceof Error ? e.message : '불러오기 실패');
    } finally {
      if (!silent) setBusy(false);
    }
  }, [convValue, targetRoas, includeArchived]);

  // 스크롤 하단 도달 시 다음 20개를 이어 붙인다(중복 id 제거).
  const loadMore = useCallback(async () => {
    if (loadingMore) return;
    setLoadingMore(true);
    try {
      const r = await api.management.campaigns(convValue, targetRoas, undefined, includeArchived, {
        limit: PAGE_SIZE,
        offset: loadedCountRef.current,
      });
      if (r.rate_limited) {
        setRateLimited(r.rate_limited);
        return;
      }
      setCampaigns((prev) => {
        const seen = new Set(prev.map((c) => c.campaign_id));
        const merged = [...prev, ...r.campaigns.filter((c) => !seen.has(c.campaign_id))];
        loadedCountRef.current = merged.length;
        return merged;
      });
      setHasMore(r.has_more ?? false);
      if (r.total != null) setTotal(r.total);
    } catch {
      // 다음 페이지 로드 실패는 조용히 무시 — 재스크롤/폴링으로 재시도.
    } finally {
      setLoadingMore(false);
    }
  }, [convValue, targetRoas, includeArchived, loadingMore]);

  // 필터(전환가치·ROAS·보관포함) 변경 시 첫 페이지부터 다시 로드.
  useEffect(() => {
    loadedCountRef.current = 0;
    load();
  }, [load]);

  // 무한스크롤 관측 — 센티넬이 보이고 더 있으면 다음 페이지 로드.
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasMore && !loadingMore && !busy) loadMore();
      },
      { rootMargin: '200px' },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [hasMore, loadingMore, busy, loadMore]);

  // 채팅 캠페인 칩 딥링크 — ?open=<campaign_id> 로 진입 시 해당 캠페인 상세 자동 열기.
  useEffect(() => {
    const openId = new URLSearchParams(window.location.search).get('open');
    if (openId) setSelected(openId);
  }, []);

  // 실데이터일 때만 120초 폴링 — Meta는 분 단위 갱신이라 잦게 안 함(rate limit 절감).
  // 탭이 숨겨져 있으면(다른 탭/최소화) 폴링하지 않아 불필요한 Meta 호출을 막는다.
  useEffect(() => {
    if (source !== 'live') return;
    const id = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      load(true);
    }, 120000);
    return () => clearInterval(id);
  }, [source, load]);

  // 캠페인별 {상세, 플랫폼} 캐시 — 재토글·재방문 시 즉시 표시(재요청 0).
  type DetailEntry = {
    detail: Detail;
    platforms: PlatformMetrics[];
    demographics: DemographicMetrics[];
    creatives: CreativePreview[];
  };
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
      api.management.campaignDemographics(id),
      api.management.campaignCreatives(id),
    ])
      .then(([d, p, g, c]): DetailEntry => {
        const entry = {
          detail: d,
          platforms: p.platforms,
          demographics: g.demographics,
          creatives: c.creatives,
        };
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

  // 캠페인 삭제 — 대시보드에서 삭제 = Meta에서도 삭제. 되돌릴 수 없어 확인 후 진행.
  const handleDelete = useCallback(
    async (id: string, name: string) => {
      if (!window.confirm(`'${name}' 캠페인을 삭제할까요?\nMeta에서도 삭제되며 되돌릴 수 없습니다.`))
        return;
      try {
        const { result } = await api.management.deleteCampaign(id);
        if (result.status !== 'success') {
          setError(`삭제 실패 — ${result.failure_reason ?? '알 수 없음'}`);
          return;
        }
        detailCache.current.delete(id);
        if (selected === id) setSelected(null);
        await load(true);
      } catch (e) {
        setError(e instanceof Error ? e.message : '삭제 실패');
      }
    },
    [load, selected],
  );

  // 게재시작/일시중지/정산 후 — 상세 캐시 비우고 목록 새로고침(상태 배지·지표 최신화).
  const handleChanged = useCallback(() => {
    detailCache.current.clear();
    load(true);
  }, [load]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      setPlatforms([]);
      setDemographics([]);
      setCreatives([]);
      return;
    }
    const hit = detailCache.current.get(selected);
    if (hit) {
      setDetail(hit.detail);
      setPlatforms(hit.platforms);
      setDemographics(hit.demographics);
      setCreatives(hit.creatives);
      return;
    }
    let alive = true;
    setDetail(null);
    setPlatforms([]);
    setDemographics([]);
    setCreatives([]);
    fetchDetail(selected)
      .then((e) => {
        if (!alive) return;
        setDetail(e.detail);
        setPlatforms(e.platforms);
        setDemographics(e.demographics);
        setCreatives(e.creatives);
      })
      .catch(() => {
        if (alive) {
          setDetail(null);
          setPlatforms([]);
          setDemographics([]);
          setCreatives([]);
        }
      });
    return () => {
      alive = false;
    };
  }, [selected, fetchDetail]);

  return (
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
                onClick={() => setIncludeArchived((v) => !v)}
                title="보관·삭제된 캠페인을 과거 데이터와 함께 표시 (Meta에서 완전 삭제된 캠페인은 Meta가 제공하지 않아 안 보일 수 있어요)"
                className={`text-[12px] px-2.5 py-1.5 rounded-lg border ${
                  includeArchived
                    ? 'border-[#3182F6] text-[#3182F6] bg-[#EBF3FF] dark:bg-[#1E3A5F]'
                    : 'border-[#E5E8EB] dark:border-[#2D3748] text-[#8B95A1] hover:text-[#191F28] dark:hover:text-[#F2F4F6]'
                }`}
              >
                {includeArchived ? '✓ 삭제됨 포함' : '삭제됨 포함'}
              </button>
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

        {authError && (
          <div className="mb-4 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 dark:border-amber-900/50 dark:bg-amber-900/20">
            <p className="text-sm text-amber-800 dark:text-amber-300">
              <span className="font-semibold">⚠ Meta 연결 만료</span> · {authError} 실데이터를
              불러올 수 없어요. 관리자가 Meta 액세스 토큰을 갱신하면 다시 표시됩니다.
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

        {rateLimited && (
          <div className="mb-4 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 dark:border-amber-900/50 dark:bg-amber-900/20">
            <p className="text-sm text-amber-800 dark:text-amber-300">
              <span className="font-semibold">⏳ Meta 요청 한도(일시)</span> · {rateLimited} 아래
              표는 마지막으로 불러온 값이에요.
            </p>
          </div>
        )}

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

        {kpiHidden && (
          <div className="mb-4 rounded-xl border border-[#E5E8EB] bg-[#F9FAFB] px-4 py-3 dark:border-[#2D3748] dark:bg-[#1A1F28]">
            <p className="text-sm text-[#4E5968] dark:text-[#9CA3AF]">
              <span className="font-semibold">🏢 조직을 선택하세요</span> · 수동 KPI(추정 CVR·ROAS)는
              특정 조직으로 전환했을 때만 조회·편집할 수 있어요. 상단 ‘조직 전환’에서 조직을 고르면
              KPI가 표시됩니다.
            </p>
          </div>
        )}

        {busy && <p className="text-sm text-[#8B95A1] py-20 text-center">불러오는 중…</p>}
        {error && (
          <p className="text-sm text-red-500 py-20 text-center" role="alert">
            {error}
          </p>
        )}

        {/* 지갑(잔액·한도)은 예산 관리 탭이 정식 집 — 여기선 게재 중단 배너가 이상만 알린다. */}

        {!busy && !error && campaigns.length > 0 && (
          <div className="space-y-4">
            <OriginLegend />
            {/* 입력은 둘뿐 — CVR·ROAS는 이 값으로 계산되는 결과(직접 입력 아님) */}
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] px-4 py-3">
              <label className="flex items-center gap-2 text-sm text-[#4E5968] dark:text-[#9CA3AF]">
                전환 1건 가치
                <span className="inline-flex items-center">
                  <span className="text-[#8B95A1]">₩</span>
                  <input
                    type="number"
                    min={0}
                    step={1000}
                    placeholder="예: 30000"
                    value={convValue ?? ''}
                    onChange={(e) =>
                      setConvValue(e.target.value === '' ? null : Number(e.target.value))
                    }
                    className="ml-1 w-28 rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent px-2 py-1 text-right text-sm tabular-nums text-[#191F28] dark:text-[#F2F4F6] focus:border-[#3182F6] outline-none"
                  />
                </span>
              </label>
              <label className="flex items-center gap-2 text-sm text-[#4E5968] dark:text-[#9CA3AF]">
                목표 ROAS
                <span className="inline-flex items-center">
                  <input
                    type="number"
                    min={0}
                    step={0.1}
                    placeholder="예: 3.0"
                    value={targetRoas ?? ''}
                    onChange={(e) =>
                      setTargetRoas(e.target.value === '' ? null : Number(e.target.value))
                    }
                    className="w-20 rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent px-2 py-1 text-right text-sm tabular-nums text-[#191F28] dark:text-[#F2F4F6] focus:border-[#3182F6] outline-none"
                  />
                  <span className="ml-0.5 text-[#8B95A1]">x</span>
                </span>
              </label>
              <span className="text-[12px] text-[#8B95A1]">
                전환 가치 입력 시 ROAS(추정)가 채워지고, 목표 미달이면 표에 ‘목표↓’로 표시돼요.
              </span>
              <button
                type="button"
                onClick={() => setShowKpiHelp((o) => !o)}
                className="ml-auto shrink-0 text-[12px] text-[#8B95A1] hover:text-[#3182F6] transition-colors"
              >
                ⓘ CVR·ROAS 계산 방식 {showKpiHelp ? '▲' : '▾'}
              </button>
              {showKpiHelp && (
                <p className="w-full text-[12px] leading-relaxed text-[#8B95A1] border-t border-[#F2F4F6] dark:border-[#2D3748] pt-2">
                  <b>CVR(전환율)</b> = 전환수 ÷ 링크 클릭수(실측 · CTR의 전체 클릭과 분모가 달라요) ·{' '}
                  <b>ROAS(투자수익률)</b> = 전환가치 × 전환수 ÷ 지출(추정). 실측 데이터가 있으면{' '}
                  <b>계산 결과(읽기전용)</b>로 뜨고, 전환 추적 전 ‘미설정’ 캠페인은 표에서{' '}
                  <b>직접 추정값</b>을 넣을 수 있어요.
                </p>
              )}
            </div>
            {view === 'table' ? (
              <CampaignTable
                campaigns={campaigns}
                selected={selected}
                onSelect={(id) => setSelected((p) => (p === id ? null : id))}
                onPrefetch={prefetch}
                onDelete={handleDelete}
                detail={detail}
                platforms={platforms}
                demographics={demographics}
                creatives={creatives}
                account={account}
                manualKpi={manualKpi}
                onEditKpi={editKpi}
                onChanged={handleChanged}
                source={source}
              />
            ) : (
              <CampaignCards
                campaigns={campaigns}
                selected={selected}
                onSelect={(id) => setSelected((p) => (p === id ? null : id))}
                onPrefetch={prefetch}
                onDelete={handleDelete}
                detail={detail}
                platforms={platforms}
                demographics={demographics}
                creatives={creatives}
                account={account}
                manualKpi={manualKpi}
                onEditKpi={editKpi}
                onChanged={handleChanged}
                source={source}
              />
            )}
            {/* 캠페인 성격 비교 레이더 — 지출 상위 캠페인 5축 상대 비교(2개 미만이면 자체 숨김) */}
            <CampaignRadar campaigns={campaigns} />
            {/* 무한스크롤 센티넬 — 화면에 들어오면 다음 20개 로드 */}
            <div ref={sentinelRef} className="h-1" />
            {loadingMore && (
              <p className="text-center text-[12px] text-[#8B95A1] py-3">더 불러오는 중…</p>
            )}
            {!hasMore && total != null && campaigns.length > 0 && (
              <p className="text-center text-[12px] text-[#B0B8C1] py-3">
                전체 {total}개 캠페인을 모두 불러왔어요
              </p>
            )}
          </div>
        )}

        <p className="mt-6 text-[12px] text-[#B0B8C1]">
          {source === 'live'
            ? '실데이터 · Meta 라이브(전체 기간 누적) · CVR은 전환(구매·리드·가입 등) 발생 시 · ROAS는 전환가치 입력 시 추정 · 금액 KRW'
            : '⚠ Mock 기반 데모 · 노출/지출은 일중 곡선 모델 기반 · "예측 CTR" 등 실측 환산 없음 · 금액 KRW'}
        </p>
      </div>
  );
}
