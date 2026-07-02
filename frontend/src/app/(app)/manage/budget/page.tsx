'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, type RebalanceProposal } from '@/lib/api';
import { BudgetGauge } from '@/components/manage/budget/BudgetGauge';
import { OriginLegend } from '@/components/manage/ValueOrigin';
import { StatCard } from '@/components/manage/StatCard';
import { SpendDonut } from '@/components/manage/budget/SpendDonut';
import { trendDelta } from '@/components/manage/trend';
import type { BudgetDecision, BudgetStatus } from '@/components/manage/budget/types';
import { formatKSTFull } from '@/lib/datetime';

const WARNING: Record<Exclude<BudgetDecision, 'allow'>, { label: string; msg: string; cls: string }> = {
  warn: {
    label: '경고',
    msg: '월 목표 90% 도달 — 페이스 점검하세요.',
    cls: 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-900/20 dark:text-amber-200 dark:border-amber-800',
  },
  escalate: {
    label: '주의',
    msg: '95% 초과 — 목표 초과가 임박했습니다.',
    cls: 'bg-red-50 text-red-800 border-red-200 dark:bg-red-900/20 dark:text-red-200 dark:border-red-800',
  },
  block: {
    label: '목표 초과',
    msg: '100% 초과 — 이번 달 목표를 넘었습니다.',
    cls: 'bg-red-100 text-red-900 border-red-300 dark:bg-red-900/30 dark:text-red-100 dark:border-red-700',
  },
};

// 크레딧 원장 항목 — /billing/history (ClickMe 크레딧, 광고비와 별개)
type LedgerEntry = {
  entry_id: string;
  delta_krw: number;
  balance_after_krw: number;
  reason: string;
  ref_id: string;
  created_at: string;
};
const REASON: Record<string, { label: string; cls: string }> = {
  charge: { label: '충전', cls: 'text-[#3182F6]' },
  spend: { label: '집행 차감', cls: 'text-[#4E5968] dark:text-[#9CA3AF]' },
  refund: { label: '환불', cls: 'text-amber-600 dark:text-amber-400' },
};

