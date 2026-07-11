// 챗 임베드 리밸런싱 적용 카드 — 확인 클릭 = 승인(HITL) → rebalance-commit 원자 1건 집행.
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { api, type RebalanceTransfer } from '@/lib/api';

type Phase = 'confirm' | 'running' | 'done';

export default function ChatRebalanceActionCard({ proposal }: { proposal: RebalanceTransfer }) {
  const [phase, setPhase] = useState<Phase>('confirm');
  const [ok, setOk] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setPhase('running');
    setError(null);
    try {
      const r = await api.management.rebalanceCommit({
        from_campaign_id: proposal.from.campaign_id,
        to_campaign_id: proposal.to.campaign_id,
        from_after_krw: proposal.from.after_krw,
        to_after_krw: proposal.to.after_krw,
        move_krw: proposal.move_krw,
        shown_from_before_krw: proposal.from.daily_budget_krw,
        shown_to_before_krw: proposal.to.daily_budget_krw,
      });
      const success = r.result.status === 'success';
      setOk(success);
      if (!success) setError(r.error_message ?? '리밸런싱을 적용하지 못했어요.');
    } catch (e) {
      setOk(false);
      setError(e instanceof Error ? e.message : '요청 중 문제가 발생했어요.');
    }
    setPhase('done');
  };

  if (phase === 'done') {
    return (
      <div className="mt-1 rounded-2xl border border-line p-4 max-w-md">
        {ok ? (
          <p className="font-bold text-ink">
            ✓ 리밸런싱 적용 완료 — ₩{proposal.move_krw.toLocaleString()} 이동
          </p>
        ) : (
          <>
            <p className="font-bold text-red-500">리밸런싱 적용 실패</p>
            <p className="mt-1 text-sm text-ink-tertiary">{error ?? '처리되지 않았어요.'}</p>
          </>
        )}
        <Link
          href="/manage/budget"
          className="mt-3 inline-block px-3 py-1.5 bg-primary text-primary-foreground text-xs font-medium rounded-lg hover:bg-primary-hover"
        >
          예산 관리로
        </Link>
      </div>
    );
  }

  return (
    <div className="mt-1 rounded-2xl border border-line p-4 max-w-md">
      <p className="font-bold text-ink mb-2">예산 리밸런싱 적용</p>
      <div className="rounded-xl bg-surface-1 px-4 py-3 text-sm text-ink">
        <p>
          <b>{proposal.from.name}</b>{' '}
          <span className="tabular-nums text-ink-tertiary">
            (₩{proposal.from.daily_budget_krw.toLocaleString()}→₩
            {proposal.from.after_krw.toLocaleString()})
          </span>{' '}
          → <b>{proposal.to.name}</b>{' '}
          <span className="tabular-nums text-ink-tertiary">
            (₩{proposal.to.daily_budget_krw.toLocaleString()}→₩
            {proposal.to.after_krw.toLocaleString()})
          </span>
        </p>
        <p className="mt-1 text-xs text-ink-tertiary">{proposal.reason}</p>
      </div>
      <p className="mt-2 text-xs text-ink-tertiary">
        총 일예산은 그대로예요 — 승인 1건으로 감액과 증액이 함께 집행되고, 증액 실패 시
        자동으로 원복을 시도해요.
      </p>
      <button
        onClick={run}
        disabled={phase !== 'confirm'}
        className="mt-3 px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary-hover disabled:opacity-40"
      >
        {phase === 'running'
          ? '적용 중…'
          : `₩${proposal.move_krw.toLocaleString()} 이동 적용`}
      </button>
      {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
    </div>
  );
}
