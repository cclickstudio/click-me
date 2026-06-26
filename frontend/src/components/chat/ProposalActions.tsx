// proposal 미리보기 카드의 안전 버튼 흐름 — finalize→approve/execute. 새 UX 표면 없음(필수 상태만).
'use client';
import { useState } from 'react';
import {
  decideProposal,
  finalizeProposal,
  newIdempotencyKey,
  type FinalizeResult,
} from '@/lib/managementActions';
import type { ChatCard } from '@/lib/chatCard';

type Props = {
  previewId?: string;
  campaignId: string;
  threadId?: string;
  shownBudgetAfterKrw?: number;
  onResult: (card: ChatCard) => void; // 결과 카드로 교체
};

export default function ProposalActions({
  previewId,
  campaignId,
  threadId,
  shownBudgetAfterKrw,
  onResult,
}: Props) {
  const [phase, setPhase] = useState<
    'preview' | 'finalizing' | 'finalized' | 'deciding'
  >('preview');
  const [fin, setFin] = useState<FinalizeResult | null>(null);
  const [driftAck, setDriftAck] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [idemKey, setIdemKey] = useState('');

  async function onReview() {
    setPhase('finalizing');
    setErr(null);
    try {
      const r = await finalizeProposal({
        previewId,
        campaignId,
        threadId,
        shownBudgetAfterKrw,
      });
      if (r.status !== 'finalized') {
        setErr(r.reason ?? '진단 결과가 없어요.');
        setPhase('preview');
        return;
      }
      setFin(r);
      setIdemKey(newIdempotencyKey()); // 이 클릭의 의도 키 — 재시도에 동일 사용
      setDriftAck(!r.drift);
      setPhase('finalized');
    } catch {
      setErr('요청 중 문제가 발생했어요.');
      setPhase('preview');
    }
  }

  async function onDecide(decision: 'approve' | 'reject') {
    if (!fin?.proposal_id) return;
    setPhase('deciding');
    setErr(null);
    try {
      const card = await decideProposal({
        proposalId: fin.proposal_id,
        decision,
        idempotencyKey: idemKey, // 네트워크 재시도는 동일 key(새 클릭이 아니라 같은 클릭의 재시도)
        threadId,
      });
      onResult(card);
    } catch {
      setErr('집행 요청 중 문제가 발생했어요.');
      setPhase('finalized');
    }
  }

  if (phase === 'preview' || phase === 'finalizing') {
    return (
      <div className='mt-2'>
        <button
          disabled={phase === 'finalizing'}
          onClick={onReview}
          className='px-3 py-1.5 text-xs rounded-md bg-[#3182F6] text-white disabled:opacity-50'>
          {phase === 'finalizing' ? '준비 중…' : '검토·승인'}
        </button>
        {err && <p className='text-xs text-[#DC2626] mt-1'>{err}</p>}
      </div>
    );
  }

  // finalized / deciding
  if (fin?.requires_external_approval) {
    return (
      <p className='mt-2 text-xs text-[#B45309]'>
        정식 승인 화면에서 처리해야 하는 제안이에요.
      </p>
    );
  }
  const expired = fin?.expires_at
    ? new Date(fin.expires_at).getTime() < Date.now()
    : false;
  return (
    <div className='mt-2 space-y-1'>
      {fin?.drift && !driftAck && (
        <div className='text-xs text-[#B45309]'>
          값이 갱신됐어요(집행 예산 {fin?.budget_after_krw?.toLocaleString()}
          원).
          <button onClick={() => setDriftAck(true)} className='ml-1 underline'>
            갱신값 확인
          </button>
        </div>
      )}
      <div className='flex gap-2'>
        <button
          disabled={phase === 'deciding' || expired || !driftAck}
          onClick={() => onDecide('approve')}
          className='px-3 py-1.5 text-xs rounded-md bg-[#3182F6] text-white disabled:opacity-50'>
          {expired ? '만료됨' : phase === 'deciding' ? '집행 중…' : '집행'}
        </button>
        <button
          disabled={phase === 'deciding'}
          onClick={() => onDecide('reject')}
          className='px-3 py-1.5 text-xs rounded-md border border-[#E5E8EB] text-[#4E5968] disabled:opacity-50'>
          거절
        </button>
      </div>
      {expired && (
        <p className='text-xs text-[#8B95A1]'>
          만료됐어요. 다시 검토를 요청해 주세요.
        </p>
      )}
      {err && <p className='text-xs text-[#DC2626]'>{err}</p>}
    </div>
  );
}
