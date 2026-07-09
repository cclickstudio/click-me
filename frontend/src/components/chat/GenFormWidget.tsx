'use client';

// 채팅 안 광고 생성 입력 위젯 — 단계별 폼 → api.generator.start → 진행률 → 결과 요약(+상세 링크)
// 생성은 project_id 필수(라우터 400)라 프로젝트 선택을 포함한다.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { useProjects } from '@/components/ProjectContext';
import { getJobs, setGenJob } from '@/lib/runningJobs';
import type { GenerationDetail, Project } from '@/lib/types';

type Phase = 'form' | 'running' | 'done' | 'error';
type Initial = {
  mode?: 'create' | 'improve'; // improve면 시뮬 결과 기반 개선 폼(단일 카드)
  product_name?: string;
  product_description?: string;
  target_audience?: string;
  campaign_objective?: string;
  // 개선(improve) 프리필 — 백엔드 improve_context가 시뮬에서 조립.
  // product_cutout_s3_key는 채팅 경로에서 추적 불가라 없음(백엔드 null 폴백).
  simulation_summary?: string;
  plain_summary?: string | null;
  improvement_direction?: string;
  existing_ad_s3_key?: string | null;
  product_cutout_s3_key?: string | null; // 생성한 광고로 시뮬한 경우 누끼 재사용(그 외 null)
  fix_requests?: string | null;
};

// 진행 중 생성 id 보관 키(G4) — 동시 1개 정책이라 단일 키로 충분(새로고침 복원용).
const ACTIVE_GEN_KEY = 'clickme_active_gen';

const inputCls =
  'w-full px-3 py-2 rounded-lg border border-line text-sm bg-surface-2 text-ink focus:outline-none focus:border-primary';
const labelCls = 'text-[11px] font-semibold text-ink-tertiary mb-1 block';
const cardCls =
  'mt-1 w-full rounded-xl border border-line bg-card p-4';
// 광고 목표 칩 — /generator 페이지의 OBJECTIVES·칩 컨벤션과 동일
const OBJECTIVES = [
  { value: 'awareness', label: '브랜드 인지' },
  { value: 'conversion', label: '구매 전환' },
  { value: 'lead_gen', label: '리드 수집' },
  { value: 'app_install', label: '앱 설치' },
  { value: 'retention', label: '재구매 유도' },
  { value: 'product_launch', label: '신제품 런칭' },
  { value: 'promotion', label: '프로모션 반응' },
];
const chipBase =
  'px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors';
