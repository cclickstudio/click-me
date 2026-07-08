'use client';

// 채팅 자동 개선 루프 진행 카드 — 백엔드 gen_loop 위젯(loop_id·stream_url)을 SSE로 관찰해
// 반복별 품질점수 → 완료 요약을 보여준다. GenProgressWidget과 동일한 복원·완료 계약.
import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, authedFetch } from '@/lib/api';
import type { GenerationDetail } from '@/lib/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Phase = 'running' | 'done' | 'error';

type SimKpis = {
  click_intent_rate?: number | null;
  purchase_intent?: number | null;
  trust_avg?: number | null;
  rejection_rate?: number | null;
};

type LoopEvent = {
  event?: string;
  iteration?: number;
  mode?: string;
  generation_id?: string;
  quality_score?: number | null;
  fix?: string;
  reason?: string;
  message?: string;
  final_generation_id?: string;
  threshold_met?: boolean;
  iterations?: number;
  kpis?: SimKpis; // simulated 이벤트 — 최초 1회 시뮬 KPI
  focus?: string; // sim_direction 이벤트 — 최우선 개선 지표 진단
};

// 최초 시뮬 KPI 한 줄 요약 — 진단 표시용(반복 비교 아님, 실측 환산 아님)
const simSummary = (k: SimKpis) => {
  const parts: string[] = [];
  if (k.click_intent_rate != null) parts.push(`클릭의향 ${Math.round(k.click_intent_rate * 100)}%`);
  if (k.purchase_intent != null) parts.push(`구매의도 ${k.purchase_intent.toFixed(1)}/5`);
  if (k.trust_avg != null) parts.push(`신뢰도 ${k.trust_avg.toFixed(1)}/5`);
  if (k.rejection_rate != null) parts.push(`거부율 ${Math.round(k.rejection_rate * 100)}%`);
  return parts.join(' · ');
};

type IterRow = { iteration: number; quality_score: number | null };

const cardCls =
  'mt-1 w-full rounded-xl border border-line bg-card p-4';

const scoreLabel = (s: number | null | undefined) =>
  s == null ? '—' : `${Math.round(s * 100)}점`;

