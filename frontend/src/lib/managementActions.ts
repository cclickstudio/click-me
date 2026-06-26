// 챗 매니지먼트 집행 API — finalize(정본 승격)·decision(approve/reject). 정본 본문은 서버에만.
import { API_BASE } from './api';
import type { ChatCard } from './chatCard';

export type FinalizeResult = {
  status: 'finalized' | 'unavailable' | 'no_anomaly';
  proposal_id?: string;
  action_type?: string;
  tier?: string;
  requires_external_approval?: boolean;
  budget_before_krw?: number;
  budget_after_krw?: number;
  summary?: string;
  expires_at?: string;
  drift?: boolean;
  reason?: string;
};

export async function finalizeProposal(input: {
  previewId?: string;
  campaignId: string;
  threadId?: string;
  shownBudgetAfterKrw?: number;
}): Promise<FinalizeResult> {
  const res = await fetch(`${API_BASE}/api/chat/management/proposals/finalize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      preview_id: input.previewId,
      campaign_id: input.campaignId,
      thread_id: input.threadId,
      shown_budget_after_krw: input.shownBudgetAfterKrw,
    }),
  });
  if (!res.ok) throw new Error(`finalize 실패 ${res.status}`);
  return res.json();
}

// idempotency_key: 한 클릭당 1개 생성. 네트워크 재시도는 동일 key(같은 의도),
// 사용자가 새로 다시 누르는 새 의도는 새 key.
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

export async function decideProposal(input: {
  proposalId: string;
  decision: 'approve' | 'reject';
  idempotencyKey: string;
  threadId?: string;
}): Promise<ChatCard> {
  const res = await fetch(
    `${API_BASE}/api/chat/management/proposals/${input.proposalId}/decision`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        decision: input.decision,
        idempotency_key: input.idempotencyKey,
        thread_id: input.threadId,
      }),
    },
  );
  if (!res.ok) throw new Error(`decision 실패 ${res.status}`);
  return res.json();
}
