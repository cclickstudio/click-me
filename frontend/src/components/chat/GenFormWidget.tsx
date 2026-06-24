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
}: {
  initial?: Initial;
  initialImage?: File; // 채팅에서 첨부한 상품 이미지
  // 완료 시 결과 요약(+결과 참조)을 채팅으로 보내 내역 영속화·다음 단계 제안
  onResult?: (summary: string, resultRef?: { kind: 'sim' | 'gen'; id: string }) => void;
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

  const finish = async (gid: string) => {
    setGenJob(null);
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
      if (onResult) {
        onResult(`[생성결과] 광고 시안 ${(d.candidates ?? []).length}개 생성 완료`, {
          kind: 'gen',
          id: gid,
        });
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : '결과 조회 실패');
      setPhase('error');
    }
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
      const es = api.generator.stream(generation_id);
      esRef.current = es;
      es.onmessage = ev => {
        try {
          const d = JSON.parse(ev.data) as { event?: string; pct?: number; message?: string };
          if (typeof d.pct === 'number') setPct(d.pct);
          if (d.message) setStageMsg(d.message);
          if (d.event === 'completed') {
            es.close();
            void finish(generation_id);
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
      es.onerror = () => {
        es.close();
        void finish(generation_id);
      };
    } catch (e) {
      setGenJob(null);
      setErr(e instanceof Error ? e.message : '시작 실패');
      setPhase('error');
    }
  };

  if (phase === 'form') {
    const totalSteps = 4;
    const stepValid = [name.trim(), desc.trim(), target.trim(), projectId][step];
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
              </div>
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
            <button onClick={() => setStep(step + 1)} disabled={!stepValid} className={btnCls}>
              다음
            </button>
          ) : (
            <button onClick={run} disabled={!projectId} className={btnCls}>
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
