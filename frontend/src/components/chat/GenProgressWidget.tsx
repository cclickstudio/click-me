'use client';

// 채팅 즉시 실행 생성 진행 카드 — 백엔드 gen_progress 위젯(generation_id)을 SSE로 관찰해
// 진행률 → 완료 요약을 보여준다. GenFormWidget의 running/done/error 단계와 동일한 계약·스타일.
import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { useProjects } from '@/components/ProjectContext';
import { setGenJob } from '@/lib/runningJobs';
import type { GenerationDetail } from '@/lib/types';

type Phase = 'running' | 'done' | 'error';

const cardCls =
  'mt-1 w-full rounded-xl border border-line bg-card p-4';

export default function GenProgressWidget({
  generationId,
  projectId,
  onComplete,
}: {
  generationId: string;
  projectId?: string | null;
  // 완료 시 어시스턴트 결과 위젯(gen_result)을 띄우는 경로 — 새로고침 복원 시엔 미발화(중복 방지)
  onComplete?: (generationId: string, candidateCount: number) => void;
}) {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>('running');
  const [pct, setPct] = useState(0);
  const [stageMsg, setStageMsg] = useState('광고 생성 진행 중...');
  const [detail, setDetail] = useState<GenerationDetail | null>(null);
  const [err, setErr] = useState('');
  const esRef = useRef<EventSource | null>(null);
  const { refreshDetails } = useProjects(); // 완료 생성물을 좌측 패널에 즉시 반영

  useEffect(() => {
    let cancelled = false;

    const finish = async (fireComplete: boolean) => {
      setGenJob(null);
      try {
        const d = (await api.generator.detail(generationId)) as GenerationDetail;
        if (cancelled) return;
        if (d.status === 'failed' || (d.candidates ?? []).length === 0) {
          setErr(d.error_message || '시안을 만들지 못했어요. 잠시 후 다시 시도해 주세요.');
          setPhase('error');
          return;
        }
        setDetail(d);
        setPhase('done');
        if (fireComplete) onComplete?.(generationId, (d.candidates ?? []).length);
      } catch (e) {
        if (cancelled) return;
        setErr(e instanceof Error ? e.message : '결과 조회 실패');
        setPhase('error');
      }
    };

    const subscribe = () => {
      esRef.current?.close();
      const es = api.generator.stream(generationId);
      esRef.current = es;
      es.onmessage = ev => {
        try {
          const d = JSON.parse(ev.data) as { event?: string; pct?: number; message?: string };
          if (typeof d.pct === 'number') setPct(d.pct);
          if (d.message) setStageMsg(d.message);
          if (d.event === 'completed') {
            es.close();
            void finish(true);
            if (projectId) refreshDetails(projectId);
          } else if (d.event === 'error') {
            es.close();
            setGenJob(null);
            setErr(d.message ?? '실행 오류');
            setPhase('error');
          }
        } catch {
          /* ignore malformed line */
        }
      };
      // 스트림 끊김(완료·네트워크) — detail 조회로 완료/실패를 확정한다.
      es.onerror = () => {
        es.close();
        void finish(true);
      };
    };

    // 마운트(새로고침 복원 포함) — 상태를 먼저 확정하고 진행 중일 때만 구독한다.
    (async () => {
      try {
        const d = (await api.generator.detail(generationId)) as GenerationDetail;
        if (cancelled) return;
        if (d.status === 'completed' || d.status === 'failed') {
          // 이미 끝난 생성(복원) — 결과만 인라인 표시, onComplete 재발화 금지(중복 위젯 방지)
          void finish(false);
        } else {
          setGenJob(generationId);
          subscribe();
        }
      } catch {
        if (!cancelled) subscribe(); // 일시 조회 실패 — 스트림으로 진행
      }
    })();

    return () => {
      cancelled = true;
      esRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generationId]);

  if (phase === 'running') {
    return (
      <button
        type="button"
        onClick={() => router.push(`/generations/${generationId}`)}
        className={`${cardCls} w-full text-left hover:border-primary transition-colors`}
        title="클릭하면 생성 페이지에서 자세히 봐요"
      >
        <div className="flex items-center gap-3">
          <div className="w-6 h-6 border-[3px] border-line border-t-[#3182F6] dark:border-t-[#5B9DF9] rounded-full animate-spin" />
          <div className="flex-1">
            <p className="text-sm text-ink">{stageMsg}</p>
            <div className="mt-1.5 h-1.5 rounded-full bg-surface-1 overflow-hidden">
              <div className="h-full bg-primary transition-all duration-300" style={{ width: `${pct}%` }} />
            </div>
          </div>
          <span className="text-xs text-ink-tertiary">{pct}%</span>
        </div>
        <p className="text-[10px] text-ink-muted mt-1">클릭하면 전체 화면에서 진행을 봐요 →</p>
      </button>
    );
  }

  if (phase === 'error') {
    return (
      <div className={cardCls}>
        <p className="text-sm text-[#F04452]">광고 생성 실패: {err}</p>
      </div>
    );
  }

  // phase === 'done' — 새로고침 복원 등 인라인 요약(라이브 완료 시엔 gen_result 위젯이 따로 뜬다)
  const cands = detail?.candidates ?? [];
  return (
    <div className={cardCls}>
      <p className="text-sm font-semibold text-ink mb-2">
        ✅ 광고 시안 {cands.length}개 생성 완료
      </p>
      <ul className="space-y-1.5">
        {cands.slice(0, 3).map(c => (
          <li key={c.candidate_id} className="rounded-lg bg-surface-1 px-3 py-2 text-sm">
            <span className="text-[10px] text-ink-tertiary">{c.strategy?.strategy_type}</span>
            <p className="text-ink truncate">{c.copy?.headline}</p>
          </li>
        ))}
      </ul>
      <button
        onClick={() => router.push(`/generations/${generationId}`)}
        className="mt-3 w-full py-2 rounded-lg border border-primary/30 text-primary text-sm font-semibold hover:bg-primary-subtle transition-colors"
      >
        상세 보기 →
      </button>
    </div>
  );
}
