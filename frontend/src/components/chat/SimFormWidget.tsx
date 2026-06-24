'use client';

// 채팅 안 시뮬레이션 입력 위젯 — 폼 입력 → api.simulation.start → 진행률 → 결과 요약(+상세 링크)
// 새로고침해도 백그라운드 실행 중이면 run_id(localStorage) + 상태 조회로 스피너를 복원한다.
import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { safeRandomUUID } from '@/lib/utils';
import { getJobs, setSimJob } from '@/lib/runningJobs';
import type { SimRunResult } from '@/lib/types';

type Phase = 'form' | 'running' | 'done' | 'error';

// 진행 중 시뮬 run_id 보관 키 — 동시 1개 정책이라 단일 키로 충분(새로고침 복원용).
const ACTIVE_SIM_KEY = 'chat_active_sim_run';

const inputCls =
  'w-full px-3 py-2 rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] text-sm bg-white dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] focus:outline-none focus:border-[#3182F6]';
const labelCls = 'text-[11px] font-semibold text-[#8B95A1] dark:text-[#6B7280] mb-1 block';

export default function SimFormWidget({
  initial,
  initialImage,
  projectId,
  latest,
  onSimComplete,
}: {
  initial?: {
    ad_content?: string;
    ad_title?: string;
    product_category?: string;
    ad_objective?: string;
  };
  initialImage?: File; // 채팅에서 첨부한 광고 이미지
  projectId?: string; // 현재 프로젝트 — DB 영속화·결과 상세 조회에 필요
  latest?: boolean; // 가장 최근 시뮬 위젯만 새로고침 시 진행중 런을 복원(중복 방지)
  // 완료 시 결과를 채팅 컨트롤러로 넘긴다 — 입력 요약·결과 요약·토론을 별도 메시지로 띄우게.
  onSimComplete?: (
    result: SimRunResult,
    input: {
      adTitle: string;
      adContent: string;
      category: string;
      objective: string;
      sampleSize: number;
    },
  ) => void;
}) {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>('form');
  const [step, setStep] = useState(0);
  const [runId, setRunId] = useState<string | null>(null);
  const [adTitle, setAdTitle] = useState(initial?.ad_title ?? '');
  const [adContent, setAdContent] = useState(initial?.ad_content ?? '');
  const [category, setCategory] = useState(initial?.product_category ?? '');
  const [objective, setObjective] = useState(initial?.ad_objective ?? '');
  const [image] = useState<File | null>(initialImage ?? null);
  const [imagePreview] = useState<string | null>(() =>
    initialImage ? URL.createObjectURL(initialImage) : null,
  );
  const [sampleSize, setSampleSize] = useState(20);
  const [pct, setPct] = useState(0);
  const [stageMsg, setStageMsg] = useState('준비 중...');
  const [err, setErr] = useState('');
  const esRef = useRef<EventSource | null>(null);
  const completeFiredRef = useRef(false); // onSimComplete 1회 보장(SSE completed·onerror 중복 방지)

  const finish = async (rid: string) => {
    setSimJob(null); // 완료 — 동시실행 슬롯 해제
    localStorage.removeItem(ACTIVE_SIM_KEY);
    try {
      const r = await api.simulation.result(rid);
      setPhase('done');
      // 결과를 채팅 컨트롤러로 넘겨 결과 요약 위젯 + 토론을 별도 메시지로 띄운다(1회만).
      if (!completeFiredRef.current) {
        completeFiredRef.current = true;
        onSimComplete?.(r, { adTitle, adContent, category, objective, sampleSize });
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : '결과 조회 실패');
      setPhase('error');
    }
  };

  // SSE 구독 — 최초 실행·새로고침 복원 공용. 진행률 갱신 + 완료/에러 처리.
  const subscribe = (rid: string) => {
    esRef.current?.close();
    const es = api.simulation.stream(rid);
    esRef.current = es;
    es.onmessage = ev => {
      try {
        const d = JSON.parse(ev.data) as { event?: string; pct?: number; message?: string };
        if (typeof d.pct === 'number') setPct(d.pct);
        if (d.message) setStageMsg(d.message);
        if (d.event === 'completed') {
          es.close();
          void finish(rid);
        } else if (d.event === 'error') {
          es.close();
          setSimJob(null);
          localStorage.removeItem(ACTIVE_SIM_KEY);
          setErr(d.message ?? '실행 오류');
          setPhase('error');
        }
      } catch {
        /* ignore malformed line */
      }
    };
    es.onerror = () => {
      es.close();
      void finish(rid); // 스트림 끊겨도 결과 조회 시도
    };
  };

  // 새로고침 복원 — 최신 위젯만, 진행 중 run_id가 있으면 상태 조회 후 스피너/결과로 복원.
  useEffect(() => {
    if (!latest) return;
    const rid = localStorage.getItem(ACTIVE_SIM_KEY);
    if (!rid) return;
    let cancelled = false;
    (async () => {
      try {
        const st = await api.simulation.status(rid);
        if (cancelled) return;
        if (st.status === 'RUNNING') {
          setRunId(rid);
          setSimJob(rid);
          setPct(st.pct ?? 0);
          setStageMsg(st.stage ? `${st.stage} 진행 중...` : '시뮬레이션 진행 중...');
          setPhase('running');
          subscribe(rid);
        } else if (st.status === 'COMPLETED') {
          setRunId(rid);
          void finish(rid);
        } else {
          localStorage.removeItem(ACTIVE_SIM_KEY); // unknown/failed — 정리
        }
      } catch {
        localStorage.removeItem(ACTIVE_SIM_KEY);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latest]);

  // 언마운트 시 스트림 정리(슬롯은 유지 — 백그라운드 런 동시실행 방지).
  useEffect(() => () => esRef.current?.close(), []);

  const run = async () => {
    if (!adTitle.trim() || !adContent.trim()) return;
    if (getJobs().sim) {
      setErr('이미 다른 시뮬레이션이 진행 중이에요. 끝난 뒤 다시 시도하세요.');
      setPhase('error');
      return;
    }
    setPhase('running');
    setPct(0);
    setStageMsg('시뮬레이션 시작...');
    try {
      const { run_id } = await api.simulation.start({
        ad_id: `chat-${safeRandomUUID()}`,
        ad_title: adTitle || undefined,
        ad_content: adContent,
        ad_image: image ?? undefined,
        project_id: projectId || undefined, // 프로젝트 귀속 → DB 저장(없으면 메모리 런)
        product_category: category || undefined,
        ad_objective: objective || undefined,
        sample_size: sampleSize,
      });
      setRunId(run_id);
      setSimJob(run_id); // 동시실행 슬롯 점유(시뮬 1개 제한)
      localStorage.setItem(ACTIVE_SIM_KEY, run_id); // 새로고침 복원용
      subscribe(run_id);
    } catch (e) {
      setSimJob(null);
      setErr(e instanceof Error ? e.message : '시작 실패');
      setPhase('error');
    }
  };

  const cardCls =
    'mt-1 w-full rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] p-4';

  if (phase === 'form') {
    const totalSteps = 4;
    // 제품명(0단계)·광고 설명(1단계) 모두 필수.
    const canNext =
      (step !== 0 || adTitle.trim().length > 0) && (step !== 1 || adContent.trim().length > 0);
    const btnCls =
      'flex-1 py-2 rounded-lg bg-[#3182F6] text-white text-sm font-semibold hover:bg-[#1B6EEB] disabled:opacity-40 transition-colors';
    return (
      <div className={cardCls}>
        <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-3">
          🧪 시뮬레이션 정보 입력{' '}
          <span className="text-[11px] font-normal text-[#8B95A1]">
            ({step + 1}/{totalSteps})
          </span>
        </p>
        {imagePreview && (
          <div className="mb-3 flex items-center gap-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={imagePreview} alt="첨부 이미지" className="w-12 h-12 rounded-lg object-cover border border-[#E5E8EB] dark:border-[#2D3748]" />
            <span className="text-[11px] text-[#8B95A1]">채팅에서 첨부한 이미지를 사용해요</span>
          </div>
        )}
        <div className="min-h-[68px]">
          {step === 0 && (
            <div>
              <label className={labelCls}>제품명 *</label>
              <input className={inputCls} value={adTitle} onChange={e => setAdTitle(e.target.value)} placeholder="예: 클릭미 신상 크림" autoFocus />
            </div>
          )}
          {step === 1 && (
            <div>
              <label className={labelCls}>광고 설명 *</label>
              <textarea className={`${inputCls} resize-none`} rows={3} value={adContent} onChange={e => setAdContent(e.target.value)} placeholder="광고 카피·내용" autoFocus />
            </div>
          )}
          {step === 2 && (
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className={labelCls}>카테고리</label>
                <input className={inputCls} value={category} onChange={e => setCategory(e.target.value)} placeholder="예: 화장품" autoFocus />
              </div>
              <div>
                <label className={labelCls}>광고 목표</label>
                <input className={inputCls} value={objective} onChange={e => setObjective(e.target.value)} placeholder="예: 구매 전환" />
              </div>
            </div>
          )}
          {step === 3 && (
            <div>
              <label className={labelCls}>가상 소비자 수: {sampleSize}명</label>
              <input type="range" min={1} max={200} value={sampleSize} onChange={e => setSampleSize(Number(e.target.value))} className="w-full" />
            </div>
          )}
        </div>
        <div className="flex gap-2 mt-3">
          {step > 0 && (
            <button onClick={() => setStep(step - 1)} className="px-3 py-2 rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] text-sm text-[#8B95A1]">
              이전
            </button>
          )}
          {step < totalSteps - 1 ? (
            <button onClick={() => setStep(step + 1)} disabled={!canNext} className={btnCls}>
              다음
            </button>
          ) : (
            <button onClick={run} disabled={!adTitle.trim() || !adContent.trim()} className={btnCls}>
              시뮬레이션 실행
            </button>
          )}
        </div>
      </div>
    );
  }

  if (phase === 'running') {
    return (
      <button
        type="button"
        onClick={() => runId && router.push(`/simulation/${runId}`)}
        className={`${cardCls} w-full text-left hover:border-[#3182F6] transition-colors`}
        title="클릭하면 시뮬레이션 페이지에서 자세히 봐요"
      >
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
        <p className="text-[10px] text-[#B0B8C1] mt-2">클릭하면 전체 화면에서 진행을 봐요 →</p>
      </button>
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

  // phase === 'done' — 결과 요약·토론은 아래 별도 메시지(sim_result·debate_stream)로 이어진다.
  return (
    <div className={cardCls}>
      <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">✅ 시뮬레이션 완료</p>
      <p className="mt-1 text-[12px] text-[#8B95A1]">아래에서 결과 요약과 토론을 확인하세요.</p>
    </div>
  );
}
