'use client';
// 매니지먼트 홈(커맨드 센터) — 전 탭의 핵심 신호를 벤토 그리드 한 화면으로. 타일 클릭 = 해당 탭 딥링크.

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { api, type BeforeAfterItem } from '@/lib/api';
import { BudgetGauge } from '@/components/manage/budget/BudgetGauge';
import { CampaignRadar } from '@/components/manage/CampaignRadar';
import { ConversionFunnel } from '@/components/manage/campaigns/ConversionFunnel';
import { HealthList } from '@/components/manage/monitoring/HealthList';
import { Sparkline } from '@/components/manage/monitoring/Sparkline';
import { ArcGauge } from '@/components/manage/WalletStrip';
import { trendDelta } from '@/components/manage/trend';
import {
  campaignHealth,
  frequencyFatigue,
  needsAttention,
} from '@/components/manage/monitoring/health';
import { metricsBlocked } from '@/components/manage/campaigns/types';
import type {
  AccountWallet,
  CampaignSource,
  CampaignSummary,
} from '@/components/manage/campaigns/types';
import type { BudgetStatus } from '@/components/manage/budget/types';

const VERDICT_CHIP: Record<BeforeAfterItem['verdict'], { label: string; cls: string }> = {
  aligned: { label: '예측대로', cls: 'bg-[#EBF3FF] text-primary dark:bg-[#1E3A5F] dark:text-[#7BB4F5]' },
  overperformed: { label: '예측보다 좋음', cls: 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-300' },
  underperformed: { label: '예측보다 약함', cls: 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300' },
  unknown: { label: '비교 대기', cls: 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-300' },
};

// 벤토 타일 — 전체가 해당 탭으로 가는 링크. hover 시 파란 테두리로 클릭 가능함을 알린다.
function Tile({
  href,
  title,
  hint,
  className = '',
  children,
}: {
  href: string;
  title: string;
  hint?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`block rounded-2xl border border-line bg-card p-5 transition-colors hover:border-primary ${className}`}
    >
      <div className="mb-2 flex items-center justify-between">
        <p className="text-[12px] font-semibold text-ink-secondary">{title}</p>
        <span className="text-[11px] text-ink-muted">{hint ?? '→'}</span>
      </div>
      {children}
    </Link>
  );
}

export default function Page() {
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [account, setAccount] = useState<AccountWallet | null>(null);
  const [source, setSource] = useState<CampaignSource>('mock');
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  const [baItems, setBaItems] = useState<BeforeAfterItem[] | null>(null);
  const [spendSeries, setSpendSeries] = useState<Record<string, number[]>>({});
  const [accountSeries, setAccountSeries] = useState<number[]>([]);
  const [now, setNow] = useState<Date>(() => new Date());
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);

  const load = useCallback(async () => {
    setBusy(true);
    // 세 소스 병렬 — 성과비교(Meta 라이브)는 느릴 수 있어 실패해도 나머지 타일은 뜬다.
    const [camps, bud, ba] = await Promise.allSettled([
      // include_series=true — 캠페인별 일별 지출을 목록에 함께 받아 상세 N콜(N+1) 제거.
      api.management.campaigns(undefined, undefined, undefined, undefined, undefined, true),
      api.management.budget(),
      api.management.beforeAfter(),
    ]);
    if (camps.status === 'fulfilled' && !camps.value.rate_limited) {
      setCampaigns(camps.value.campaigns);
      setAccount(camps.value.account ?? null);
      setSource(camps.value.source ?? 'mock');
      // 캠페인별 일별 지출 — 목록 응답의 series에서 추출(스파크라인 + 전사 추세 날짜 병합 합산).
      const entries = camps.value.campaigns.map(
        (c) => [c.campaign_id, c.series ?? []] as const,
      );
      setSpendSeries(Object.fromEntries(entries.map(([id, s]) => [id, s.map((p) => p.spend_krw)])));
      const byDate = new Map<string, number>();
      for (const [, s] of entries)
        for (const p of s) byDate.set(p.label, (byDate.get(p.label) ?? 0) + p.spend_krw);
      setAccountSeries([...byDate.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, v]) => v));
    }
    if (bud.status === 'fulfilled') setBudget(bud.value);
    setBaItems(ba.status === 'fulfilled' ? ba.value.items : []);
    setNow(new Date());
    setLastUpdated(new Date().toLocaleTimeString('ko-KR'));
    setBusy(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // ── 파생 신호(전부 실측/기존 규칙 기반 — 합성 없음) ──────────────────────
  const active = campaigns.filter((c) => c.state === 'active').length;
  const attention = campaigns.filter(
    (c) => needsAttention(campaignHealth(c).level) || frequencyFatigue(c)?.level === 'warn',
  );
  const spent = account?.amount_spent_krw ?? 0;
  const cap = account?.spend_cap_krw;
  const walletPct = cap != null && cap > 0 ? Math.min(100, Math.round((spent / cap) * 100)) : null;
  const walletStroke =
    walletPct == null
      ? ''
      : walletPct >= 95
        ? 'stroke-red-500'
        : walletPct >= 80
          ? 'stroke-amber-500'
          : 'stroke-[#2563EB]';
  const target = budget?.monthly_target_krw ?? budget?.limit_krw ?? 0;
  const projection = budget?.projection_krw ?? budget?.spent_krw ?? 0;
  const projPct = target > 0 ? Math.round((projection / target) * 100) : 0;
  const daysInMonth = budget?.period
    ? new Date(Number(budget.period.slice(0, 4)), Number(budget.period.slice(5, 7)), 0).getDate()
    : 30;
  const planPct =
    budget?.period === new Date().toISOString().slice(0, 7) && target > 0
      ? (new Date().getDate() / daysInMonth) * 100
      : null;
  // 전환 퍼널 대상 — 지출 1위(권한 있는) 캠페인.
  const topCampaign = campaigns
    .filter((c) => !metricsBlocked(c) && c.impressions > 0)
    .sort((a, b) => b.spend_krw - a.spend_krw)[0];
  const baTop = (baItems ?? []).slice(0, 3);

  // 오늘 브리핑 — 기존 규칙 신호를 한 문장으로(결정론, LLM 없음).
  const briefing: string[] = [];
  briefing.push(active > 0 ? `게재 중 ${active}건` : '게재 중인 캠페인 없음');
  if (walletPct != null && walletPct >= 95) briefing.push('지갑 거의 소진 → 충전 필요');
  if (attention.length > 0) briefing.push(`주의 신호 ${attention.length}건`);
  if (budget && budget.decision !== 'allow') briefing.push('월 목표 가드레일 경고');
  else if (target > 0 && projection > target) briefing.push('이 페이스면 월 목표 초과 예상');
  const overCnt = (baItems ?? []).filter((i) => i.verdict === 'overperformed').length;
  if (overCnt > 0) briefing.push(`예측보다 좋은 캠페인 ${overCnt}건 — 증액 검토`);

  return (
    <div className="max-w-screen-xl mx-auto px-6 py-8">
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-ink">매니지먼트 홈</h1>
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
            전 캠페인 핵심 신호를 한 화면에 · 타일을 누르면 해당 탭으로 이동해요
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0 text-xs text-ink-tertiary">
          {lastUpdated && <span>갱신 {lastUpdated}</span>}
          <button
            onClick={() => void load()}
            disabled={busy}
            className="px-2.5 py-1.5 rounded-lg border border-line hover:border-primary hover:text-primary disabled:opacity-50 transition-colors"
          >
            {busy ? '불러오는 중…' : '↻ 새로고침'}
          </button>
        </div>
      </div>

      {/* 오늘 브리핑 — 규칙 기반 한 줄 요약 */}
      {!busy && briefing.length > 0 && (
        <div className="mb-4 rounded-xl border border-primary/30 bg-primary-subtle/40 px-4 py-3">
          <p className="text-sm text-ink">
            <span className="font-bold text-primary">오늘 브리핑</span>
            <span className="ml-2">{briefing.join(' · ')}</span>
          </p>
        </div>
      )}

      {busy && campaigns.length === 0 ? (
        <p className="text-sm text-ink-tertiary py-20 text-center">불러오는 중…</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* HERO — 이번 달 예산 소진 (가장 큰 타일) */}
          <Tile
            href="/manage/budget"
            title={`${budget?.period ?? ''} 월 목표 대비 소진`}
            hint="예산 관리 →"
            className="md:col-span-2"
          >
            {budget && target > 0 ? (
              <>
                <BudgetGauge
                  spent={budget.spent_krw}
                  limit={target}
                  ratio={budget.ratio}
                  decision={budget.decision}
                  planPct={planPct}
                />
                <p className="mt-2 text-[11px] text-ink-tertiary">
                  이 페이스면 월말 ₩{projection.toLocaleString()} · 목표의 {projPct}%
                </p>
              </>
            ) : (
              <p className="py-6 text-sm text-ink-tertiary">
                월 목표가 없어요 — 예산 관리에서 설정하면 가드레일이 켜져요.
              </p>
            )}
          </Tile>

          {/* 주의 신호 */}
          <Tile href="/manage/monitoring" title="주의 신호" hint="모니터링 →">
            <p
              className={`text-4xl font-extrabold tabular-nums ${
                attention.length > 0 ? 'text-[#E5484D]' : 'text-ink'
              }`}
            >
              {attention.length}
            </p>
            <p className="mt-1 text-[11px] text-ink-tertiary">
              {attention.length > 0
                ? campaignHealth(attention[0]).label
                : '모든 캠페인이 정상이에요'}
            </p>
          </Tile>

          {/* 지갑 */}
          <Tile href="/manage/budget" title="계정 지갑" hint="예산 관리 →">
            <div className="flex items-center gap-3">
              {walletPct != null && (
                <div className="relative shrink-0">
                  <ArcGauge pct={walletPct} strokeClass={walletStroke} />
                  <span className="absolute inset-x-0 bottom-0 text-center text-[12px] font-bold tabular-nums text-ink">
                    {walletPct}%
                  </span>
                </div>
              )}
              <div>
                <p className="text-xl font-extrabold tabular-nums text-ink">
                  ₩{(account?.available_balance_krw ?? 0).toLocaleString()}
                </p>
                <p className="text-[11px] text-ink-tertiary">
                  선불 잔액{walletPct != null && walletPct >= 95 && ' · 거의 소진'}
                </p>
              </div>
            </div>
          </Tile>

          {/* 캠페인 성격 레이더 — 자체 카드라 그대로 배치(2개 미만이면 스스로 숨음) */}
          <div className="md:col-span-2">
            <CampaignRadar campaigns={campaigns} />
          </div>

          {/* 전환 퍼널 — 지출 1위 캠페인 */}
          {topCampaign && (
            <Tile
              href={`/manage/campaigns?open=${topCampaign.campaign_id}`}
              title={`전환 퍼널 · ${topCampaign.name}`}
              hint="상세 →"
            >
              <ConversionFunnel
                impressions={topCampaign.impressions}
                clicks={topCampaign.clicks}
                conversions={topCampaign.conversions}
                ctr={topCampaign.ctr}
                cvr={topCampaign.cvr}
              />
            </Tile>
          )}

          {/* 성과 비교 최신 판정 */}
          <Tile href="/manage/compare" title="성과 비교" hint="전체 보기 →">
            {baItems == null ? (
              <p className="py-4 text-sm text-ink-tertiary">불러오는 중…</p>
            ) : baTop.length === 0 ? (
              <p className="py-4 text-sm text-ink-tertiary">비교할 캠페인이 아직 없어요.</p>
            ) : (
              <div className="space-y-2">
                {baTop.map((it) => (
                  <div key={it.campaign_id} className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm text-ink">
                      {it.name}
                    </span>
                    <span
                      className={`shrink-0 rounded-lg px-2 py-0.5 text-[11px] font-semibold ${VERDICT_CHIP[it.verdict].cls}`}
                    >
                      {VERDICT_CHIP[it.verdict].label}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Tile>

          {/* 일별 지출 추세 */}
          <Tile href="/manage/budget" title="일별 지출 추세 (전체 기간)" hint="예산 관리 →" className="md:col-span-2">
            <div className="flex items-end justify-between gap-4">
              <div>
                <p className="text-2xl font-extrabold tabular-nums text-ink">
                  ₩{campaigns.reduce((a, c) => a + c.spend_krw, 0).toLocaleString()}
                </p>
                <p className="text-[11px] text-ink-tertiary">
                  누적 지출
                  {(() => {
                    const d = trendDelta(accountSeries);
                    if (d == null) return null;
                    const pct = Math.round(d * 100);
                    return (
                      <span className={pct >= 0 ? 'text-green-600 ml-1.5' : 'text-red-500 ml-1.5'}>
                        7일 {pct >= 0 ? '▲' : '▼'}
                        {Math.abs(pct)}%
                      </span>
                    );
                  })()}
                </p>
              </div>
              <Sparkline values={accountSeries} width={320} height={64} />
            </div>
          </Tile>

          {/* 캠페인 건강 신호 — 자체 카드·행별 딥링크 보유라 그대로 배치 */}
          <div className="md:col-span-2">
            <p className="mb-2 text-[12px] font-semibold text-ink-secondary">
              캠페인 건강 신호 <span className="font-normal text-ink-muted">· 행 클릭 시 캠페인 관리로</span>
            </p>
            <HealthList campaigns={campaigns} spendSeries={spendSeries} now={now} compact />
          </div>
        </div>
      )}

      <p className="mt-6 text-[11px] text-ink-muted">
        모든 타일은 실측(Meta)·기존 규칙 신호 기반이에요 · 상세 수치와 조작은 각 탭에서 · 금액 KRW
      </p>
    </div>
  );
}
