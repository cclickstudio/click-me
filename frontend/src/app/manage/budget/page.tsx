'use client';

import { useEffect, useState } from 'react';
import AppLayout from '@/components/AppLayout';
import { api } from '@/lib/api';
import { BudgetGauge } from '@/components/manage/budget/BudgetGauge';
import { OriginLegend, OriginTag } from '@/components/manage/ValueOrigin';
import type { BudgetDecision, BudgetStatus } from '@/components/manage/budget/types';

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

function Tile({
  label,
  value,
  sub,
  origin,
}: {
  label: string;
  value: string;
  sub?: string;
  origin?: 'setting' | 'computed';
}) {
  return (
    <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] px-4 py-3">
      <p className="text-xs text-[#8B95A1]">
        {label}
        {origin && <OriginTag origin={origin} />}
      </p>
      <p className="text-xl font-extrabold text-[#191F28] dark:text-[#F2F4F6] tabular-nums mt-1">{value}</p>
      {sub && <p className="text-[11px] text-[#B0B8C1] mt-0.5">{sub}</p>}
    </div>
  );
}

export default function Page() {
  const [status, setStatus] = useState<BudgetStatus | null>(null);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [targetInput, setTargetInput] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.management
      .budget()
      .then((b) => {
        if (!alive) return;
        setStatus(b);
        setTargetInput(b.monthly_target_krw ?? b.limit_krw);
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : '불러오기 실패'));
    api.billing
      .history()
      .then((r) => alive && setLedger(r.entries))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

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
  const maxSpend = status ? Math.max(...status.campaigns.map((c) => c.spend_krw), 1) : 1;

  // 런레이트(월말 예상) vs 목표
  const target = status?.monthly_target_krw ?? status?.limit_krw ?? 0;
  const projection = status?.projection_krw ?? status?.spent_krw ?? 0;
  const projPct = target > 0 ? Math.round((projection / target) * 100) : 0;
  const projOver = target > 0 && projection > target;

  // 일자별 계획선 — 월 목표 / 이번 달 일수
  const daysInMonth = status?.period
    ? new Date(Number(status.period.slice(0, 4)), Number(status.period.slice(5, 7)), 0).getDate()
    : 30;
  const dailyPlan = target > 0 ? Math.round(target / daysInMonth) : 0;
  const daily = status?.daily ?? [];
  const maxDaily = Math.max(...daily.map((d) => d.spend_krw), dailyPlan, 1);

  return (
    <AppLayout>
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">예산 관리</h1>
          <p className="text-sm text-[#8B95A1] mt-1">
            월 목표 예산 대비 이번 달 실 Meta 집행 페이싱 · 여력=Meta 선불 잔액 · 90/95/100% 가드레일
          </p>
        </div>

        {error && <p className="text-sm text-red-500 mb-4" role="alert">{error}</p>}

        {status && (
          <div className="space-y-4">
            {warn && (
              <div className={`rounded-2xl border px-4 py-3 text-sm ${warn.cls}`}>
                <b>{warn.label}</b> · {warn.msg}
              </div>
            )}

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
              />
            </div>

            <OriginLegend />
            <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
              <Tile label="월 목표" value={`₩${target.toLocaleString()}`} origin="setting" />
              <Tile label="이번 달 소진" value={`₩${status.spent_krw.toLocaleString()}`} />
              <Tile label="잔여" value={`₩${status.remaining_krw.toLocaleString()}`} origin="computed" />
              <Tile
                label="월 목표 소진율"
                value={`${(status.ratio * 100).toFixed(0)}%`}
                origin="computed"
              />
              <Tile
                label="크레딧 잔액 (집행 한도)"
                value={`₩${(status.credit_balance_krw ?? 0).toLocaleString()}`}
                sub="ClickMe 크레딧 — spend_cap"
              />
              <Tile
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
              <p className="font-bold text-[#191F28] dark:text-[#F2F4F6] mb-3">캠페인별 지출 (이번 달)</p>
              <div className="space-y-2.5">
                {status.campaigns.map((c) => (
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

            {/* 월 목표 예산 설정 */}
            <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-5">
              <p className="font-bold text-[#191F28] dark:text-[#F2F4F6] mb-1">월 목표 예산 설정</p>
              <p className="text-xs text-[#8B95A1] mb-3">
                이번 달 광고에 쓸 목표 금액. 소진이 이 목표에 가까워지면 가드레일이 경고합니다.
                (실제 게재 가능액은 위 &lsquo;여력&rsquo; — Meta 선불 잔액)
              </p>
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
                                {new Date(e.created_at).toLocaleString('ko-KR')}
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
    </AppLayout>
  );
}