export default function GenLoopWidget({
  loopId,
  streamUrl,
  onComplete,
}: {
  loopId: string;
  streamUrl: string;
  // 완료 시 어시스턴트 결과 위젯(gen_result)을 띄우는 경로 — 새로고침 복원 시엔 미발화(중복 방지)
  onComplete?: (generationId: string, candidateCount: number) => void;
}) {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>('running');
  const [rows, setRows] = useState<IterRow[]>([]);
  const [statusMsg, setStatusMsg] = useState('자동 개선 루프 진행 중...');
  const [finalGid, setFinalGid] = useState<string | null>(null);
  const [thresholdMet, setThresholdMet] = useState<boolean | null>(null);
  const [simDiag, setSimDiag] = useState<{ summary: string; focus?: string } | null>(null);
  const [err, setErr] = useState('');
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    let cancelled = false;

    const upsertRow = (iteration: number, quality_score: number | null) => {
      setRows(prev => {
        const next = prev.filter(r => r.iteration !== iteration);
        next.push({ iteration, quality_score });
        return next.sort((a, b) => a.iteration - b.iteration);
      });
    };

    const finish = async (gid: string, fireComplete: boolean) => {
      setFinalGid(gid);
      setPhase('done');
      if (!fireComplete) return;
      try {
        const d = (await api.generator.detail(gid)) as GenerationDetail;
        if (cancelled) return;
        onComplete?.(gid, (d.candidates ?? []).length);
      } catch {
        /* 결과 위젯 발화 실패 — 인라인 요약으로 충분 */
      }
    };

    const handleEvent = (d: LoopEvent, live: boolean) => {
      switch (d.event) {
        case 'iteration_start':
          setStatusMsg(d.iteration === 0 ? '최초 시안 생성 중...' : `개선 ${d.iteration}회차 생성 중...`);
          break;
        case 'generated':
          if (typeof d.iteration === 'number') upsertRow(d.iteration, d.quality_score ?? null);
          setStatusMsg('품질 평가 중...');
          break;
        case 'simulated':
          if (d.kpis) setSimDiag(prev => ({ summary: simSummary(d.kpis!), focus: prev?.focus }));
          break;
        case 'sim_direction':
          setSimDiag(prev => ({ summary: prev?.summary ?? '', focus: d.focus }));
          break;
        case 'improving':
          setStatusMsg(`개선 방향 반영 중${d.fix ? ` — ${d.fix.split('\n')[0]}` : ''}`);
          break;
        case 'stopped':
          setStatusMsg('더 적용할 개선점이 없어 조기 종료했어요.');
          break;
        case 'completed':
          if (typeof d.threshold_met === 'boolean') setThresholdMet(d.threshold_met);
          if (d.final_generation_id) void finish(d.final_generation_id, live);
          break;
        case 'error':
          setErr(d.message ?? '루프 실행 오류');
          setPhase('error');
          break;
      }
    };

    const subscribe = () => {
      esRef.current?.close();
      // 스트림은 이벤트를 처음부터 재생하므로 재구독만으로 진행 상태가 복원된다.
      const es = new EventSource(`${API_BASE}${streamUrl}`);
      esRef.current = es;
      es.onmessage = ev => {
        try {
          handleEvent(JSON.parse(ev.data) as LoopEvent, true);
        } catch {
          /* ignore malformed line */
        }
      };
      es.onerror = () => es.close(); // 완료 시 서버가 스트림을 닫는다(completed 이벤트로 이미 확정)
    };

    // 마운트(새로고침 복원 포함) — 상태를 먼저 확정하고, 끝난 루프는 onComplete 재발화 없이 요약만.
    (async () => {
      try {
        const res = await authedFetch(`${API_BASE}/api/generator/generations/loop/${loopId}`);
        if (cancelled) return;
        if (res.status === 404) {
          setErr('루프 정보를 찾을 수 없어요. 서버가 재시작됐을 수 있어요.');
          setPhase('error');
          return;
        }
        const body = (await res.json()) as {
          status?: string;
          result?: {
            final_generation_id?: string;
            threshold_met?: boolean;
            history?: { iteration: number; quality_score: number | null }[];
          } | null;
        };
        if (body.status === 'completed' && body.result) {
          (body.result.history ?? []).forEach(h => upsertRow(h.iteration, h.quality_score));
          setThresholdMet(body.result.threshold_met ?? null);
          if (body.result.final_generation_id) void finish(body.result.final_generation_id, false);
          return;
        }
        if (body.status === 'failed') {
          setErr('자동 개선 루프가 실패했어요.');
          setPhase('error');
          return;
        }
        subscribe();
      } catch {
        if (!cancelled) subscribe(); // 일시 조회 실패 — 스트림으로 진행
      }
    })();

    return () => {
      cancelled = true;
      esRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loopId, streamUrl]);

  if (phase === 'error') {
    return (
      <div className={cardCls}>
        <p className="text-sm text-[#F04452]">자동 개선 루프 오류: {err}</p>
      </div>
    );
  }

  const simBlock = simDiag && (simDiag.summary || simDiag.focus) && (
    <div className="mt-2 rounded-lg bg-primary-subtle px-3 py-2 text-xs">
      <span className="font-semibold text-primary">🧪 소비자 반응 진단</span>
      {simDiag.summary && (
        <p className="text-ink-secondary mt-0.5">{simDiag.summary}</p>
      )}
      {simDiag.focus && (
        <p className="text-ink mt-0.5">
          최우선 개선 — <span className="font-semibold">{simDiag.focus}</span>
        </p>
      )}
    </div>
  );

  const historyList = rows.length > 0 && (
    <ul className="space-y-1 mt-2">
      {rows.map(r => (
        <li
          key={r.iteration}
          className="flex items-center justify-between rounded-lg bg-surface-1 px-3 py-1.5 text-xs"
        >
          <span className="text-ink-secondary">
            {r.iteration === 0 ? '최초 생성' : `개선 ${r.iteration}회차`}
          </span>
          <span className="font-semibold text-ink">
            품질 {scoreLabel(r.quality_score)}
          </span>
        </li>
      ))}
    </ul>
  );

  if (phase === 'running') {
    return (
      <div className={cardCls}>
        <div className="flex items-center gap-3">
          <div className="w-6 h-6 border-[3px] border-line border-t-primary dark:border-t-[#5B9DF9] rounded-full animate-spin" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-ink">
              🔁 자동 개선 루프
            </p>
            <p className="text-xs text-ink-secondary mt-0.5 truncate">{statusMsg}</p>
          </div>
        </div>
        {simBlock}
        {historyList}
      </div>
    );
  }

  // phase === 'done' — 새로고침 복원 등 인라인 요약(라이브 완료 시엔 gen_result 위젯이 따로 뜬다)
  return (
    <div className={cardCls}>
      <p className="text-sm font-semibold text-ink mb-1">
        ✅ 자동 개선 루프 완료
        {thresholdMet != null && (
          <span
            className={`ml-2 text-[11px] px-2 py-0.5 rounded-full font-medium ${
              thresholdMet
                ? 'bg-emerald-50 text-emerald-600'
                : 'bg-amber-50 text-amber-600'
            }`}
          >
            {thresholdMet ? '품질 목표 달성' : '반복 상한 도달'}
          </span>
        )}
      </p>
      {simBlock}
      {historyList}
      {finalGid && (
        <button
          onClick={() => router.push(`/generations/${finalGid}`)}
          className="mt-3 w-full py-2 rounded-lg border border-primary/30 text-primary text-sm font-semibold hover:bg-primary-subtle transition-colors"
        >
          최종 시안 보기 →
        </button>
      )}
    </div>
  );
}
