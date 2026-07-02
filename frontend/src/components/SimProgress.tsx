// 챗 트리거 작업(시뮬·토론·생성)의 라이브 진행률 — /api/chat/{kind}/{id}/stream 구독, 완료 시 요약.
'use client';

import { useEffect, useRef, useState } from 'react';
import { authedFetch } from '@/lib/api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export type JobKind = 'sim' | 'debate' | 'gen';

// 진행 단계 라벨(표준 SimulationService/DebateService/generator 이벤트와 동일).
const STAGE_LABEL: Record<string, string> = {
  ad_analysis: '광고 해석 중...',
  panel: '페르소나 패널 로드 중...',
  reaction: '페르소나 반응 생성 중...',
  aggregate: '결과 집계 중...',
  analysis: '반응 분석 중...',
  kpi: 'KPI 계산 중...',
  topic: '토론 주제 도출 중...',
  selection: '토론 패널 선발 중...',
  assignment: '토론자 배정 중...',
  debate: '토론 진행 중...',
  judge_final: '판정 정리 중...',
  report: '리포트 작성 중...',
};

const LABEL: Record<JobKind, { run: string; done: string; err: string }> = {
  sim: { run: '시뮬레이션 진행 중', done: '시뮬레이션 완료', err: '시뮬레이션 오류' },
  debate: { run: '토론 진행 중', done: '토론 완료', err: '토론 오류' },
  gen: { run: '시안 생성 진행 중', done: '시안 생성 완료', err: '시안 생성 오류' },
};

type ProgressEvent = { event?: string; pct?: number; stage?: string; message?: string };

const rate = (v?: number | null) => (typeof v === 'number' ? `${(v * 100).toFixed(0)}%` : '—');
const sc = (v?: number | null) => (typeof v === 'number' ? `${v.toFixed(1)}/5` : '—');

export function JobProgress({
  kind,
  id,
  onDone,
}: {
  kind: JobKind;
  id: string;
  onDone?: () => void;
}) {
  const [pct, setPct] = useState(0);
  const [hasPct, setHasPct] = useState(false);
  const [stageMsg, setStageMsg] = useState('준비 중...');
  const [status, setStatus] = useState<'running' | 'done' | 'error'>('running');
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    if (!id) return;
    // withCredentials: SSE는 Authorization 헤더를 못 붙이므로 쿠키로 인증(백엔드 쿠키 폴백).
    const es = new EventSource(`${API_BASE}/api/chat/${kind}/${id}/stream`, {
      withCredentials: true,
    });
    esRef.current = es;
    es.onmessage = (ev: MessageEvent) => {
      let data: ProgressEvent;
      try {
        data = JSON.parse(ev.data) as ProgressEvent;
      } catch {
        return;
      }
      if (data.event === 'error') {
        setStatus('error');
        setStageMsg(data.message ?? '진행 중 오류가 발생했어요');
        es.close();
        esRef.current = null;
        return;
      }
      if (typeof data.pct === 'number') {
        setPct(data.pct);
        setHasPct(true);
      }
      if (data.stage) setStageMsg(data.message ?? STAGE_LABEL[data.stage] ?? '');
      if (data.event === 'completed') {
        setPct(100);
        setHasPct(true);
        setStatus('done');
        es.close();
        esRef.current = null;
        authedFetch(`${API_BASE}/api/chat/${kind}/${id}/result`)
          .then((r) => r.json())
          .then((r) => setResult(r as Record<string, unknown>))
          .catch(() => {})
          .finally(() => onDoneRef.current?.());
      }
    };
    es.onerror = () => {
      // 완료 시 서버가 스트림을 닫으면 onerror가 날 수 있다 — 상태는 completed에서만 바꾼다.
    };
    return () => {
      es.close();
      esRef.current = null;
    };
  }, [kind, id]);

  const lab = LABEL[kind];
  const barPct = status === 'done' ? 100 : hasPct ? pct : status === 'error' ? 100 : 35;

  return (
    <div className="w-full rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#1C2333] px-3 py-2.5">
      <div className="flex items-center justify-between mb-1.5">
        <p className="text-[10px] font-semibold text-[#8B95A1] dark:text-[#6B7280]">
          {status === 'done' ? lab.done : status === 'error' ? lab.err : lab.run}
        </p>
        {hasPct && status !== 'error' && (
          <span className="text-[10px] text-[#8B95A1] dark:text-[#6B7280]">{pct}%</span>
        )}
      </div>
      <div className="h-1.5 w-full rounded-full bg-[#E5E8EB] dark:bg-[#2D3748] overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            status === 'error' ? 'bg-red-400' : 'bg-[#3182F6]'
          } ${status === 'running' && !hasPct ? 'animate-pulse' : ''}`}
          style={{ width: `${barPct}%` }}
        />
      </div>
      <p className="text-[11px] text-[#4E5968] dark:text-[#9CA3AF] mt-1.5">{stageMsg}</p>
      {status === 'done' && <Summary kind={kind} result={result} />}
    </div>
  );
}

function Summary({ kind, result }: { kind: JobKind; result: Record<string, unknown> | null }) {
  if (!result || (result as { error?: string }).error) {
    return (
      <p className="text-[10px] text-[#B0B8C1] dark:text-[#6B7280] mt-1.5">
        완료됐어요. 결과가 저장되지 않았을 수 있어요 — 좌측 프로젝트 목록도 확인해 보세요.
      </p>
    );
  }
  if (kind === 'sim') {
    const agg = (result.aggregate ?? {}) as Record<string, number | null>;
    const pi = agg.purchase_intent ?? agg.purchase_intent_avg;
    return (
      <div className="grid grid-cols-2 gap-1.5 mt-2">
        <Kpi label="클릭 의향률" value={rate(agg.click_intent_rate)} />
        <Kpi label="구매의도" value={sc(pi)} />
        <Kpi label="신뢰도" value={sc(agg.trust_avg)} />
        <Kpi label="거부율" value={rate(agg.rejection_rate)} />
      </div>
    );
  }
  if (kind === 'gen') {
    const cands = (result.candidates ?? []) as Array<{ qa_passed?: boolean }>;
    const passed = cands.filter((c) => c?.qa_passed).length;
    return (
      <p className="text-[11px] text-[#4E5968] dark:text-[#9CA3AF] mt-2">
        시안 <b>{cands.length}</b>개 생성 · QA 통과 <b>{passed}</b>개 — 좌측 프로젝트의 광고 시안 목록에서 확인하세요.
      </p>
    );
  }
  // debate
  const topic = (result.topic ?? {}) as { headline?: string };
  return (
    <p className="text-[11px] text-[#4E5968] dark:text-[#9CA3AF] mt-2">
      {topic.headline ? `토론 주제: ${topic.headline}` : '토론이 완료됐어요.'} — &quot;토론 결과 보여줘&quot;라고 하시면 상세를 보여드릴게요.
    </p>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white dark:bg-[#252D3D] px-2 py-1.5">
      <p className="text-[10px] text-[#8B95A1] dark:text-[#6B7280]">{label}</p>
      <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">{value}</p>
    </div>
  );
}
