'use client';

import { useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { CampaignForm, type CampaignFormValues } from '@/components/manage/campaigns/CampaignForm';
import { CreateProposalPreview } from '@/components/manage/campaigns/CreateProposalPreview';
import type { Proposal, ActionResult } from '@/components/manage/types';
import type { ActivateResponse } from '@/lib/api';
import { setPendingActivation } from '@/lib/pendingActivation';

type Step = 'form' | 'preview' | 'done';

export default function Page() {
  const [step, setStep] = useState<Step>('form');
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [result, setResult] = useState<ActionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null); // Meta 거부 사용자용 메시지
  const [activating, setActivating] = useState(false);
  const [activateResult, setActivateResult] = useState<ActivateResponse | null>(null);
  const [adSkipped, setAdSkipped] = useState(false);

  const createProposal = async (v: CampaignFormValues) => {
    setBusy(true);
    setError(null);
    try {
      const { proposal: p } = await api.management.createCampaignProposal(v);
      setProposal(p);
      setStep('preview');
    } catch (e) {
      setError(e instanceof Error ? e.message : '제안 생성 실패');
    } finally {
      setBusy(false);
    }
  };

  // 게재 활성화 — Meta 선불 잔액 부족이면 원인(causes)만 표시(충전은 Meta Ads Manager).
  const runActivate = async (campaignId: string, commit?: number) => {
    setActivating(true);
    setError(null);
    try {
      const resp = await api.management.activate(campaignId, commit);
      setActivateResult(resp);
    } catch (e) {
      setError(e instanceof Error ? e.message : '게재 시작 실패');
    } finally {
      setActivating(false);
    }
  };

  const approveAndExecute = async () => {
    if (!proposal) return;
    setBusy(true);
    setError(null);
    setMetaError(null);
    try {
      const a = (await api.management.approve(proposal, true)) as { approved_action: unknown };
      const resp = (await api.management.execute(a.approved_action, proposal)) as {
        result: ActionResult;
        error_message?: string;
      };
      setResult(resp.result);
      if (resp.error_message) setMetaError(resp.error_message); // Meta 거부 사유 표시
      // 생성(PAUSED) 성공 + LIVE(Meta id 존재)면 곧바로 게재 시도 → 부족하면 충전 페이지로.
      const metaId = resp.result?.platform_response_snapshot?.campaign_meta_id;
      const adSkippedFlag = resp.result?.platform_response_snapshot?.ad_creation_skipped === true;
      setAdSkipped(adSkippedFlag);
      setStep('done');
      if (resp.result?.status === 'success' && metaId && !adSkippedFlag) {
        await runActivate(metaId, proposal.max_total_spend_krw);
      }
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
    setMetaError(null);
    setActivateResult(null);
    setAdSkipped(false);
    setStep('form');
  };

  const success = result?.status === 'success';
  // LIVE 생성 시에만 Meta 캠페인 id가 잡힌다(목/검증 모드는 없음 → 게재 불가).
  const metaCampaignId = result?.platform_response_snapshot?.campaign_meta_id;
  const commitKrw = proposal?.max_total_spend_krw;

  const startDelivery = async () => {
    if (!metaCampaignId) return;
    if (
      !window.confirm(
        `게재를 시작하면 광고가 실제로 노출되고, 집행분만큼 선불 잔액에서 차감됩니다.\n이 캠페인 충전 한도: ${commitKrw?.toLocaleString() ?? '-'}원\n계속할까요?`,
      )
    )
      return;
    await runActivate(metaCampaignId, commitKrw);
  };

  return (
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        <div className="mb-6">
          <Link href="/manage/campaigns" className="text-sm text-[#8B95A1] hover:text-[#3182F6]">
            ← 캠페인 대시보드
          </Link>
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6] mt-1">새 캠페인 만들기</h1>
          <p className="text-sm text-[#8B95A1] mt-1">
            폼 → 제안 → 승인 → 생성 (Tier 3 · 사람 승인 · 생성은 PAUSED, 게재는 직접)
          </p>
        </div>

        {step === 'form' && <CampaignForm onSubmit={createProposal} busy={busy} />}

        {step === 'preview' && proposal && (
          <CreateProposalPreview
            proposal={proposal}
            onApprove={approveAndExecute}
            onCancel={reset}
            busy={busy}
          />
        )}

        {step === 'done' && (
          <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-6 max-w-xl">
            {success ? (
              <>
                <div className="flex items-center gap-2 mb-2">
                  <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300 text-sm font-bold">
                    ✓
                  </span>
                  <h2 className="font-bold text-[#191F28] dark:text-[#F2F4F6]">캠페인 생성됨 (PAUSED)</h2>
                </div>
                <p className="text-sm text-[#8B95A1]">
                  생성 직후 <b>자동으로 게재를 시작</b>합니다. 게재에는 두 가지가 필요해요 —
                  <b>예산 한도(ClickMe 크레딧)</b>와 <b>실광고비(Meta 선불 잔액)</b>. 부족한 쪽을
                  채우면 게재가 이어집니다(크레딧만큼 집행 상한 적용).
                </p>

                {activating && (
                  <p className="mt-3 text-sm text-[#8B95A1]">게재 시작 중…</p>
                )}

                {/* 게재 미시작(자동 시도 실패 등) 시의 수동 재시도 — 잔액 부족이면 충전 페이지로 이동 */}
                {!activating && !activateResult && (
                  <div className="mt-4">
                    {adSkipped ? (
                      <p className="text-xs text-[#8B95A1]">
                        광고 소재가 없어 게재할 수 없습니다. Meta Ads Manager에서 소재를 추가한 뒤
                        게재하세요.
                      </p>
                    ) : metaCampaignId ? (
                      <button
                        onClick={startDelivery}
                        disabled={activating}
                        className="px-4 py-2 bg-[#191F28] text-white text-sm font-semibold rounded-lg hover:bg-black disabled:opacity-50"
                      >
                        게재 다시 시도
                      </button>
                    ) : (
                      <p className="text-xs text-[#8B95A1]">
                        실모드(live)에서 생성된 캠페인만 앱에서 게재를 시작할 수 있습니다.
                      </p>
                    )}
                  </div>
                )}

                {/* 게재 시작 결과 */}
                {activateResult && activateResult.serving && (
                  <div className="mt-4 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 p-3">
                    <p className="text-sm font-semibold text-green-700 dark:text-green-300">
                      게재가 시작되었습니다.
                    </p>
                    <p className="text-xs text-green-600 dark:text-green-400 mt-1">
                      충전액 {activateResult.commit_krw.toLocaleString()}원까지 집행되며 소진되면 자동
                      종료됩니다. 현재 선불 잔액 {activateResult.balance_krw.toLocaleString()}원.
                    </p>
                  </div>
                )}
                {activateResult && !activateResult.serving && (
                  <div className="mt-4 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 p-3">
                    <p className="text-sm font-semibold text-amber-700 dark:text-amber-300">
                      게재를 시작하지 못했습니다.
                    </p>
                    <ul className="mt-1 space-y-1">
                      {activateResult.causes.map((c) => (
                        <li key={c.code} className="text-xs text-amber-700 dark:text-amber-300">
                          • {c.message}
                        </li>
                      ))}
                    </ul>
                    {/* 예산 한도(크레딧) 부족 → 인앱 충전(/payment), 충전 후 게재 자동 재개 */}
                    {activateResult.causes.some((c) => c.code === 'INSUFFICIENT_CREDIT') && (
                      <Link
                        href="/payment"
                        onClick={() =>
                          metaCampaignId &&
                          setPendingActivation({
                            campaignId: metaCampaignId,
                            commit: commitKrw ?? 0,
                          })
                        }
                        className="inline-block mt-2 mr-2 px-3 py-1.5 bg-[#3182F6] text-white text-xs font-medium rounded-lg hover:bg-[#1B6EEB]"
                      >
                        📊 예산 한도(크레딧) 충전하기
                      </Link>
                    )}
                    {/* 실광고비(Meta 선불) 부족 → Meta Ads Manager에서 충전(외부) */}
                    {activateResult.causes.some((c) => c.code === 'INSUFFICIENT_META_BALANCE') && (
                      <a
                        href="https://business.facebook.com/billing_hub/accounts"
                        target="_blank"
                        rel="noreferrer"
                        className="inline-block mt-2 px-3 py-1.5 bg-[#191F28] text-white text-xs font-medium rounded-lg hover:bg-black"
                      >
                        💳 실광고비(Meta 선불) 충전 — Ads Manager
                      </a>
                    )}
                  </div>
                )}
              </>
            ) : (
              <>
                <h2 className="font-bold text-red-500 mb-2">생성 실패</h2>
                {metaError && (
                  <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-3 mb-3">
                    <p className="text-xs font-semibold text-red-700 dark:text-red-300">Meta 거부 사유</p>
                    <p className="text-sm text-red-600 dark:text-red-400 mt-1 leading-relaxed">{metaError}</p>
                  </div>
                )}
                <p className="text-sm text-[#8B95A1]">
                  사유 코드 {result?.failure_reason ?? '알 수 없음'}
                  {!metaError && ' — 예산 한도·일정(최소 24h)·정책을 확인하세요.'}
                </p>
              </>
            )}
            <div className="flex items-center gap-2 mt-5">
              <Link
                href="/manage/campaigns"
                className="px-4 py-2 bg-[#3182F6] text-white text-sm font-medium rounded-lg hover:bg-[#1B6EEB]"
              >
                대시보드로
              </Link>
              <button
                onClick={reset}
                className="px-4 py-2 text-sm font-medium rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] text-[#4E5968] dark:text-[#9CA3AF]"
              >
                또 만들기
              </button>
            </div>
          </div>
        )}

        {error && (
          <p className="mt-4 text-sm text-red-500" role="alert">
            {error}
          </p>
        )}
      </div>
  );
}