export default function Page() {
  const [status, setStatus] = useState<BudgetStatus | null>(null);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [targetInput, setTargetInput] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  // 캠페인별 지출 기간 토글 — 이번 달 ₩0이면 전체 기간(실측)으로 볼 수 있게.
  const [spendScope, setSpendScope] = useState<'month' | 'all'>('month');
  const [allTimeSpend, setAllTimeSpend] = useState<
    { name: string; spend_krw: number; roas?: number | null }[] | null
  >(null);
  // 예산 리밸런싱 제안 — 저효율→고효율 이동(적용은 budget-commit 2건, HITL 유지)
  const [rebalance, setRebalance] = useState<RebalanceProposal | null>(null);
  const [rebalanceNote, setRebalanceNote] = useState<string | null>(null);
  const [rebalanceBusy, setRebalanceBusy] = useState(false);
  const [rebalanceMsg, setRebalanceMsg] = useState<string | null>(null);
  // 월 매출 기반 목표 계산기 — 벤치마크(매출의 5~15%)를 계산기로 승격
  const [revenueInput, setRevenueInput] = useState(0);

  const fetchData = useCallback(async (initial = false) => {
    setRefreshing(true);
    try {
      const b = await api.management.budget();
      setStatus(b);
      if (initial) setTargetInput(b.monthly_target_krw ?? b.limit_krw);
      setLastUpdated(new Date().toLocaleTimeString('ko-KR'));
    } catch (e) {
      setError(e instanceof Error ? e.message : '불러오기 실패');
    } finally {
      setRefreshing(false);
    }
    api.billing
      .history()
      .then((r) => setLedger(r.entries))
      .catch(() => {});
    api.management
      .rebalanceProposal()
      .then((r) => {
        setRebalance(r.proposal);
        setRebalanceNote(r.note);
      })
      .catch(() => {});
  }, []);

  // 리밸런싱 적용 — 기존 budget-commit(검증·승인·감사)을 두 캠페인에 순서대로.
  // 감액을 먼저 해 총예산이 순간적으로도 늘지 않게 한다.
  const applyRebalance = async () => {
    if (!rebalance) return;
    setRebalanceBusy(true);
    setRebalanceMsg(null);
    try {
      await api.management.budgetCommit(rebalance.from.campaign_id, {
        action: 'decrease_budget',
        new_daily_budget_krw: rebalance.from.after_krw,
        shown_budget_before_krw: rebalance.from.daily_budget_krw,
      });
      await api.management.budgetCommit(rebalance.to.campaign_id, {
        action: 'increase_budget',
        new_daily_budget_krw: rebalance.to.after_krw,
        shown_budget_before_krw: rebalance.to.daily_budget_krw,
      });
      setRebalanceMsg('적용 완료 — 두 캠페인의 일예산을 변경했어요.');
      setRebalance(null);
      void fetchData();
    } catch (e) {
      setRebalanceMsg(e instanceof Error ? e.message : '적용 실패');
    } finally {
      setRebalanceBusy(false);
    }
  };

  useEffect(() => {
    void fetchData(true);
  }, [fetchData]);

  // 전체 기간 지출 — 토글 첫 진입 시 1회 로드(캠페인 목록 API의 누적 spend 실측 재사용).
  useEffect(() => {
    if (spendScope !== 'all' || allTimeSpend != null) return;
    let alive = true;
    api.management
      .campaigns()
      .then((r) => {
        if (!alive) return;
        setAllTimeSpend(
          (r.campaigns ?? []).map((c) => ({
            name: c.name,
            spend_krw: c.spend_krw,
            roas: c.roas,
          })),
        );
      })
      .catch(() => alive && setAllTimeSpend([]));
    return () => {
      alive = false;
    };
  }, [spendScope, allTimeSpend]);

  const applyTarget = async () => {
    setBusy(true);
    setError(null);
    try {
      const b = await api.management.setBudgetLimit(targetInput);
      setStatus(b);
    } catch (e) {
      setError(e instanceof Error ? e.message : '월 목표 설정 실패');
    } finally {
      setBusy(false);
    }
  };

  const warn = status && status.decision !== 'allow' ? WARNING[status.decision] : null;
  // 캠페인별 지출 — 토글 스코프에 따라 이번 달(budget API) / 전체 기간(campaigns API 누적) 실측.
  const spendRows =
    spendScope === 'all' && allTimeSpend != null ? allTimeSpend : (status?.campaigns ?? []);
  const maxSpend = Math.max(...spendRows.map((c) => c.spend_krw), 1);

  // 런레이트(월말 예상) vs 목표
  const target = status?.monthly_target_krw ?? status?.limit_krw ?? 0;
  const projection = status?.projection_krw ?? status?.spent_krw ?? 0;
  const projPct = target > 0 ? Math.round((projection / target) * 100) : 0;
  const projOver = target > 0 && projection > target;

  // 일자별 계획선 — 월 목표 / 이번 달 일수
  const daysInMonth = status?.period
    ? new Date(Number(status.period.slice(0, 4)), Number(status.period.slice(5, 7)), 0).getDate()
    : 30;
  // 오늘까지 계획 페이스(월 경과율) — 게이지 점선 마커. 이번 달이 아니면 표시하지 않는다.
  const nowYm = new Date().toISOString().slice(0, 7);
  const planPct =
    status?.period === nowYm && target > 0 ? (new Date().getDate() / daysInMonth) * 100 : null;
  const dailyPlan = target > 0 ? Math.round(target / daysInMonth) : 0;
  const daily = status?.daily ?? [];
  const maxDaily = Math.max(...daily.map((d) => d.spend_krw), dailyPlan, 1);

  return (
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        <div className="mb-6 flex items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">예산 관리</h1>
            <p className="text-sm text-[#8B95A1] mt-1">
              월 목표 예산 대비 이번 달 실 Meta 집행 페이싱 · 여력=Meta 선불 잔액 · 90/95/100% 가드레일
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0 text-xs text-[#8B95A1]">
            {lastUpdated && <span>갱신 {lastUpdated}</span>}
            <button
              onClick={() => void fetchData()}
              disabled={refreshing}
              className="px-2.5 py-1.5 rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] hover:border-[#3182F6] hover:text-[#3182F6] disabled:opacity-50 transition-colors"
            >
              {refreshing ? '불러오는 중…' : '↻ 새로고침'}
            </button>
          </div>
        </div>

        {error && <p className="text-sm text-red-500 mb-4" role="alert">{error}</p>}

        {status && (
          <div className="space-y-4">
            {warn && (
              <div className={`rounded-2xl border px-4 py-3 text-sm ${warn.cls}`}>
                <b>{warn.label}</b> · {warn.msg}
              </div>
            )}

            {/* 기본 목표 벤치마크 — 어떤 규모의 회사를 가정한 값인지(근거: management.py _BUDGET 주석) */}
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#1A202C] px-5 py-3.5">
              <span className="text-[13px] font-semibold text-[#4E5968] dark:text-[#9CA3AF]">
                기본 목표 기준
              </span>
              {(
                [
                  ['가정 업종·규모', '이커머스·리테일 소기업 (5~20인)'],
                  ['월 매출', '₩2,000만~6,000만'],
                  ['광고비 비중', '매출의 5~15%'],
                  ['권장 월 광고비', '₩3,000,000 (일 ₩100,000)'],
                ] as [string, string][]
              ).map(([label, value]) => (
                <div key={label}>
                  <p className="text-[11px] text-[#8B95A1]">{label}</p>
                  <p className="mt-0.5 text-[13px] font-semibold text-[#191F28] dark:text-[#F2F4F6]">
                    {value}
                  </p>
                </div>
              ))}
              <span className="ml-auto hidden text-[11px] text-[#B0B8C1] lg:block">
                내 매출 규모에 맞게 아래에서 목표를 조정하세요
              </span>
            </div>

            <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-5">
              <div className="flex items-center justify-between mb-3">
                <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">
                  {status.period ?? ''} 월 목표 대비 소진
                </p>
                {target > 0 && (
                  <span
                    className={`text-xs font-medium px-2 py-1 rounded-lg ${
                      projOver
                        ? 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300'
                        : 'bg-[#EBF3FF] text-[#3182F6] dark:bg-[#1E3A5F] dark:text-[#7BB4F5]'
                    }`}
                  >
                    이 페이스면 월말 ₩{projection.toLocaleString()} · 목표의 {projPct}%
                  </span>
                )}
              </div>
              <BudgetGauge
                spent={status.spent_krw}
                limit={target}
                ratio={status.ratio}
                decision={status.decision}
                planPct={planPct}
              />
            </div>

            <OriginLegend />
            <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
              <StatCard label="월 목표" value={`₩${target.toLocaleString()}`} origin="setting" />
              <StatCard
                label="이번 달 소진"
                value={`₩${status.spent_krw.toLocaleString()}`}
                series={daily.map((d) => d.spend_krw)}
                delta={trendDelta(daily.map((d) => d.spend_krw))}
                deltaLabel="일간"
              />
              <StatCard
                label="잔여"
                value={`₩${status.remaining_krw.toLocaleString()}`}
                origin="computed"
              />
              <StatCard
                label="월 목표 소진율"
                value={`${(status.ratio * 100).toFixed(0)}%`}
                origin="computed"
                alert={status.decision !== 'allow'}
              />
              <StatCard
                label="크레딧 잔액 (집행 한도)"
                value={`₩${(status.credit_balance_krw ?? 0).toLocaleString()}`}
                sub="ClickMe 크레딧 — spend_cap"
              />
              <StatCard
                label="여력 (Meta 선불 잔액)"
                value={`₩${(status.account_balance_krw ?? 0).toLocaleString()}`}
                sub="실제 게재 가능 금액"
              />
            </div>

            {/* Meta 선불 계정 정합 — 충전 한도 − 누적 지출 = 잔액 (충전 한도는 결제액의 부가세 제외분) */}
            {(status.account_spend_cap_krw ?? 0) > 0 && (
              <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-5">
                <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-3">
                  Meta 선불 계정 정합
                </p>
                <div className="flex flex-wrap items-end gap-x-3 gap-y-2 tabular-nums">
                  <div>
                    <p className="text-[11px] text-[#8B95A1]">충전 한도</p>
                    <p className="text-lg font-bold text-[#191F28] dark:text-[#F2F4F6]">
                      ₩{(status.account_spend_cap_krw ?? 0).toLocaleString()}
                    </p>
                  </div>
                  <span className="pb-1 text-lg text-[#8B95A1]">−</span>
                  <div>
                    <p className="text-[11px] text-[#8B95A1]">누적 지출</p>
                    <p className="text-lg font-bold text-[#191F28] dark:text-[#F2F4F6]">
                      ₩{(status.account_amount_spent_krw ?? 0).toLocaleString()}
                    </p>
                  </div>
                  <span className="pb-1 text-lg text-[#8B95A1]">=</span>
                  <div>
                    <p className="text-[11px] text-[#8B95A1]">선불 잔액</p>
                    <p className="text-lg font-extrabold text-[#3182F6]">
                      ₩{(status.account_balance_krw ?? 0).toLocaleString()}
                    </p>
                  </div>
                </div>
                <p className="mt-3 text-[11px] text-[#B0B8C1]">
                  충전 한도는 결제액의 <b>부가세(10%) 제외분</b>입니다 — 실제 결제액 ≈ 충전 한도 × 1.1 (예:
                  충전 한도 ₩{(status.account_spend_cap_krw ?? 0).toLocaleString()} → 결제 ≈ ₩
                  {Math.round((status.account_spend_cap_krw ?? 0) * 1.1).toLocaleString()}).
                </p>
              </div>
            )}

            {/* 일자별 계획 vs 실제 */}
            {daily.length > 0 && (
              <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-5">
                <div className="flex items-center justify-between mb-3">
                  <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">일자별 소진</p>
                  {dailyPlan > 0 && (
                    <span className="text-[11px] text-[#8B95A1]">일 계획 ₩{dailyPlan.toLocaleString()}</span>
                  )}
                </div>
                <div className="space-y-1.5">
                  {daily.map((d) => (
                    <div key={d.date} className="flex items-center gap-3">
                      <span className="w-14 text-[11px] text-[#8B95A1] tabular-nums">{d.date.slice(5)}</span>
                      <div className="flex-1 h-2 rounded-full bg-[#F2F4F6] dark:bg-[#2D3748] overflow-hidden">
                        <div
                          className={`h-full ${dailyPlan > 0 && d.spend_krw > dailyPlan ? 'bg-red-400' : 'bg-[#3182F6]'}`}
                          style={{ width: `${(d.spend_krw / maxDaily) * 100}%` }}
                        />
                      </div>
                      <span className="w-20 text-right text-xs tabular-nums text-[#191F28] dark:text-[#F2F4F6]">
                        ₩{d.spend_krw.toLocaleString()}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-5">
              <div className="flex items-center justify-between mb-3">
                <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">캠페인별 지출</p>
                <div className="flex rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] overflow-hidden text-[11px]">
                  {(
                    [
                      ['month', '이번 달'],
                      ['all', '전체 기간'],
                    ] as const
                  ).map(([key, label]) => (
                    <button
                      key={key}
                      onClick={() => setSpendScope(key)}
                      className={`px-2.5 py-1 ${
                        spendScope === key
                          ? 'bg-[#3182F6] text-white'
                          : 'text-[#8B95A1] hover:bg-[#F2F4F6] dark:hover:bg-[#2D3748]'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              {spendScope === 'all' && allTimeSpend == null ? (
                <p className="text-xs text-[#8B95A1] py-2">불러오는 중…</p>
              ) : spendRows.length === 0 ? (
                <p className="text-xs text-[#8B95A1] py-2">표시할 캠페인이 없어요.</p>
              ) : spendScope === 'month' && spendRows.every((c) => c.spend_krw === 0) ? (
                <p className="text-xs text-[#8B95A1] py-2">
                  이번 달 집행이 아직 없어요 — ‘전체 기간’으로 누적 지출을 볼 수 있어요.
                </p>
              ) : (
                <div className="grid gap-5 md:grid-cols-[220px_1fr] items-center">
                  {/* 지출 비중 도넛 — 실측 구성비(지출 0뿐이면 자체적으로 숨김) */}
                  <SpendDonut rows={spendRows} />
                  <div className="space-y-2.5">
                    {spendRows.map((c) => (
                      <div key={c.name} className="flex items-center gap-3">
                        <span className="w-32 truncate text-sm text-[#4E5968] dark:text-[#C9CED6]">{c.name}</span>
                        <div className="flex-1 h-2 rounded-full bg-[#F2F4F6] dark:bg-[#2D3748] overflow-hidden">
                          <div className="h-full bg-[#3182F6]" style={{ width: `${(c.spend_krw / maxSpend) * 100}%` }} />
                        </div>
                        {c.roas != null && (
                          <span className="w-16 text-right text-[11px] tabular-nums text-[#8B95A1]">
                            ROAS {c.roas.toFixed(1)}x
                          </span>
                        )}
                        <span className="w-24 text-right text-sm tabular-nums text-[#191F28] dark:text-[#F2F4F6]">
                          ₩{c.spend_krw.toLocaleString()}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* 예산 리밸런싱 제안 — 저효율→고효율 이동(적용은 승인 경로 재사용) */}
            <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-5">
              <p className="font-bold text-[#191F28] dark:text-[#F2F4F6] mb-1">
                예산 리밸런싱 제안
                <span className="ml-2 rounded-md bg-[#EBF3FF] px-1.5 py-0.5 text-[10px] font-semibold text-[#3182F6] dark:bg-[#1E3A5F] dark:text-[#7BB4F5]">
                  AI 제안
                </span>
              </p>
              <p className="text-xs text-[#8B95A1] mb-3">
                최근 7일 CPC를 비교해 저효율 캠페인의 일예산 20%를 고효율 쪽으로 옮기는 제안.
                적용해도 바로 집행되지 않고 기존 예산 변경 검증·승인 경로를 그대로 거칩니다.
              </p>
              {rebalance ? (
                <div className="rounded-xl bg-[#F9FAFB] dark:bg-[#232A36] px-4 py-3">
                  <p className="text-sm text-[#191F28] dark:text-[#F2F4F6]">
                    <b>{rebalance.from.name}</b>{' '}
                    <span className="tabular-nums text-[#8B95A1]">
                      (CPC ₩{rebalance.from.cpc_krw.toLocaleString()} · ₩
                      {rebalance.from.daily_budget_krw.toLocaleString()}→₩
                      {rebalance.from.after_krw.toLocaleString()})
                    </span>{' '}
                    → <b>{rebalance.to.name}</b>{' '}
                    <span className="tabular-nums text-[#8B95A1]">
                      (CPC ₩{rebalance.to.cpc_krw.toLocaleString()} · ₩
                      {rebalance.to.daily_budget_krw.toLocaleString()}→₩
                      {rebalance.to.after_krw.toLocaleString()})
                    </span>
                  </p>
                  <p className="mt-1 text-xs text-[#8B95A1]">{rebalance.reason}</p>
                  <div className="mt-2 flex justify-end">
                    <button
                      onClick={applyRebalance}
                      disabled={rebalanceBusy}
                      className="rounded-lg bg-[#3182F6] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#1B6EEB] disabled:opacity-40"
                    >
                      {rebalanceBusy
                        ? '적용 중…'
                        : `₩${rebalance.move_krw.toLocaleString()} 이동 적용`}
                    </button>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-[#B0B8C1]">{rebalanceNote ?? '제안을 불러오는 중…'}</p>
              )}
              {rebalanceMsg && (
                <p className="mt-2 text-xs text-[#4E5968] dark:text-[#9CA3AF]">{rebalanceMsg}</p>
              )}
            </div>

            {/* 월 목표 예산 설정 */}
            <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-5">
              <p className="font-bold text-[#191F28] dark:text-[#F2F4F6] mb-1">월 목표 예산 설정</p>
              <p className="text-xs text-[#8B95A1] mb-3">
                이번 달 광고에 쓸 목표 금액. 소진이 이 목표에 가까워지면 가드레일이 경고합니다.
                (실제 게재 가능액은 위 &lsquo;여력&rsquo; — Meta 선불 잔액)
              </p>
              {/* 월 매출 기반 권장 목표 계산기 — 벤치마크(매출의 5~15%, 표준 10%) */}
              <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
                <span className="text-[#8B95A1]">월 매출로 계산</span>
                <span className="inline-flex items-center gap-1">
                  <span className="text-[#8B95A1]">₩</span>
                  <input
                    type="number"
                    min={0}
                    step={1_000_000}
                    value={revenueInput || ''}
                    onChange={(e) => setRevenueInput(Number(e.target.value))}
                    placeholder="예: 30000000"
                    className="w-36 rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent px-2 py-1.5 tabular-nums text-[#191F28] dark:text-[#F2F4F6] outline-none focus:border-[#3182F6]"
                  />
                </span>
                {revenueInput > 0 && (
                  <>
                    <span className="text-[#4E5968] dark:text-[#9CA3AF] tabular-nums">
                      권장 ₩{Math.round(revenueInput * 0.05).toLocaleString()}~₩
                      {Math.round(revenueInput * 0.15).toLocaleString()} (매출의 5~15%) · 표준 10% =
                      ₩{Math.round(revenueInput * 0.1).toLocaleString()}
                    </span>
                    <button
                      onClick={() =>
                        setTargetInput(Math.round((revenueInput * 0.1) / 10_000) * 10_000)
                      }
                      className="rounded-lg border border-[#3182F6] px-2 py-1 font-semibold text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F]"
                    >
                      10% 적용
                    </button>
                  </>
                )}
              </div>
              <div className="flex items-center gap-2 max-w-md">
                <span className="text-sm text-[#8B95A1]">₩</span>
                <input
                  type="number"
                  min={0}
                  step={100_000}
                  value={targetInput}
                  onChange={(e) => setTargetInput(Number(e.target.value))}
                  className="flex-1 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent px-3 py-2 text-sm text-[#191F28] dark:text-[#F2F4F6] focus:border-[#3182F6] outline-none tabular-nums"
                />
                <button
                  onClick={applyTarget}
                  disabled={busy}
                  className="px-4 py-2 bg-[#3182F6] text-white text-sm font-medium rounded-lg hover:bg-[#1B6EEB] disabled:opacity-40 whitespace-nowrap"
                >
                  목표 설정
                </button>
              </div>
            </div>

            {ledger.length > 0 && (
              <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-5">
                <p className="font-bold text-[#191F28] dark:text-[#F2F4F6] mb-1">ClickMe 크레딧 내역</p>
                <p className="text-[11px] text-[#B0B8C1] mb-3">ClickMe 서비스 크레딧(광고비와 별개)</p>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
                    <thead className="border-b border-[#E5E8EB] text-[#8B95A1] dark:border-[#2D3748] text-xs">
                      <tr>
                        <th className="px-3 py-2 text-left font-semibold">일시</th>
                        <th className="px-3 py-2 text-left font-semibold">구분</th>
                        <th className="px-3 py-2 text-right font-semibold">금액</th>
                        <th className="px-3 py-2 text-right font-semibold">잔액</th>
                      </tr>
                    </thead>
                    <tbody className="text-[#191F28] dark:text-[#F2F4F6]">
                      {ledger
                        .slice()
                        .reverse()
                        .map((e) => {
                          const r = REASON[e.reason] ?? { label: e.reason, cls: '' };
                          return (
                            <tr
                              key={e.entry_id}
                              className="border-b border-[#F2F4F6] last:border-0 dark:border-[#252D3D]"
                            >
                              <td className="px-3 py-2 text-left text-[#4E5968] dark:text-[#9CA3AF]">
                                {formatKSTFull(e.created_at)}
                              </td>
                              <td className={`px-3 py-2 text-left font-medium ${r.cls}`}>{r.label}</td>
                              <td className="px-3 py-2 text-right tabular-nums">
                                {e.delta_krw > 0 ? '+' : ''}
                                {e.delta_krw.toLocaleString()}원
                              </td>
                              <td className="px-3 py-2 text-right tabular-nums text-[#8B95A1]">
                                ₩{e.balance_after_krw.toLocaleString()}
                              </td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        <p className="mt-6 text-[11px] text-[#B0B8C1]">
          월 목표 = 내가 정한 이번 달 예산 · 소진 = 이번 달 실 Meta 집행 · 여력 = Meta 선불 잔액 · 금액 KRW(부가세 별도)
        </p>
      </div>
  );
}
