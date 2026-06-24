'use client';

import { useState } from 'react';
import AppLayout from '@/components/AppLayout';
import { api, type AnomalyScanItem } from '@/lib/api';
import { AZone } from '@/components/manage/AZone';
import { BZone } from '@/components/manage/BZone';
import { ApprovalBridge } from '@/components/manage/ApprovalBridge';
import { AuditTimeline } from '@/components/manage/AuditTimeline';
import { KpiStrip } from '@/components/manage/KpiStrip';
import type { ActionResult, AuditEvent, RunResult, ViewMode } from '@/components/manage/types';

// 주입할 문제 상황 — value는 백엔드 enum, label/symptom은 사용자용.
const FAULT_OPTIONS = [
  {
    value: 'bid_loss',
    label: '입찰 경쟁 패배 — 노출 급감',
    symptom: '14시부터 노출이 급감하는데 예산은 남아요. 경매가 급등·낙찰률 하락 신호예요.',
  },
  {
    value: 'review_rejected',
    label: '심사 거부 — 게재 중단',
    symptom: '광고가 심사에서 거부돼 노출이 전면 중단돼요.',
  },
  {
    value: 'none',
    label: '정상 — 문제 없음',
    symptom: '이상 없이 정상 게재돼요. 감지기가 "정상"으로 판정하는지 확인하는 경우예요.',
  },
];

