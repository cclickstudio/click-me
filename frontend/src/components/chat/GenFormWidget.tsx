'use client';

// 채팅 안 광고 생성 입력 위젯 — 단계별 폼 → api.generator.start → 진행률 → 결과 요약(+상세 링크)
// 생성은 project_id 필수(라우터 400)라 프로젝트 선택을 포함한다.
import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { getJobs, setGenJob } from '@/lib/runningJobs';
import type { GenerationDetail, Project } from '@/lib/types';

type Phase = 'form' | 'running' | 'done' | 'error';
type Initial = {
  product_name?: string;
  product_description?: string;
  target_audience?: string;
  campaign_objective?: string;
};

// 진행 중 생성 id 보관 키(G4) — 동시 1개 정책이라 단일 키로 충분(새로고침 복원용).
const ACTIVE_GEN_KEY = 'clickme_active_gen';

const inputCls =
  'w-full px-3 py-2 rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] text-sm bg-white dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] focus:outline-none focus:border-[#3182F6]';
const labelCls = 'text-[11px] font-semibold text-[#8B95A1] dark:text-[#6B7280] mb-1 block';
const cardCls =
  'mt-1 w-full rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] p-4';
const btnCls =
  'flex-1 py-2 rounded-lg bg-[#3182F6] text-white text-sm font-semibold hover:bg-[#1B6EEB] disabled:opacity-40 transition-colors';

