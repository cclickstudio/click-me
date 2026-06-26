// 챗 트리거 시뮬의 라이브 진행률 — /api/chat/sim/{runId}/stream 구독, 완료 시 KPI 인라인.
'use client';

import { useEffect, useRef, useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// 표준 시뮬 진행 단계 라벨(simulation 페이지와 동일 — 같은 SimulationService 이벤트).
const STAGE_LABEL: Record<string, string> = {
  ad_analysis: '광고 해석 중...',
  panel: '페르소나 패널 로드 중...',
  reaction: '페르소나 반응 생성 중...',
  aggregate: '결과 집계 중...',
};

type Agg = {
  click_intent_rate?: number | null;
  purchase_intent?: number | null;
  purchase_intent_avg?: number | null;
  trust_avg?: number | null;
  rejection_rate?: number | null;
};

type ProgressEvent = { event?: string; pct?: number; stage?: string; message?: string };

const rate = (v?: number | null) => (typeof v === 'number' ? `${(v * 100).toFixed(0)}%` : '—');
const score = (v?: number | null) => (typeof v === 'number' ? `${v.toFixed(1)}/5` : '—');

export function SimProgress({ runId, onDone }: { runId: string; onDone?: () => void }) {
  const [pct, setPct] = useState(0);
  const [stageMsg, setStageMsg] = useState('시뮬레이션 준비 중...');
  const [status, setStatus] = useState<'running' | 'done' | 'error'>('running');
  const [agg, setAgg] = useState<Agg | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    if (!runId) return;
    const es = new EventSource(`${API_BASE}/api/chat/sim/${runId}/stream`);
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
      if (typeof data.pct === 'number') setPct(data.pct);
      if (data.stage) setStageMsg(data.message ?? STAGE_LABEL[data.stage] ?? '');
      if (data.event === 'completed') {
        setPct(100);
        setStatus('done');
        es.close();
        esRef.current = null;
        fetch(`${API_BASE}/api/chat/sim/${runId}/result`)
          .then((r) => r.json())
          .then((r) => {
            if (r && r.aggregate) setAgg(r.aggregate as Agg);
          })
          .catch(() => {})
          .finally(() => onDoneRef.current?.());
      }
    };
    es.onerror = () => {
      // 완료 시 서버가 스트림을 닫으면 onerror가 날 수 있다 — 상태 보존(완료 처리는 completed에서).
    };
    return () => {
      es.close();
      esRef.current = null;
    };
  }, [runId]);

  const pi = agg?.purchase_intent ?? agg?.purchase_intent_avg;

  return (
    <div className="w-full rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#1C2333] px-3 py-2.5">
      <div className="flex items-center justify-between mb-1.5">
        <p className="text-[10px] font-semibold text-[#8B95A1] dark:text-[#6B7280]">
          {status === 'done' ? '시뮬레이션 완료' : status === 'error' ? '시뮬레이션 오류' : '시뮬레이션 진행 중'}
        </p>
        <span className="text-[10px] text-[#8B95A1] dark:text-[#6B7280]">{pct}%</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-[#E5E8EB] dark:bg-[#2D3748] overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            status === 'error' ? 'bg-red-400' : 'bg-[#3182F6]'
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-[11px] text-[#4E5968] dark:text-[#9CA3AF] mt-1.5">{stageMsg}</p>

      {status === 'done' && agg && (
        <div className="grid grid-cols-2 gap-1.5 mt-2">
          <Kpi label="클릭 의향률" value={rate(agg.click_intent_rate)} />
          <Kpi label="구매의도" value={score(pi)} />
          <Kpi label="신뢰도" value={score(agg.trust_avg)} />
          <Kpi label="거부율" value={rate(agg.rejection_rate)} />
        </div>
      )}
      {status === 'done' && !agg && (
        <p className="text-[10px] text-[#B0B8C1] dark:text-[#6B7280] mt-1.5">
          완료됐어요. 결과가 저장되지 않았을 수 있어요(프로젝트 미선택). 좌측 프로젝트의 시뮬레이션 목록도 확인해 보세요.
        </p>
      )}
    </div>
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