export default function Page() {
  const [mode, setMode] = useState<ViewMode>('user');
  const [fault, setFault] = useState('bid_loss');
  const [run, setRun] = useState<RunResult | null>(null);
  const [result, setResult] = useState<ActionResult | null>(null);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [decided, setDecided] = useState<'approved' | 'rejected' | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 실 캠페인 성과 이상 스캔 (데모와 별개 — live 전용)
  const [scan, setScan] = useState<{ items: AnomalyScanItem[]; scanned: number; note?: string } | null>(
    null,
  );
  const [scanBusy, setScanBusy] = useState(false);

  const scanReal = async () => {
    setScanBusy(true);
    try {
      const r = await api.management.anomalyScan(3.0);
      setScan({ items: r.anomalies, scanned: r.scanned, note: r.note });
    } catch (e) {
      setScan({ items: [], scanned: 0, note: e instanceof Error ? e.message : '스캔 실패' });
    } finally {
      setScanBusy(false);
    }
  };

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
              <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">이상 감지</h1>
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
                title="결과를 사용자 관점으로 요약해서 보기"
                className={`px-3 py-1.5 ${mode === 'user' ? 'bg-[#3182F6] text-white' : 'text-[#8B95A1]'}`}
              >
                사용자 보기
              </button>
              <button
                onClick={() => setMode('arch')}
                title="감지·진단·실행의 내부 동작(아키텍처) 상세 보기"
                className={`px-3 py-1.5 ${mode === 'arch' ? 'bg-[#3182F6] text-white' : 'text-[#8B95A1]'}`}
              >
                내부 동작
              </button>
            </div>
            <span className="text-[11px] text-[#8B95A1]">문제 상황 주입</span>
            <select
              value={fault}
              onChange={(e) => setFault(e.target.value)}
              className="text-sm px-2 py-1.5 rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent"
            >
              {FAULT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
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

        {/* 시연 안내 + 선택한 문제 상황의 증상 미리보기 */}
        <div className="mb-4 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#1A202C] px-4 py-3">
          <p className="text-[12px] text-[#4E5968] dark:text-[#9CA3AF]">
            <span className="font-semibold text-[#3182F6]">시연 방법</span> · 문제 상황을 고르고{' '}
            <b>데모 실행</b>을 누르면, 시스템이 <b>감지 → 진단 → 처방</b>하는 과정을 보여줍니다.
          </p>
          <p className="mt-1.5 flex items-start gap-1.5 text-[12px]">
            <span className="shrink-0 px-1.5 py-0.5 rounded-md bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 text-[11px] font-semibold">
              예상 증상
            </span>
            <span className="text-[#8B95A1]">
              {FAULT_OPTIONS.find((o) => o.value === fault)?.symptom}
            </span>
          </p>
        </div>

        {/* 실 캠페인 성과 이상 스캔 — 데모(고장주입)와 별개, 실 Meta 캠페인을 진단 */}
        <div className="mb-4 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] px-4 py-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">
                실 캠페인 성과 이상 스캔
              </p>
              <p className="text-[12px] text-[#8B95A1] mt-0.5">
                실제 Meta 캠페인을 돌며 성과 진단(ROAS 미달·전환 저조)을 실측합니다. 위 데모와 별개.
              </p>
            </div>
            <button
              onClick={scanReal}
              disabled={scanBusy}
              className="px-3 py-1.5 bg-[#191F28] text-white text-[12px] font-medium rounded-lg hover:bg-black disabled:opacity-40"
            >
              {scanBusy ? '스캔 중…' : '실 캠페인 스캔'}
            </button>
          </div>
          {scan && (
            <div className="mt-3">
              {scan.note && <p className="text-[12px] text-[#8B95A1]">{scan.note}</p>}
              {!scan.note && (
                <p className="text-[12px] text-[#8B95A1]">
                  {scan.scanned}개 캠페인 스캔 · 이상 {scan.items.length}건
                </p>
              )}
              <ul className="mt-2 space-y-1.5">
                {scan.items.map((a) => (
                  <li
                    key={a.campaign_id}
                    className="rounded-lg bg-amber-50 dark:bg-amber-900/20 px-3 py-2"
                  >
                    <p className="text-[12px] font-semibold text-amber-700 dark:text-amber-300">
                      {a.name} — {a.diagnosis.anomaly_type}
                    </p>
                    {a.diagnosis.hypothesis && (
                      <p className="text-[12px] text-amber-700 dark:text-amber-300">
                        {a.diagnosis.hypothesis}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
              {!scan.note && scan.items.length === 0 && (
                <p className="mt-1 text-[12px] text-green-600 dark:text-green-400">
                  성과 이상 없음 — 진단된 문제가 없습니다.
                </p>
              )}
            </div>
          )}
        </div>

        <KpiStrip run={run} />

        {run ? (
          <>
            {(() => {
              const ran = FAULT_OPTIONS.find((o) => o.value === run.fault);
              const detected = run.anomaly_hours.length > 0;
              const matched = detected === (run.fault !== 'none');
              return (
                <div className="mb-4 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] px-4 py-3 text-[12px] space-y-1">
                  <p>
                    <span className="font-semibold text-amber-700 dark:text-amber-400">예상</span>{' '}
                    <span className="text-[#8B95A1]">{ran?.symptom}</span>
                  </p>
                  <p>
                    <span className="font-semibold text-[#3182F6]">감지 결과</span>{' '}
                    <span className="text-[#4E5968] dark:text-[#9CA3AF]">
                      {detected
                        ? `이상 구간 ${run.anomaly_hours.length}개 감지`
                        : '이상 없음 — 정상 판정'}
                    </span>
                    {matched && (
                      <span className="ml-2 font-semibold text-green-600 dark:text-green-400">
                        ✓ 예상대로
                      </span>
                    )}
                  </p>
                </div>
              );
            })()}
            <div className="flex flex-col lg:flex-row gap-4 items-stretch">
              <AZone run={run} mode={mode} />
              <BZone proposal={run.proposal} result={result} mode={mode} />
            </div>
            <ApprovalBridge run={run} decided={decided} onApprove={approve} onReject={reject} mode={mode} />
            <AuditTimeline events={audit} mode={mode} />
          </>
        ) : (
          <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] py-20 text-center text-sm text-[#8B95A1]">
            &quot;데모 실행&quot;을 눌러 감지→진단→처방→승인→실행 사이클을 시작하세요
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
