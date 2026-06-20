'use client';

import { useState } from 'react';
import Link from 'next/link';
import AppLayout from '@/components/AppLayout';
import { api } from '@/lib/api';
import { CampaignForm, type CampaignFormValues } from '@/components/manage/campaigns/CampaignForm';
import { CreateProposalPreview } from '@/components/manage/campaigns/CreateProposalPreview';
import type { Proposal, ActionResult } from '@/components/manage/types';

type Step = 'form' | 'preview' | 'done';

export default function Page() {
  const [step, setStep] = useState<Step>('form');
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [result, setResult] = useState<ActionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const approveAndExecute = async () => {
    if (!proposal) return;
    setBusy(true);
    setError(null);
    try {
      const a = (await api.management.approve(proposal, true)) as { approved_action: unknown };
      const { result: r } = (await api.management.execute(a.approved_action, proposal)) as {
        result: ActionResult;
      };
      setResult(r);
      setStep('done');
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
    setStep('form');
  };

  const success = result?.status === 'success';

  return (
    <AppLayout>
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        <div className="mb-6">
          <Link href="/manage/campaigns" className="text-sm text-[#8B95A1] hover:text-[#3182F6]">
            ← 캠페인 대시보드
          </Link>
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6] mt-1">새 캠페인 만들기</h1>
          <p className="text-sm text-[#8B95A1] mt-1">
            폼 → 제안 → 승인 → 생성 (Tier 3 · 사람 승인 · Mock 기반 데모)
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
                  안전을 위해 <b>PAUSED 상태</b>로 생성됩니다 · 실행 모드에 따라 검증(validate)·실생성(live) ·
                  실제 게재(과금)는 사람이 Ads Manager에서 직접 켜야 시작됩니다.
                </p>
              </>
            ) : (
              <>
                <h2 className="font-bold text-red-500 mb-2">생성 실패</h2>
                <p className="text-sm text-[#8B95A1]">
                  사유 {result?.failure_reason ?? '알 수 없음'} — 예산 한도·정책을 확인하세요.
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
    </AppLayout>
  );
}
