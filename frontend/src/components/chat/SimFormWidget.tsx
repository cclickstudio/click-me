'use client';

// 채팅 안 시뮬레이션 입력 위젯 — 폼 입력 → api.simulation.start → 진행률 → 결과 요약(+상세 링크)
import { useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { safeRandomUUID } from '@/lib/utils';
import type { SimRunResult } from '@/lib/types';

type Phase = 'form' | 'running' | 'done' | 'error';

const inputCls =
  'w-full px-3 py-2 rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] text-sm bg-white dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] focus:outline-none focus:border-[#3182F6]';
const labelCls = 'text-[11px] font-semibold text-[#8B95A1] dark:text-[#6B7280] mb-1 block';

export default function SimFormWidget({ initial }: { initial?: { ad_content?: string } }) {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>('form');
  const [adTitle, setAdTitle] = useState('');
  const [adContent, setAdContent] = useState(initial?.ad_content ?? '');
  const [category, setCategory] = useState('');
  const [objective, setObjective] = useState('');
  const [sampleSize, setSampleSize] = useState(20);
  const [pct, setPct] = useState(0);
  const [stageMsg, setStageMsg] = useState('준비 중...');
  const [result, setResult] = useState<SimRunResult | null>(null);
  const [err, setErr] = useState('');
  const esRef = useRef<EventSource | null>(null);

  const finish = async (runId: string) => {
    try {
      const r = await api.simulation.result(runId);
      setResult(r);
      setPhase('done');
    } catch (e) {
      setErr(e instanceof Error ? e.message : '결과 조회 실패');
      setPhase('error');
    }
  };

  const run = async () => {
    if (!adContent.trim()) return;
    setPhase('running');
    setPct(0);
    setStageMsg('시뮬레이션 시작...');
    try {
      const { run_id } = await api.simulation.start({
        ad_id: `chat-${safeRandomUUID()}`,
        ad_title: adTitle || undefined,
        ad_content: adContent,
        product_category: category || undefined,
        ad_objective: objective || undefined,
        sample_size: sampleSize,
      });
      const es = api.simulation.stream(run_id);
      esRef.current = es;
      es.onmessage = ev => {
        try {
          const d = JSON.parse(ev.data) as {
            event?: string;
            pct?: number;
            message?: string;
          };
          if (typeof d.pct === 'number') setPct(d.pct);
          if (d.message) setStageMsg(d.message);
          if (d.event === 'completed') {
            es.close();
            void finish(run_id);
          } else if (d.event === 'error') {
            es.close();
            setErr(d.message ?? '실행 오류');
            setPhase('error');
          }
        } catch {
          /* ignore malformed line */
        }
      };
      es.onerror = () => {
        es.close();
        void finish(run_id); // 스트림 끊겨도 결과 조회 시도
      };
    } catch (e) {
      setErr(e instanceof Error ? e.message : '시작 실패');
      setPhase('error');
    }
  };

  const cardCls =
    'mt-1 w-full rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] p-4';

  if (phase === 'form') {
    return (
      <div className={cardCls}>
        <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-3">
          🧪 시뮬레이션 정보 입력
        </p>
        <div className="space-y-2.5">
          <div>
            <label className={labelCls}>제품명</label>
            <input className={inputCls} value={adTitle} onChange={e => setAdTitle(e.target.value)} placeholder="예: 클릭미 신상 크림" />
          </div>
          <div>
            <label className={labelCls}>광고 설명 *</label>
            <textarea className={`${inputCls} resize-none`} rows={2} value={adContent} onChange={e => setAdContent(e.target.value)} placeholder="광고 카피·내용" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className={labelCls}>카테고리</label>
              <input className={inputCls} value={category} onChange={e => setCategory(e.target.value)} placeholder="예: 화장품" />
            </div>
            <div>
              <label className={labelCls}>광고 목표</label>
              <input className={inputCls} value={objective} onChange={e => setObjective(e.target.value)} placeholder="예: 구매 전환" />
            </div>
          </div>
          <div>
            <label className={labelCls}>가상 소비자 수: {sampleSize}명</label>
            <input type="range" min={1} max={200} value={sampleSize} onChange={e => setSampleSize(Number(e.target.value))} className="w-full" />
          </div>
        </div>
        <button
          onClick={run}
          disabled={!adContent.trim()}
          className="mt-3 w-full py-2 rounded-lg bg-[#3182F6] text-white text-sm font-semibold hover:bg-[#1B6EEB] disabled:opacity-40 transition-colors"
        >
          시뮬레이션 실행
        </button>
      </div>
    );
  }

  if (phase === 'running') {
    return (
      <div className={cardCls}>
        <div className="flex items-center gap-3">
          <div className="w-6 h-6 border-[3px] border-[#E5E8EB] dark:border-[#2D3748] border-t-[#3182F6] rounded-full animate-spin" />
          <div className="flex-1">
            <p className="text-sm text-[#191F28] dark:text-[#F2F4F6]">{stageMsg}</p>
            <div className="mt-1.5 h-1.5 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] overflow-hidden">
              <div className="h-full bg-[#3182F6] transition-all duration-300" style={{ width: `${pct}%` }} />
            </div>
          </div>
          <span className="text-xs text-[#8B95A1]">{pct}%</span>
        </div>
      </div>
    );
  }

  if (phase === 'error') {
    return (
      <div className={cardCls}>
        <p className="text-sm text-[#F04452]">시뮬레이션 실패: {err}</p>
        <button onClick={() => setPhase('form')} className="mt-2 text-xs text-[#3182F6]">
          다시 시도
        </button>
      </div>
    );
  }

  // phase === 'done'
  const agg = result?.aggregate;
  const detailId = result?.simulation_id;
  const pct1 = (n: number | null | undefined) => (n == null ? '—' : `${(n * 100).toFixed(0)}%`);
  const sc = (n: number | null | undefined) => (n == null ? '—' : n.toFixed(2));
  return (
    <div className={cardCls}>
      <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-2">✅ 시뮬레이션 결과</p>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div className="rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D] px-3 py-2">
          <p className="text-[10px] text-[#8B95A1]">클릭 의향률</p>
          <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">{pct1(agg?.click_intent_rate)}</p>
        </div>
        <div className="rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D] px-3 py-2">
          <p className="text-[10px] text-[#8B95A1]">구매의도</p>
          <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">{sc(agg?.purchase_intent)}/5</p>
        </div>
        <div className="rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D] px-3 py-2">
          <p className="text-[10px] text-[#8B95A1]">신뢰도</p>
          <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">{sc(agg?.trust_avg)}/5</p>
        </div>
        <div className="rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D] px-3 py-2">
          <p className="text-[10px] text-[#8B95A1]">거부율</p>
          <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">{pct1(agg?.rejection_rate)}</p>
        </div>
      </div>
      {detailId ? (
        <button
          onClick={() => router.push(`/simulation/${detailId}`)}
          className="mt-3 w-full py-2 rounded-lg border border-[#3182F6]/30 text-[#3182F6] text-sm font-semibold hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors"
        >
          상세 보기 →
        </button>
      ) : (
        <p className="mt-2 text-[11px] text-[#B0B8C1]">프로젝트에 저장되지 않아 상세 페이지는 없어요(요약만).</p>
      )}
    </div>
  );
}
