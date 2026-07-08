// 챗 임베드 예산 변경 — /budget-proposal 프리뷰(현재→변경·Tier)→/budget-commit 집행→결과.
'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ApiError, api } from '@/lib/api';
import type { CampaignSummary } from '@/components/manage/campaigns/types';
import type { Proposal, ActionResult } from '@/components/manage/types';

export type BudgetActionPayload = {
  action: 'increase_budget' | 'decrease_budget';
  campaign_id?: string;
  campaign_name?: string;
  new_daily_budget_krw?: number;
  pct?: number;
};

type PickItem = Pick<CampaignSummary, 'campaign_id' | 'name' | 'state' | 'daily_budget_krw'>;

const MIN_DAILY_BUDGET_KRW = 1521;

export default function ChatBudgetProposalCard({ action }: { action: BudgetActionPayload }) {
  const [campaignId, setCampaignId] = useState(action.campaign_id ?? '');
  const [before, setBefore] = useState<number | null>(null);
  const [picker, setPicker] = useState<PickItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [resolvedCampaign, setResolvedCampaign] = useState<PickItem | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [manualTarget, setManualTarget] = useState<number | null>(null);
  const [manualTargetForced, setManualTargetForced] = useState(false);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [drift, setDrift] = useState(false);
  const [result, setResult] = useState<ActionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isIncrease = action.action === 'increase_budget';

  // LLM이 준 campaign_id도 반드시 로그인 사용자의 캠페인 목록으로 재해석한다(정본 매칭).
  useEffect(() => {
    let alive = true;
    setCampaignId(action.campaign_id ?? '');
    setBefore(null);
    setPicker([]);
    setLoaded(false);
    setResolvedCampaign(null);
    setWarning(null);
    setManualTarget(null);
    setManualTargetForced(false);
    setProposal(null);
    setDrift(false);
    setResult(null);
    setError(null);

    api.management
      .campaigns()
      .then((r) => {
        if (!alive) return;
        const list = (r.campaigns ?? []).map((c) => ({
          campaign_id: c.campaign_id,
          name: c.name,
          state: c.state,
          daily_budget_krw: c.daily_budget_krw,
        }));
        setPicker(list);

        const canonical = action.campaign_id
          ? list.find((c) => c.campaign_id === action.campaign_id)
          : null;
        if (action.campaign_id && !canonical) {
          setCampaignId('');
          setResolvedCampaign(null);
          setWarning('지정한 캠페인을 찾을 수 없어 직접 선택해 주세요.');
        } else if (canonical) {
          setCampaignId(canonical.campaign_id);
          setResolvedCampaign(canonical);
          setBefore(canonical.daily_budget_krw);
          setWarning(null);
        }
        setLoaded(true);
      })
      .catch(() => {
        if (!alive) return;
        setPicker([]);
        setCampaignId('');
        setResolvedCampaign(null);
        setWarning(
          action.campaign_id ? '지정한 캠페인을 찾을 수 없어 직접 선택해 주세요.' : null,
        );
        setLoaded(true);
      });

    return () => {
      alive = false;
    };
  }, [action.action, action.campaign_id, action.new_daily_budget_krw, action.pct]);

  const onSelectCampaign = (nextCampaignId: string) => {
    const canonical = picker.find((c) => c.campaign_id === nextCampaignId) ?? null;
    setCampaignId(nextCampaignId);
    setResolvedCampaign(canonical);
    setBefore(canonical?.daily_budget_krw ?? null);
    setWarning(null);
    setManualTarget(null);
    setManualTargetForced(false);
    setProposal(null);
    setDrift(false);
    setError(null);
  };

  // 목표 예산 = 발화의 절대값 우선, 없으면 pct 환산, 둘 다 없으면 수동 입력값.
  const suggestedTarget =
    action.new_daily_budget_krw ??
    (before != null && action.pct != null ? Math.round(before * (1 + action.pct / 100)) : null);
  const target = manualTargetForced ? manualTarget : suggestedTarget ?? manualTarget;
  const needsManualTarget =
    !proposal && (manualTargetForced || (action.new_daily_budget_krw == null && action.pct == null));

  // 프리뷰 표시값 — proposal이 있으면 서버 정본(현재→변경)을 그대로 그린다.
  const showBefore = proposal ? proposal.budget_before_krw : before;
  const showTarget = proposal ? proposal.budget_after_krw : target;

  const review = async () => {
    if (!resolvedCampaign || target == null) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.management.budgetProposal(resolvedCampaign.campaign_id, {
        action: action.action,
        new_daily_budget_krw: target,
        shown_budget_before_krw: before ?? undefined,
      });
      setBefore(r.budget_before_krw);
      setDrift(r.drift);
      setProposal(r.proposal);
      setManualTargetForced(false);
    } catch (e) {
      // 검증 실패(범위·no-op·방향불일치)면 목표 입력으로 되돌려 다시 시도하게 한다.
      setManualTarget(target);
      setManualTargetForced(true);
      setProposal(null);
      setError(e instanceof Error ? e.message : '제안을 만들지 못했어요.');
    } finally {
      setBusy(false);
    }
  };

  const execute = async () => {
    if (!proposal || !resolvedCampaign) return;
    setBusy(true);
    setError(null);
    try {
      const resp = await api.management.budgetCommit(resolvedCampaign.campaign_id, {
        action: action.action,
        new_daily_budget_krw: proposal.budget_after_krw,
        shown_budget_before_krw: proposal.budget_before_krw,
      });
      setBefore(resp.budget_before_krw);
      setResult(resp.result);
      if (resp.error_message) setError(resp.error_message);
    } catch (e) {
      // 서버가 stale/검증 거부(409/422)면 프리뷰로 되돌리고 사유를 보여준다(집행 버튼 숨김).
      if (e instanceof ApiError && (e.status === 409 || e.status === 422)) {
        setProposal(null);
        setDrift(false);
        setError(e.message);
        return;
      }
      setError(e instanceof Error ? e.message : '집행에 실패했어요.');
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    const pending = result.status === 'pending_review';
    const ok = result.status === 'success' || pending;
    return (
      <div className="mt-1 rounded-2xl border border-line p-4 max-w-md">
        <p className={`font-bold ${ok ? 'text-ink' : 'text-red-500'}`}>
          {pending ? '검토 중' : ok ? '✓ 예산을 변경했어요' : '예산 변경 실패'}
        </p>
        {pending && <p className="mt-1 text-sm text-ink-tertiary">Meta 검토가 진행 중이에요.</p>}
        {!ok && (
          <p className="mt-1 text-sm text-ink-tertiary">
            {error ?? `사유 ${result.failure_reason ?? '알 수 없음'}`}
          </p>
        )}
        {ok && result.approval_id && (
          <p className="mt-1 text-[11px] text-ink-muted">승인 ID {result.approval_id}</p>
        )}
        <Link
          href="/manage/campaigns"
          className="mt-3 inline-block px-3 py-1.5 bg-primary text-primary-foreground text-xs font-medium rounded-lg hover:bg-primary-hover"
        >
          대시보드로
        </Link>
      </div>
    );
  }

  return (
    <div className="mt-1 rounded-2xl border border-line p-4 max-w-md">
      <p className="font-bold text-ink mb-2">
        예산 {isIncrease ? '증액' : '감액'}
      </p>

      {warning && (
        <p className="mb-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
          {warning}
        </p>
      )}

      {!resolvedCampaign && !proposal ? (
        <label className="mb-2 block">
          <span className="text-xs text-ink-tertiary">대상 캠페인</span>
          <select
            value={campaignId}
            onChange={(e) => onSelectCampaign(e.target.value)}
            className="mt-1 w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm"
          >
            <option value="">선택하세요</option>
            {picker.map((c) => (
              <option key={c.campaign_id} value={c.campaign_id}>
                {c.name} ({c.state})
              </option>
            ))}
          </select>
          {loaded && picker.length === 0 && (
            <span className="mt-1 block text-xs text-ink-tertiary">불러올 캠페인이 없어요.</span>
          )}
        </label>
      ) : (
        resolvedCampaign && (
          <div className="mb-2 text-sm text-ink-secondary">
            <p className="font-medium text-ink">
              {resolvedCampaign.name}
            </p>
            <p className="text-xs text-ink-tertiary">상태 {resolvedCampaign.state}</p>
          </div>
        )
      )}

      {needsManualTarget && (
        <label className="mb-2 block">
          <span className="text-xs text-ink-tertiary">목표 일 예산(원)</span>
          <input
            type="number"
            min={MIN_DAILY_BUDGET_KRW}
            value={manualTarget ?? ''}
            onChange={(e) => setManualTarget(e.target.value === '' ? null : Number(e.target.value))}
            placeholder="예: 50000"
            className="mt-1 w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm"
          />
        </label>
      )}

      {showBefore != null && showTarget != null ? (
        <div className="mb-2 text-sm text-ink-secondary">
          <p>
            일 예산 <b>{showBefore.toLocaleString()}원</b> →{' '}
            <b className="text-primary">{showTarget.toLocaleString()}원</b>
          </p>
          <span className="block text-[11px] text-ink-tertiary mt-0.5">
            7일 기준 예상 최대 지출 {((showTarget ?? 0) * 7).toLocaleString()}원
          </span>
          {isIncrease && (
            <span className="block text-[11px] text-amber-600 dark:text-amber-400 mt-0.5">
              예산을 늘리면 추가 지출이 발생할 수 있어요.
            </span>
          )}
          {drift && (
            <span className="block text-[11px] text-ink-tertiary mt-0.5">
              현재 예산이 갱신됐어요.
            </span>
          )}
        </div>
      ) : (
        <p className="text-xs text-ink-tertiary mb-2">캠페인과 목표 예산을 확인할 수 없어요.</p>
      )}

      {!proposal ? (
        <button
          onClick={review}
          disabled={busy || !resolvedCampaign || target == null}
          className="px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary-hover disabled:opacity-40"
        >
          {busy ? '준비 중…' : '검토·승인'}
        </button>
      ) : (
        <div className="flex gap-2">
          <button
            onClick={execute}
            disabled={busy || !resolvedCampaign}
            className="px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary-hover disabled:opacity-40"
          >
            {busy ? '집행 중…' : '집행'}
          </button>
          <button
            onClick={() => setProposal(null)}
            disabled={busy}
            className="px-4 py-2 border border-line text-sm rounded-lg disabled:opacity-40"
          >
            취소
          </button>
        </div>
      )}
      {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
    </div>
  );
}
