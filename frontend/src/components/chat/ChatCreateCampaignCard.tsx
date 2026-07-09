// 챗 카드에 임베드하는 신규 캠페인 생성 플로우 — 폼→프리뷰→승인·집행→결과. 정식 엔드포인트 재사용.
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { CampaignForm, type CampaignFormValues, type CampaignPrefill } from '@/components/manage/campaigns/CampaignForm';
import { CreateProposalPreview } from '@/components/manage/campaigns/CreateProposalPreview';
import type { Proposal, ActionResult } from '@/components/manage/types';

type Phase = 'form' | 'preview' | 'done';

export default function ChatCreateCampaignCard({ prefill }: { prefill?: CampaignPrefill }) {
  const [phase, setPhase] = useState<Phase>('form');
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [result, setResult] = useState<ActionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 폼 제출 → 정식 /create-proposal 로 제안 생성(아직 미집행).
  const createProposal = async (v: CampaignFormValues) => {
    setBusy(true);
    setError(null);
    try {
      const { proposal: p } = await api.management.createCampaignProposal(v);
      setProposal(p);
      setPhase('preview');
    } catch (e) {
      setError(e instanceof Error ? e.message : '제안 생성 실패');
    } finally {
      setBusy(false);
    }
  };

  // 프리뷰 승인 → 정식 /approve + /execute (사람 승인 게이트). 생성은 PAUSED 까지.
  const approveAndExecute = async () => {
    if (!proposal) return;
    setBusy(true);
    setError(null);
    try {
      const a = (await api.management.approve(proposal, true)) as { approved_action: unknown };
      const resp = (await api.management.execute(a.approved_action, proposal)) as {
        result: ActionResult;
        error_message?: string;
      };
      setResult(resp.result);
      if (resp.error_message) setError(resp.error_message); // Meta 거부 사유 등
      setPhase('done');
    } catch (e) {
      setError(e instanceof Error ? e.message : '승인·생성 실패');
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setProposal(null);
    setResult(null);
    setError(null);
    setPhase('form');
  };

  if (phase === 'form') {
    return (
      <div className="mt-1">
        <CampaignForm onSubmit={createProposal} busy={busy} initial={prefill} />
        {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
      </div>
    );
  }

  if (phase === 'preview' && proposal) {
    return (
      <div className="mt-1">
        <CreateProposalPreview
          proposal={proposal}
          onApprove={approveAndExecute}
          onCancel={reset}
          busy={busy}
        />
        {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
      </div>
    );
  }

  // done — ResultStatus: success(즉시) | pending_review(Meta 심사 중) 둘 다 "정상 처리". 나머지는 실패.
  const status = result?.status;
  const ok = status === 'success' || status === 'pending_review';
  return (
    <div className="mt-1 rounded-2xl border border-line p-4 max-w-xl">
      {ok ? (
        <>
          <p className="font-bold text-ink">
            {status === 'pending_review' ? '⏳ 캠페인 제출됨 (심사 중)' : '✓ 캠페인 생성됨 (PAUSED)'}
          </p>
          <p className="mt-1 text-sm text-ink-tertiary">
            {status === 'pending_review'
              ? 'Meta 심사가 끝나면 게재할 수 있어요.'
              : '대시보드에서 게재를 시작할 수 있어요.'}
          </p>
          {result?.approval_id && (
            <p className="mt-1 text-[11px] text-ink-muted">승인 ID: {result.approval_id}</p>
          )}
        </>
      ) : (
        <>
          <p className="font-bold text-red-500">생성 실패</p>
          <p className="mt-1 text-sm text-ink-tertiary">
            {error ?? `사유 코드 ${result?.failure_reason ?? '알 수 없음'}`}
          </p>
        </>
      )}
      <div className="mt-3 flex gap-2">
        <Link
          href="/manage/campaigns"
          className="px-3 py-1.5 bg-primary text-primary-foreground text-xs font-medium rounded-lg hover:bg-primary-hover"
        >
          대시보드로
        </Link>
        <button
          onClick={reset}
          className="px-3 py-1.5 text-xs font-medium rounded-lg border border-line text-ink-secondary"
        >
          다시 만들기
        </button>
      </div>
    </div>
  );
}