const chipActive = 'border-primary bg-primary-subtle text-primary';
const chipIdle = 'border-line text-ink-tertiary hover:border-primary';
const btnCls =
  'flex-1 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary-hover disabled:opacity-40 transition-colors';

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
  const [genId, setGenId] = useState<string | null>(null);
  const [name, setName] = useState(initial?.product_name ?? '');
  const [desc, setDesc] = useState(initial?.product_description ?? '');
  const [target, setTarget] = useState(initial?.target_audience ?? '');
  const [objective, setObjective] = useState(initial?.campaign_objective ?? 'conversion');
  const [fixRequests, setFixRequests] = useState(initial?.fix_requests ?? '');
  const isImprove = initial?.mode === 'improve';
  const [image] = useState<File | null>(initialImage ?? null);
  const [imagePreview] = useState<string | null>(() =>
    initialImage ? URL.createObjectURL(initialImage) : null,
  );
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState('');
  const { refreshDetails } = useProjects(); // 완료 시 좌측 패널의 제너 목록 갱신용
  const [pct, setPct] = useState(0);
  const [stageMsg, setStageMsg] = useState('준비 중...');
  const [detail, setDetail] = useState<GenerationDetail | null>(null);
  const [err, setErr] = useState('');
  const esRef = useRef<EventSource | null>(null);
  const phaseRef = useRef(phase); // 콜백에서 최신 phase 참조(N3 동기화 가드)
  phaseRef.current = phase;

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
          if (projectId) refreshDetails(projectId); // 완료 생성물을 패널에 즉시 반영
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
    if (isImprove) {
      if (!initial?.simulation_summary || !projectId) return;
    } else if (!name.trim() || !desc.trim() || !target.trim() || !projectId) {
      return;
    }
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
      const body = isImprove
        ? {
            mode: 'improve',
            project_id: projectId,
            product_name: name,
            simulation_summary: initial?.simulation_summary ?? '',
            plain_summary: initial?.plain_summary ?? null,
            improvement_direction: initial?.improvement_direction || null,
            existing_ad_s3_key: initial?.existing_ad_s3_key ?? null,
            product_cutout_s3_key: initial?.product_cutout_s3_key ?? null,
            fix_requests: fixRequests.trim() || null,
            campaign_objective: objective,
          }
        : {
            product_name: name,
            product_description: desc,
            target_audience: target,
            campaign_objective: objective,
            project_id: projectId,
            product_image_temp_key: productImageTempKey ?? null,
          };
      const { generation_id } = (await api.generator.start(body)) as { generation_id: string };
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

  // 진행 중 generation_id(localStorage)가 있으면 상태 조회 후 스피너/결과로 복원(G4·N3 공용).
  // 유휴(form) 상태에서만 동작 — 이미 진행/완료를 다루는 중이면 무시(중복 구독 방지).
  const restoreFromKey = useCallback(async () => {
    if (!latest || phaseRef.current !== 'form') return;
    const gid = localStorage.getItem(ACTIVE_GEN_KEY);
    if (!gid) return;
    try {
      const d = (await api.generator.detail(gid)) as GenerationDetail;
      if (phaseRef.current !== 'form') return;
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
      /* 일시 실패 — 키 유지(다음 트리거에 재시도) */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latest]);

  // 새로고침 복원(G4) + 타 탭·탭 복귀 동기화(N3) — 마운트·storage(타 탭 localStorage 변경)·
  // visibilitychange(백그라운드→복귀) 시 진행 상태를 다시 맞춘다.
  useEffect(() => {
    void restoreFromKey();
    const onStorage = (e: StorageEvent) => {
      if (e.key === ACTIVE_GEN_KEY) void restoreFromKey();
    };
    const onVisible = () => {
      if (document.visibilityState === 'visible') void restoreFromKey();
    };
    window.addEventListener('storage', onStorage);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.removeEventListener('storage', onStorage);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [restoreFromKey]);

  // 개선(improve) 폼 — 단계 없는 단일 카드. 시뮬 요약은 읽기 전용, 수정 요청만 입력받는다.
  if (phase === 'form' && isImprove) {
    return (
      <div className={cardCls}>
        <p className="text-sm font-semibold text-ink mb-3">
          🔄 시뮬 결과 기반 개선 생성{initial?.product_name ? ` — ${initial.product_name}` : ''}
        </p>
        <div className="space-y-2">
          <div>
            <label className={labelCls}>시뮬레이션 결과</label>
            <p className="text-sm text-ink rounded-lg bg-surface-1 px-3 py-2">
              {initial?.simulation_summary}
            </p>
          </div>
          {initial?.improvement_direction && (
            <div>
              <label className={labelCls}>개선 방향 (토론 권고)</label>
              <p className="text-[12px] text-ink-secondary whitespace-pre-line rounded-lg bg-surface-1 px-3 py-2 max-h-24 overflow-y-auto">
                {initial.improvement_direction}
              </p>
            </div>
          )}
          {initial?.plain_summary && (
            <details className="text-[12px] text-ink-secondary">
              <summary className="cursor-pointer text-[11px] font-semibold text-ink-tertiary">AI 분석 보기</summary>
              <p className="mt-1 whitespace-pre-line rounded-lg bg-surface-1 px-3 py-2 max-h-24 overflow-y-auto">
                {initial.plain_summary}
              </p>
            </details>
          )}
          <div>
            <label className={labelCls}>수정 요청사항 (선택)</label>
            <textarea
              className={`${inputCls} resize-none`}
              rows={2}
              value={fixRequests}
              onChange={e => setFixRequests(e.target.value)}
              placeholder="예: 가격 강조 문구를 빼주세요"
            />
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
        <div className="flex gap-2 mt-3">
          <button onClick={run} disabled={!initial?.simulation_summary || !projectId} className={btnCls}>
            개선 시안 생성
          </button>
        </div>
      </div>
    );
  }

  if (phase === 'form') {
    // 백엔드 필수값(상품명·상품설명·타깃·저장 프로젝트)과 일치 — 누락 시 실행 차단·안내.
    const missing: string[] = [];
    if (!name.trim()) missing.push('상품명');
    if (!desc.trim()) missing.push('상품 설명');
    if (!target.trim()) missing.push('타깃 고객');
    if (!projectId) missing.push('저장할 프로젝트');
    const allValid = missing.length === 0;
    return (
      <div className={cardCls}>
        <p className="text-sm font-semibold text-ink mb-3">🎨 광고 생성 정보 입력</p>
        {imagePreview && (
          <div className="mb-3 flex items-center gap-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={imagePreview} alt="첨부 이미지" className="w-12 h-12 rounded-lg object-cover border border-line" />
            <span className="text-[11px] text-ink-tertiary">채팅에서 첨부한 이미지를 상품 이미지로 사용해요</span>
          </div>
        )}
        <div className="space-y-3">
          <div>
            <label className={labelCls}>상품명 *</label>
            <input className={inputCls} value={name} onChange={e => setName(e.target.value)} placeholder="예: 클릭미 수분크림" autoFocus />
          </div>
          <div>
            <label className={labelCls}>상품 설명 *</label>
            <textarea className={`${inputCls} resize-none`} rows={3} value={desc} onChange={e => setDesc(e.target.value)} placeholder="상품 특징·강점" />
          </div>
          <div>
            <label className={labelCls}>타깃 고객 *</label>
            <input className={inputCls} value={target} onChange={e => setTarget(e.target.value)} placeholder="예: 20-30대 건성 피부 여성" />
          </div>
          <div>
            <label className={labelCls}>광고 목표 *</label>
            <div className="flex flex-wrap gap-1.5">
              {OBJECTIVES.map(o => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => setObjective(o.value)}
                  className={`${chipBase} ${objective === o.value ? chipActive : chipIdle}`}
                >
                  {o.label}
                </button>
              ))}
            </div>
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
        {!allValid && (
          <p className="mt-2 text-[11px] text-[#F04452]">
            필수 항목을 입력해주세요: {missing.join(', ')}
          </p>
        )}
        <div className="flex gap-2 mt-3">
          <button onClick={run} disabled={!allValid} className={btnCls}>
            광고 생성 실행
          </button>
        </div>
      </div>
    );
  }

  if (phase === 'running') {
    return (
      <button
        type="button"
        onClick={() => genId && router.push(`/generations/${genId}`)}
        className={`${cardCls} w-full text-left hover:border-primary transition-colors`}
        title="클릭하면 생성 페이지에서 자세히 봐요"
      >
        <div className="flex items-center gap-3">
          <div className="w-6 h-6 border-[3px] border-line border-t-primary dark:border-t-[#5B9DF9] rounded-full animate-spin" />
          <div className="flex-1">
            <p className="text-sm text-ink">{stageMsg}</p>
            <div className="mt-1.5 h-1.5 rounded-full bg-surface-1 overflow-hidden">
              <div className="h-full bg-primary transition-all duration-300" style={{ width: `${pct}%` }} />
            </div>
          </div>
          <span className="text-xs text-ink-tertiary">{pct}%</span>
        </div>
        {/* G1 — 무엇을 생성 중인지 입력 확인(상품·타깃) */}
        {(name || target) && (
          <p className="text-[11px] text-ink-secondary mt-2 truncate">
            🎨 {name || '광고'}
            {target ? ` · 타깃 ${target}` : ''}
          </p>
        )}
        <p className="text-[10px] text-ink-muted mt-1">클릭하면 전체 화면에서 진행을 봐요 →</p>
      </button>
    );
  }

  if (phase === 'error') {
    return (
      <div className={cardCls}>
        <p className="text-sm text-[#F04452]">광고 생성 실패: {err}</p>
        <button onClick={() => setPhase('form')} className="mt-2 text-xs text-primary">
          다시 시도
        </button>
      </div>
    );
  }

  // phase === 'done'
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
      {genId && (
        <button
          onClick={() => router.push(`/generations/${genId}`)}
          className="mt-3 w-full py-2 rounded-lg border border-primary/30 text-primary text-sm font-semibold hover:bg-primary-subtle transition-colors"
        >
          상세 보기 →
        </button>
      )}
    </div>
  );
}