export default function GenFormWidget({
  initial,
  initialImage,
  onResult,
  onComplete,
  latest = false,
}: {
  initial?: Initial;
  initialImage?: File; // 채팅에서 첨부한 상품 이미지
  // 완료 시 결과 요약(+결과 참조)을 채팅으로 보내 내역 영속화·다음 단계 제안
  onResult?: (summary: string, resultRef?: { kind: 'sim' | 'gen'; id: string }) => void;
  // 완료 시 어시스턴트 결과 위젯을 띄우는 경로(시뮬과 동일). 있으면 onResult 대신 이걸 쓴다.
  onComplete?: (generationId: string, candidateCount: number) => void;
  latest?: boolean; // 가장 최근 gen_form만 새로고침 복원 대상(G4)
}) {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>('form');
  const [step, setStep] = useState(0);
  const [genId, setGenId] = useState<string | null>(null);
  const [name, setName] = useState(initial?.product_name ?? '');
  const [desc, setDesc] = useState(initial?.product_description ?? '');
  const [target, setTarget] = useState(initial?.target_audience ?? '');
  const [objective, setObjective] = useState(initial?.campaign_objective ?? 'conversion');
  const [image] = useState<File | null>(initialImage ?? null);
  const [imagePreview] = useState<string | null>(() =>
    initialImage ? URL.createObjectURL(initialImage) : null,
  );
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState('');
  const [pct, setPct] = useState(0);
  const [stageMsg, setStageMsg] = useState('준비 중...');
  const [detail, setDetail] = useState<GenerationDetail | null>(null);
  const [err, setErr] = useState('');
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    api.projects
      .list()
      .then(d => {
        const ps = (Array.isArray(d) ? d : []) as Project[];
        setProjects(ps);
        if (ps[0]) setProjectId(ps[0].id);
      })
      .catch(() => {});
  }, []);

  // fireComplete=false면 결과만 인라인으로 보여주고 onComplete(결과 위젯 append·오케스트레이터
  // 재시뮬 신호)는 안 쏜다 — 새로고침 복원(G4)에서 중복 append·재시뮬 재요청을 막기 위함.
  const finish = async (gid: string, fireComplete = true) => {
    setGenJob(null);
    localStorage.removeItem(ACTIVE_GEN_KEY); // 완료 — 복원 키 정리
    try {
      const d = (await api.generator.detail(gid)) as GenerationDetail;
      // 실패했거나 후보가 하나도 없으면 에러 카드로 — "0개 생성 완료"·재시뮬 제안 오노출 방지.
      if (d.status === 'failed' || (d.candidates ?? []).length === 0) {
        setErr(d.error_message || '시안을 만들지 못했어요. 잠시 후 다시 시도해 주세요.');
        setPhase('error');
        return;
      }
      setDetail(d);
      setPhase('done');
      const count = (d.candidates ?? []).length;
      // 어시스턴트 결과 위젯 경로(onComplete)가 있으면 그걸로 — 결과를 assistant가 준다.
      // 없으면 구 경로(onResult: [생성결과] user 메시지) 폴백.
      if (fireComplete) {
        if (onComplete) {
          onComplete(gid, count);
        } else if (onResult) {
          onResult(`[생성결과] 광고 시안 ${count}개 생성 완료`, {
            kind: 'gen',
            id: gid,
          });
        }
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : '결과 조회 실패');
      setPhase('error');
    }
  };

  // SSE 구독 — 최초 실행·새로고침 복원 공용. 진행률 갱신 + 완료/에러 처리(G4).
  // fromRestore면 완료 시 결과만 인라인 표시(onComplete 미발화) — 새로고침 후 완료에서
  // gen_result 중복 append·오케스트레이터 재시뮬 재요청·위젯 리마운트 글리치를 막는다.
  const subscribe = (gid: string, fromRestore = false) => {
    esRef.current?.close();
    const es = api.generator.stream(gid);
    esRef.current = es;
    es.onmessage = ev => {
      try {
        const d = JSON.parse(ev.data) as { event?: string; pct?: number; message?: string };
        if (typeof d.pct === 'number') setPct(d.pct);
        if (d.message) setStageMsg(d.message);
        if (d.event === 'completed') {
          es.close();
          void finish(gid, !fromRestore);
        } else if (d.event === 'error') {
          es.close();
          setGenJob(null);
          localStorage.removeItem(ACTIVE_GEN_KEY);
          setErr(d.message ?? '실행 오류');
          setPhase('error');
        }
      } catch {
        /* ignore malformed line */
      }
    };
    // 스트림 끊김(완료·네트워크) — 상태 조회 대신 detail로 완료/실패를 확정한다(finish 내부에서 분기).
    es.onerror = () => {
      es.close();
      void finish(gid, !fromRestore);
    };
  };

  const run = async () => {
    if (!name.trim() || !desc.trim() || !target.trim() || !projectId) return;
    if (getJobs().gen) {
      setErr('이미 다른 생성이 진행 중이에요. 끝난 뒤 다시 시도하세요.');
      setPhase('error');
      return;
    }
    setPhase('running');
    setPct(0);
    setStageMsg('광고 생성 시작...');
    try {
      // 첨부 이미지가 있으면 상품 이미지로 업로드해 temp_key를 넘긴다(실패해도 이미지 없이 진행).
      let productImageTempKey: string | undefined;
      if (image) {
        try {
          const up = await api.generator.uploadProductImage(image);
          productImageTempKey = up.temp_key;
        } catch {
          /* 업로드 실패 — 이미지 없이 생성 */
        }
      }
      const { generation_id } = (await api.generator.start({
        product_name: name,
        product_description: desc,
        target_audience: target,
        campaign_objective: objective,
        project_id: projectId,
        product_image_temp_key: productImageTempKey ?? null,
      })) as { generation_id: string };
      setGenId(generation_id);
      setGenJob(generation_id); // 동시실행 슬롯 점유(생성 1개 제한)
      localStorage.setItem(ACTIVE_GEN_KEY, generation_id); // 새로고침 복원용(G4)
      subscribe(generation_id);
    } catch (e) {
      setGenJob(null);
      localStorage.removeItem(ACTIVE_GEN_KEY);
      setErr(e instanceof Error ? e.message : '시작 실패');
      setPhase('error');
    }
  };

  // 새로고침 복원(G4) — 최신 gen_form만, 진행 중 generation_id가 있으면 상태 조회 후 스피너/결과로 복원.
  useEffect(() => {
    if (!latest) return;
    const gid = localStorage.getItem(ACTIVE_GEN_KEY);
    if (!gid) return;
    let cancelled = false;
    (async () => {
      try {
        const d = (await api.generator.detail(gid)) as GenerationDetail;
        if (cancelled) return;
        if (d.status === 'running' || d.status === 'pending') {
          setGenId(gid);
          setGenJob(gid);
          setStageMsg('광고 생성 진행 중...');
          setPhase('running');
          subscribe(gid, true); // 복원 구독 — 완료 시 인라인 결과(글리치 방지)
        } else if (d.status === 'completed') {
          // 복원 시엔 결과만 인라인 표시 — onComplete 재발화(중복 위젯·재시뮬 재요청) 방지.
          setGenId(gid);
          void finish(gid, false);
        } else {
          localStorage.removeItem(ACTIVE_GEN_KEY); // failed/unknown — 정리
        }
      } catch {
        localStorage.removeItem(ACTIVE_GEN_KEY);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latest]);

  if (phase === 'form') {
    const totalSteps = 4;
    const stepValid = [name.trim(), desc.trim(), target.trim(), projectId][step];
    // 백엔드 필수값(상품명·상품설명·타깃·저장 프로젝트)과 일치 — 누락 시 실행 차단·안내.
    const missing: string[] = [];
    if (!name.trim()) missing.push('상품명');
    if (!desc.trim()) missing.push('상품 설명');
    if (!target.trim()) missing.push('타깃 고객');
    if (!projectId) missing.push('저장할 프로젝트');
    const allValid = missing.length === 0;
    return (
      <div className={cardCls}>
        <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-3">
          🎨 광고 생성 정보 입력{' '}
          <span className="text-[11px] font-normal text-[#8B95A1]">
            ({step + 1}/{totalSteps})
          </span>
        </p>
        {imagePreview && (
          <div className="mb-3 flex items-center gap-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={imagePreview} alt="첨부 이미지" className="w-12 h-12 rounded-lg object-cover border border-[#E5E8EB] dark:border-[#2D3748]" />
            <span className="text-[11px] text-[#8B95A1]">채팅에서 첨부한 이미지를 상품 이미지로 사용해요</span>
          </div>
        )}
        <div className="min-h-[68px]">
          {step === 0 && (
            <div>
              <label className={labelCls}>상품명 *</label>
              <input className={inputCls} value={name} onChange={e => setName(e.target.value)} placeholder="예: 클릭미 수분크림" autoFocus />
            </div>
          )}
          {step === 1 && (
            <div>
              <label className={labelCls}>상품 설명 *</label>
              <textarea className={`${inputCls} resize-none`} rows={3} value={desc} onChange={e => setDesc(e.target.value)} placeholder="상품 특징·강점" autoFocus />
            </div>
          )}
          {step === 2 && (
            <div>
              <label className={labelCls}>타깃 고객 *</label>
              <input className={inputCls} value={target} onChange={e => setTarget(e.target.value)} placeholder="예: 20-30대 건성 피부 여성" autoFocus />
            </div>
          )}
          {step === 3 && (
            <div className="space-y-2">
              <div>
                <label className={labelCls}>광고 목표</label>
                <input className={inputCls} value={objective} onChange={e => setObjective(e.target.value)} placeholder="예: conversion" />
              </div>
              <div>
                <label className={labelCls}>저장할 프로젝트 *</label>
                <select className={inputCls} value={projectId} onChange={e => setProjectId(e.target.value)}>
                  {projects.length === 0 && <option value="">프로젝트 없음</option>}
                  {projects.map(p => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
                {projects.length === 0 && (
                  <p className="mt-1 text-[11px] text-[#F04452]">
                    저장할 프로젝트가 없어요. 프로젝트를 먼저 만든 뒤 생성할 수 있어요.
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
        {step === totalSteps - 1 && !allValid && (
          <p className="mt-2 text-[11px] text-[#F04452]">
            필수 항목을 입력해주세요: {missing.join(', ')}
          </p>
        )}
        <div className="flex gap-2 mt-3">
          {step > 0 && (
            <button onClick={() => setStep(step - 1)} className="px-3 py-2 rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] text-sm text-[#8B95A1]">
              이전
            </button>
          )}
          {step < totalSteps - 1 ? (
            <button onClick={() => setStep(step + 1)} disabled={!stepValid} className={btnCls}>
              다음
            </button>
          ) : (
            <button onClick={run} disabled={!allValid} className={btnCls}>
              광고 생성 실행
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
        onClick={() => genId && router.push(`/generations/${genId}`)}
        className={`${cardCls} w-full text-left hover:border-[#3182F6] transition-colors`}
        title="클릭하면 생성 페이지에서 자세히 봐요"
      >
        <div className="flex items-center gap-3">
          <div className="w-6 h-6 border-[3px] border-[#E5E8EB] dark:border-[#2D3748] border-t-[#3182F6] dark:border-t-[#5B9DF9] rounded-full animate-spin" />
          <div className="flex-1">
            <p className="text-sm text-[#191F28] dark:text-[#F2F4F6]">{stageMsg}</p>
            <div className="mt-1.5 h-1.5 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] overflow-hidden">
              <div className="h-full bg-[#3182F6] transition-all duration-300" style={{ width: `${pct}%` }} />
            </div>
          </div>
          <span className="text-xs text-[#8B95A1]">{pct}%</span>
        </div>
        {/* G1 — 무엇을 생성 중인지 입력 확인(상품·타깃) */}
        {(name || target) && (
          <p className="text-[11px] text-[#4E5968] dark:text-[#9CA3AF] mt-2 truncate">
            🎨 {name || '광고'}
            {target ? ` · 타깃 ${target}` : ''}
          </p>
        )}
        <p className="text-[10px] text-[#B0B8C1] mt-1">클릭하면 전체 화면에서 진행을 봐요 →</p>
      </button>
    );
  }

  if (phase === 'error') {
    return (
      <div className={cardCls}>
        <p className="text-sm text-[#F04452]">광고 생성 실패: {err}</p>
        <button onClick={() => setPhase('form')} className="mt-2 text-xs text-[#3182F6]">
          다시 시도
        </button>
      </div>
    );
  }

  // phase === 'done'
  const cands = detail?.candidates ?? [];
  return (
    <div className={cardCls}>
      <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-2">
        ✅ 광고 시안 {cands.length}개 생성 완료
      </p>
      <ul className="space-y-1.5">
        {cands.slice(0, 3).map(c => (
          <li key={c.candidate_id} className="rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D] px-3 py-2 text-sm">
            <span className="text-[10px] text-[#8B95A1]">{c.strategy?.strategy_type}</span>
            <p className="text-[#191F28] dark:text-[#F2F4F6] truncate">{c.copy?.headline}</p>
          </li>
        ))}
      </ul>
      {genId && (
        <button
          onClick={() => router.push(`/generations/${genId}`)}
          className="mt-3 w-full py-2 rounded-lg border border-[#3182F6]/30 text-[#3182F6] text-sm font-semibold hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors"
        >
          상세 보기 →
        </button>
      )}
    </div>
  );
}
