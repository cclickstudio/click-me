// 챗 임베드 캠페인 상태 조치 — 확인(+캠페인 선택기·실과금)→기존 pause/activate 호출→결과.
'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { CampaignSummary } from '@/components/manage/campaigns/types';

export type CampaignActionPayload = {
  action: 'pause' | 'activate';
  campaign_id?: string;
  campaign_name?: string;
};

type Phase = 'confirm' | 'running' | 'done';
type PickItem = Pick<CampaignSummary, 'campaign_id' | 'name' | 'state' | 'daily_budget_krw'>;

const LABEL: Record<CampaignActionPayload['action'], string> = {
  pause: '일시중지',
  activate: '게재 시작',
};

export default function ChatCampaignActionCard({ action }: { action: CampaignActionPayload }) {
  const [phase, setPhase] = useState<Phase>('confirm');
  const [campaignId, setCampaignId] = useState(action.campaign_id ?? '');
  const [picker, setPicker] = useState<PickItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [resolvedCampaign, setResolvedCampaign] = useState<PickItem | null>(null);
  const [ackBilling, setAckBilling] = useState(false); // activate 실과금 확인
  const [ok, setOk] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);

  // LLM이 준 campaign_id도 반드시 로그인 사용자의 캠페인 목록으로 재해석한다.
  useEffect(() => {
    let alive = true;
    setCampaignId(action.campaign_id ?? '');
    setResolvedCampaign(null);
    setWarning(null);
    setLoaded(false);
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
  }, [action.campaign_id]);

  const needsAck = action.action === 'activate';
  const commitKrw = resolvedCampaign?.daily_budget_krw;
  const canRun =
    !!campaignId &&
    !!resolvedCampaign &&
    (!needsAck || (ackBilling && commitKrw != null)) &&
    phase === 'confirm';

  const onSelectCampaign = (nextCampaignId: string) => {
    setCampaignId(nextCampaignId);
    setResolvedCampaign(picker.find((c) => c.campaign_id === nextCampaignId) ?? null);
    setWarning(null);
  };

  const run = async () => {
    if (!campaignId || !resolvedCampaign) return;
    setPhase('running');
    setError(null);
    try {
      if (action.action === 'pause') {
        const r = (await api.management.pause(campaignId)) as { paused: boolean; error_message?: string };
        setOk(r.paused);
        if (!r.paused && r.error_message) setError(r.error_message);
      } else {
        if (commitKrw == null) {
          setOk(false);
          setError('집행 상한을 확인할 수 없어 게재를 시작하지 않았어요.');
          setPhase('done');
          return;
        }
        const r = (await api.management.activate(campaignId, commitKrw)) as {
          serving: boolean;
          causes?: { code: string; message: string }[];
        };
        setOk(r.serving);
        if (!r.serving) setError((r.causes ?? []).map((c) => c.message).join(' / ') || '게재를 시작하지 못했어요.');
      }
      setPhase('done');
    } catch (e) {
      setError(e instanceof Error ? e.message : '요청 중 문제가 발생했어요.');
      setPhase('done');
    }
  };

  if (phase === 'done') {
    return (
      <div className="mt-1 rounded-2xl border border-line p-4 max-w-md">
        {ok ? (
          <p className="font-bold text-ink">
            ✓ {LABEL[action.action]} 완료
          </p>
        ) : (
          <>
            <p className="font-bold text-red-500">{LABEL[action.action]} 실패</p>
            <p className="mt-1 text-sm text-ink-tertiary">{error ?? '처리되지 않았어요.'}</p>
          </>
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
      <p className="font-bold text-ink mb-2">캠페인 {LABEL[action.action]}</p>

      {warning && (
        <p className="mb-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
          {warning}
        </p>
      )}

      {!resolvedCampaign ? (
        <label className="block mb-2">
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
        <div className="mb-2 text-sm text-ink-secondary">
          <p className="font-medium text-ink">{resolvedCampaign.name}</p>
          <p className="text-xs text-ink-tertiary">
            상태 {resolvedCampaign.state}
            {needsAck && commitKrw != null ? ` · 집행 상한 ₩${commitKrw.toLocaleString()}` : ''}
          </p>
        </div>
      )}

      {needsAck && (
        <label className="flex items-start gap-2 text-xs text-ink-secondary mb-2">
          <input type="checkbox" checked={ackBilling} onChange={(e) => setAckBilling(e.target.checked)} className="mt-0.5" />
          <span>이 작업은 지금부터 실제 과금이 시작됩니다 — 이해했습니다.</span>
        </label>
      )}

      <button
        onClick={run}
        disabled={!canRun}
        className="px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary-hover disabled:opacity-40"
      >
        {phase === 'running' ? '처리 중…' : LABEL[action.action]}
      </button>
      {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
    </div>
  );
}
