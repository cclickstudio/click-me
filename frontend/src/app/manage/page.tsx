'use client';

import { useState } from 'react';
import AppLayout from '@/components/AppLayout';
import { api } from '@/lib/api';
import { AZone } from '@/components/manage/AZone';
import { BZone } from '@/components/manage/BZone';
import { ApprovalBridge } from '@/components/manage/ApprovalBridge';
import { AuditTimeline } from '@/components/manage/AuditTimeline';
import { KpiStrip } from '@/components/manage/KpiStrip';
import type { ActionResult, AuditEvent, RunResult, ViewMode } from '@/components/manage/types';

const FAULTS = ['bid_loss', 'review_rejected', 'none'];

export default function Page() {
  const [mode, setMode] = useState<ViewMode>('user');
  const [fault, setFault] = useState('bid_loss');
  const [run, setRun] = useState<RunResult | null>(null);
  const [result, setResult] = useState<ActionResult | null>(null);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [decided, setDecided] = useState<'approved' | 'rejected' | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    setAudit([]);
    setDecided(null);
    try {
      const r = (await api.management.run(fault)) as RunResult;
      if (r.diagnosis) {
        const { proposal } = (await api.management.regenerate(r.diagnosis)) as {
          proposal: RunResult['proposal'];
        };
        r.proposal = proposal;
      }
      setRun(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : '실행 실패');
    } finally {
      setBusy(false);
    }
  };

  const approve = async () => {
    if (!run?.proposal) return;
    setBusy(true);
    setError(null);
    try {
      const a = (await api.management.approve(run.proposal, true)) as {
        approved_action: { approval_id: string };
      };
      setDecided('approved');
      const { result: res } = (await api.management.execute(a.approved_action, run.proposal)) as {
        result: ActionResult;
      };
      setResult(res);
      const { events } = (await api.management.audit(a.approved_action.approval_id)) as {
        events: AuditEvent[];
      };
      setAudit(events);
    } catch (e) {
      setError(e instanceof Error ? e.message : '승인·실행 실패');
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    if (!run?.proposal) return;
    await api.management.approve(run.proposal, false);
    setDecided('rejected');
  };

  return (
    <AppLayout>
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">광고 매니지먼트</h1>
              <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                시연
              </span>
            </div>
            <p className="text-sm text-[#8B95A1] mt-1">
              이상 감지·진단·처방 시연 · 주입한 고장 시나리오 기준 (실데이터 아님)
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] overflow-hidden text-sm">
              <button
                onClick={() => setMode('user')}
                className={`px-3 py-1.5 ${mode === 'user' ? 'bg-[#3182F6] text-white' : 'text-[#8B95A1]'}`}
              >
                사용자 보기
              </button>
              <button
                onClick={() => setMode('arch')}
                className={`px-3 py-1.5 ${mode === 'arch' ? 'bg-[#3182F6] text-white' : 'text-[#8B95A1]'}`}
              >
                아키텍처 보기
              </button>
            </div>
            <span className="text-[11px] text-[#8B95A1]">고장 시나리오</span>
            <select
              value={fault}
              onChange={(e) => setFault(e.target.value)}
              className="text-sm px-2 py-1.5 rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent"
            >
              {FAULTS.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
            <button
              onClick={start}
              disabled={busy}
              className="px-4 py-2 bg-[#3182F6] text-white text-sm font-medium rounded-lg hover:bg-[#1B6EEB] disabled:opacity-40"
            >
              {busy ? '실행 중…' : '▶ 데모 실행'}
            </button>
          </div>
        </div>

        <KpiStrip run={run} />

        {run ? (
          <>
            <div className="flex flex-col lg:flex-row gap-4 items-stretch">
              <AZone run={run} mode={mode} />
              <BZone proposal={run.proposal} result={result} mode={mode} />
            </div>
            <ApprovalBridge run={run} decided={decided} onApprove={approve} onReject={reject} mode={mode} />
            <AuditTimeline events={audit} mode={mode} />
          </>
        ) : (
          <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] py-20 text-center text-sm text-[#8B95A1]">
            &quot;데모 실행&quot;을 눌러 감지→진단→개선→승인→실행 사이클을 시작하세요
          </div>
        )}

        {error && (
          <p className="mt-4 text-sm text-red-500" role="alert">
            {error}
          </p>
        )}
        <p className="mt-6 text-[11px] text-[#B0B8C1]">
          ⚠ Mock 기반 데모 · 시뮬 점수는 실제 성과와 상관 미검증 · 예측 CTR 등 실측 환산 없음 · 금액 KRW
        </p>
      </div>
    </AppLayout>
  );
}
