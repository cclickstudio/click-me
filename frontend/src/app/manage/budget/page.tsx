'use client';

import { useEffect, useState } from 'react';
import AppLayout from '@/components/AppLayout';
import { api } from '@/lib/api';
import { BudgetGauge } from '@/components/manage/budget/BudgetGauge';
import type { BudgetDecision, BudgetStatus } from '@/components/manage/budget/types';

const WARNING: Record<Exclude<BudgetDecision, 'allow'>, { label: string; msg: string; cls: string }> = {
  warn: {
    label: '경고',
    msg: '예산 90% 도달 — 추가 집행 시 주의하세요.',
    cls: 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-900/20 dark:text-amber-200 dark:border-amber-800',
  },
  escalate: {
    label: '자율 차단',
    msg: '95% 초과 — 추가 집행은 사용자 승인이 필요합니다.',
    cls: 'bg-red-50 text-red-800 border-red-200 dark:bg-red-900/20 dark:text-red-200 dark:border-red-800',
  },
  block: {
    label: '한도 초과',
    msg: '100% 초과 — 신규 집행이 차단됩니다.',
    cls: 'bg-red-100 text-red-900 border-red-300 dark:bg-red-900/30 dark:text-red-100 dark:border-red-700',
  },
};

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] px-4 py-3">
      <p className="text-xs text-[#8B95A1]">{label}</p>
      <p className="text-xl font-extrabold text-[#191F28] dark:text-[#F2F4F6] tabular-nums mt-1">{value}</p>
    </div>
  );
}

export default function Page() {
  const [status, setStatus] = useState<BudgetStatus | null>(null);
  const [limitInput, setLimitInput] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setBusy(true);
    api.management
      .budget()
      .then((b) => {
        if (!alive) return;
        setStatus(b);
        setLimitInput(b.limit_krw);
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : '불러오기 실패'))
      .finally(() => alive && setBusy(false));
    return () => {
      alive = false;
    };
  }, []);

  const applyLimit = async () => {
    setBusy(true);
    setError(null);
    try {
      const b = await api.management.setBudgetLimit(limitInput);
      setStatus(b);
    } catch (e) {
      setError(e instanceof Error ? e.message : '한도 변경 실패');
    } finally {
      setBusy(false);
    }
  };

  const warn = status && status.decision !== 'allow' ? WARNING[status.decision] : null;
  const maxSpend = status ? Math.max(...status.campaigns.map((c) => c.spend_krw), 1) : 1;

  return (
    <AppLayout>
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">예산 관리</h1>
          <p className="text-sm text-[#8B95A1] mt-1">한도 대비 소진·페이싱 + 90/95/100% 가드레일 (Mock 기반 데모)</p>
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
              <BudgetGauge
                spent={status.spent_krw}
                limit={status.limit_krw}
                ratio={status.ratio}
                decision={status.decision}
              />
            </div>

            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <Tile label="한도" value={`₩${status.limit_krw.toLocaleString()}`} />
              <Tile label="소진" value={`₩${status.spent_krw.toLocaleString()}`} />
              <Tile label="잔여" value={`₩${status.remaining_krw.toLocaleString()}`} />
              <Tile label="소진율" value={`${(status.ratio * 100).toFixed(0)}%`} />
            </div>

            <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-5">
              <p className="font-bold text-[#191F28] dark:text-[#F2F4F6] mb-3">캠페인별 지출</p>
              <div className="space-y-2.5">
                {status.campaigns.map((c) => (
                  <div key={c.name} className="flex items-center gap-3">
                    <span className="w-32 truncate text-sm text-[#4E5968] dark:text-[#C9CED6]">{c.name}</span>
                    <div className="flex-1 h-2 rounded-full bg-[#F2F4F6] dark:bg-[#2D3748] overflow-hidden">
                      <div className="h-full bg-[#3182F6]" style={{ width: `${(c.spend_krw / maxSpend) * 100}%` }} />
                    </div>
                    <span className="w-24 text-right text-sm tabular-nums text-[#191F28] dark:text-[#F2F4F6]">
                      ₩{c.spend_krw.toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-5">
              <p className="font-bold text-[#191F28] dark:text-[#F2F4F6] mb-1">한도 설정</p>
              <p className="text-xs text-[#8B95A1] mb-3">한도를 바꾸면 경고 레벨이 즉시 반영됩니다.</p>
              <div className="flex items-center gap-2 max-w-md">
                <span className="text-sm text-[#8B95A1]">₩</span>
                <input
                  type="number"
                  min={0}
                  step={100_000}
                  value={limitInput}
                  onChange={(e) => setLimitInput(Number(e.target.value))}
                  className="flex-1 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent px-3 py-2 text-sm text-[#191F28] dark:text-[#F2F4F6] focus:border-[#3182F6] outline-none tabular-nums"
                />
                <button
                  onClick={applyLimit}
                  disabled={busy}
                  className="px-4 py-2 bg-[#3182F6] text-white text-sm font-medium rounded-lg hover:bg-[#1B6EEB] disabled:opacity-40 whitespace-nowrap"
                >
                  한도 변경
                </button>
              </div>
            </div>
          </div>
        )}

        <p className="mt-6 text-[11px] text-[#B0B8C1]">
          ⚠ Mock 기반 데모 · 소진은 캠페인 합산 추정 · 하드캡=내부 권한 한도(플랫폼 절대상한 아님) · 금액 KRW
        </p>
      </div>
    </AppLayout>
  );
}
