'use client';

// 채팅 안 시뮬레이션 입력 위젯 — 폼 입력 → api.simulation.start → 진행률 → 결과 요약(+상세 링크)
// 새로고침해도 백그라운드 실행 중이면 run_id(localStorage) + 상태 조회로 스피너를 복원한다.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { safeRandomUUID } from '@/lib/utils';
import { getJobs, setSimJob } from '@/lib/runningJobs';
import { SIM_CATEGORIES } from '@/lib/simCategories';
import type { AnalysisMode, SimRunResult } from '@/lib/types';

type Phase = 'form' | 'running' | 'done' | 'error';

// 3-모드 분석(A-1, /simulation 이식) — persona_set은 세그먼트 편집이 필요해 채팅에선 미지원,
// 고르면 전체 페이지로 안내한다(아래 렌더 분기 참조).
const MODE_TABS: { value: AnalysisMode; label: string; desc: string }[] = [
  { value: 'synthetic', label: '전체 합성', desc: '조건에 맞는 가상 소비자 표본 전체의 반응을 예측합니다.' },
  { value: 'individual', label: '1명 심층', desc: '가상 소비자 1명을 깊이 있게 분석합니다.' },
  { value: 'persona_set', label: '세그먼트 비교', desc: '여러 세그먼트를 나란히 비교합니다 — 채팅에선 지원하지 않아 전체 페이지로 이동해요.' },
];

// 진행 중 시뮬 run_id 보관 키 — 동시 1개 정책이라 단일 키로 충분(새로고침 복원용).
const ACTIVE_SIM_KEY = 'chat_active_sim_run';

const inputCls =
  'w-full px-3 py-2 rounded-lg border border-line text-sm bg-surface-2 text-ink focus:outline-none focus:border-primary';
const labelCls = 'text-[11px] font-semibold text-ink-tertiary mb-1 block';

// 칩 스타일(/simulation 컨벤션 이식).
const chipBase = 'px-2.5 py-1.5 rounded-lg border text-[11px] font-medium transition-colors';
const chipActive = 'border-primary bg-primary-subtle text-primary';
const chipIdle =
  'border-line text-ink-tertiary hover:border-primary';

// 광고 목표 — 일반인도 쉽게 고르는 단일 선택(/simulation의 AD_GOALS 이식).
const AD_GOALS = ['관심 유도', '클릭 유도', '가입·문의 유도', '구매 전환', '재구매·단골'];

// 5단계 진행 인디케이터 라벨(W3 — 사용자가 현재 위치·남은 단계를 한눈에).
const STEP_LABELS = ['제품명', '광고 설명', '카테고리', '광고 목표', '대상 설정'];

// 연령대 → age_min/age_max 변환(다중 선택 시 하한~상한 범위).
const AGE_BANDS: { label: string; min: number; max: number }[] = [
  { label: '10대', min: 14, max: 19 },
  { label: '20대', min: 20, max: 29 },
  { label: '30대', min: 30, max: 39 },
  { label: '40대', min: 40, max: 49 },
  { label: '50대', min: 50, max: 59 },
  { label: '60대 이상', min: 60, max: 84 },
];

export default function SimFormWidget({
  initial,
  initialImage,
  initialImageUrl,
  projectId,
  latest,
  onSimComplete,
}: {
  initial?: {
    ad_content?: string;
    ad_title?: string;
    product_category?: string;
    ad_objective?: string;
    analysis_mode?: AnalysisMode;
  };
  initialImage?: File; // 채팅에서 첨부한 광고 이미지
  initialImageUrl?: string; // 생성 시안 등에서 넘어온 이미지 URL(파일 대신 URL로 시뮬)
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
  // 3-모드 분석 — persona_set은 채팅 미지원(아래 렌더에서 전체 페이지로 안내).
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>(
    initial?.analysis_mode ?? 'synthetic',
  );
  const [adTitle, setAdTitle] = useState(initial?.ad_title ?? '');
  const [adContent, setAdContent] = useState(initial?.ad_content ?? '');
  // 카테고리 — /simulation과 동일한 2단 셀렉트(업종 대분류 → NICE 류).
  // initial.product_category(이름)가 대분류명과 일치하면 대분류만 미리 선택(세부 류는 미보유).
  const [categoryId, setCategoryId] = useState<number | ''>(
    () => SIM_CATEGORIES.find(c => c.name === initial?.product_category)?.id ?? '',
  );
  const [serviceClass, setServiceClass] = useState<number | ''>('');
  const categoryName = SIM_CATEGORIES.find(c => c.id === categoryId)?.name ?? '';
  // 광고 목표 — 칩 단일 선택 + 기타 직접 입력. initial이 칩 값이면 그 칩, 아니면 기타로.
  const _initGoalMatched = AD_GOALS.includes(initial?.ad_objective ?? '');
  const [goalItem, setGoalItem] = useState<string>(
    _initGoalMatched ? (initial?.ad_objective as string) : initial?.ad_objective ? '기타' : '',
  );
  const [customGoal, setCustomGoal] = useState(_initGoalMatched ? '' : (initial?.ad_objective ?? ''));
  const objectiveValue = goalItem === '기타' ? customGoal.trim() : goalItem;
  // 인구 생성 — 표본 수/추출 방식/연령대/성별(/simulation 이식).
  const [allocation, setAllocation] = useState<'proportional' | 'stratified'>('proportional');
  const [ageBands, setAgeBands] = useState<string[]>([]);
  const [gender, setGender] = useState<'' | 'F' | 'M'>('');
  const [image, setImage] = useState<File | null>(initialImage ?? null);
  const [imagePreview, setImagePreview] = useState<string | null>(() =>
    initialImage ? URL.createObjectURL(initialImage) : (initialImageUrl ?? null),
  );
  // 생성 시안 등 URL 기반 이미지 — 파일 업로드가 있으면 파일이 우선한다.
  const imageUrl = initialImageUrl ?? '';
  const hasImage = !!image || !!imageUrl;
  const previewSrc = imagePreview ?? (imageUrl || null);
  const [sampleSize, setSampleSize] = useState(20);
  const [pct, setPct] = useState(0);
  const [stageMsg, setStageMsg] = useState('준비 중...');
  const [err, setErr] = useState('');
  const esRef = useRef<EventSource | null>(null);
  const phaseRef = useRef(phase); // 콜백에서 최신 phase 참조(N3 동기화 가드)
  phaseRef.current = phase;
  const completeFiredRef = useRef(false); // onSimComplete 1회 보장(SSE completed·onerror 중복 방지)
  const streamRetryRef = useRef(0); // onerror 재구독 횟수 가드(무한 재구독 방지)

  const finish = async (rid: string) => {
    setSimJob(null); // 완료 — 동시실행 슬롯 해제
    localStorage.removeItem(ACTIVE_SIM_KEY);
    try {
      const r = await api.simulation.result(rid);
      setPhase('done');
      // 결과를 채팅 컨트롤러로 넘겨 결과 요약 위젯 + 토론을 별도 메시지로 띄운다(1회만).
      if (!completeFiredRef.current) {
        completeFiredRef.current = true;
        onSimComplete?.(r, {
          adTitle,
          adContent,
          category: categoryName,
          objective: objectiveValue,
          sampleSize,
        });
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
        streamRetryRef.current = 0; // 정상 수신 — 재구독 예산 회복
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
    es.onerror = async () => {
      es.close();
      // 스트림 끊김 — 완료/진행/실패를 상태로 확인해 분기.
      // ★ 새로고침·언로드로 끊긴 경우: 여기서 ACTIVE_SIM_KEY를 동기 삭제하면 안 됨
      //   (그러면 새 페이지의 복원 로직이 진행중 런을 못 찾음). 비동기 상태 확인으로
      //   언로드 시엔 키를 보존하고, 페이지가 살아있을 때만 완료/실패를 확정한다.
      try {
        const st = await api.simulation.status(rid);
        if (st.status === 'COMPLETED') {
          void finish(rid); // 완료라 끊긴 것 — 결과 조회
        } else if (st.status === 'RUNNING') {
          // 진행 중인데 네트워크 블립으로 끊긴 경우 — 한정 횟수 재구독(키 유지 → 새로고침 복원).
          if (esRef.current === es && streamRetryRef.current < 5) {
            streamRetryRef.current += 1;
            subscribe(rid);
          }
        } else {
          setSimJob(null);
          localStorage.removeItem(ACTIVE_SIM_KEY);
          setErr('실행 오류');
          setPhase('error');
        }
      } catch {
        /* 상태 확인 실패 — 키 유지(다음 새로고침에 복원 시도). */
      }
    };
  };

  // 진행 중 run_id(localStorage)가 있으면 상태 조회 후 스피너/결과로 복원(새로고침·N3 공용).
  // 유휴(form) 상태에서만 동작 — 이미 진행/완료를 다루는 중이면 무시(중복 구독 방지).
  const restoreFromKey = useCallback(async () => {
    if (!latest || phaseRef.current !== 'form') return;
    const rid = localStorage.getItem(ACTIVE_SIM_KEY);
    if (!rid) return;
    try {
      const st = await api.simulation.status(rid);
      if (phaseRef.current !== 'form') return;
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
      /* 일시 실패 — 키 유지(다음 트리거에 재시도) */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latest]);

  // 새로고침 복원 + 타 탭·탭 복귀 동기화(N3) — 마운트·storage(타 탭 localStorage 변경)·
  // visibilitychange(백그라운드→복귀) 시 진행 상태를 다시 맞춘다.
  useEffect(() => {
    void restoreFromKey();
    const onStorage = (e: StorageEvent) => {
      if (e.key === ACTIVE_SIM_KEY) void restoreFromKey();
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

  // 언마운트 시 스트림 정리(슬롯은 유지 — 백그라운드 런 동시실행 방지).
  useEffect(() => () => esRef.current?.close(), []);

  const onPickImage = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setImage(f);
    setImagePreview(URL.createObjectURL(f));
  };

  const run = async () => {
    if (!adTitle.trim() || !adContent.trim() || !hasImage) return;
    if (getJobs().sim) {
      setErr('이미 다른 시뮬레이션이 진행 중이에요. 끝난 뒤 다시 시도하세요.');
      setPhase('error');
      return;
    }
    setPhase('running');
    setPct(0);
    setStageMsg('시뮬레이션 시작...');
    // 연령대·성별을 고르면 그 조건(MANUAL), 아무것도 안 고르면 자동 추정(AUTO).
    const targetFilter: Record<string, unknown> = {};
    const bands = AGE_BANDS.filter(b => ageBands.includes(b.label));
    if (bands.length > 0) {
      targetFilter.age_min = Math.min(...bands.map(b => b.min));
      targetFilter.age_max = Math.max(...bands.map(b => b.max));
    }
    if (gender) targetFilter.gender = gender;
    const targetMode = bands.length > 0 || gender !== '' ? 'MANUAL' : 'AUTO';
    try {
      const { run_id } = await api.simulation.start({
        ad_id: `chat-${safeRandomUUID()}`,
        ad_title: adTitle || undefined,
        ad_content: adContent,
        ad_image: image ?? undefined,
        // 파일이 없고 URL 이미지(생성 시안 등)만 있으면 URL을 VLM 입력으로 전달.
        ad_image_url: !image && imageUrl ? imageUrl : undefined,
        project_id: projectId || undefined, // 프로젝트 귀속 → DB 저장(없으면 메모리 런)
        product_category: categoryName || undefined,
        service_class: typeof serviceClass === 'number' ? serviceClass : undefined,
        ad_objective: objectiveValue || undefined,
        // individual은 표본 1명 고정(/simulation 이식).
        sample_size: analysisMode === 'individual' ? 1 : sampleSize,
        allocation,
        target_filter: targetFilter,
        target_mode: targetMode,
        analysis_mode: analysisMode,
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
    'mt-1 w-full rounded-xl border border-line bg-card p-4';

  if (phase === 'form') {
    const totalSteps = 5;
    // 0 제품명·1 광고설명 필수, 2 카테고리(대분류+세부 류), 3 광고 목표(칩 또는 기타 입력) 필수.
    const canNext =
      (step !== 0 || adTitle.trim().length > 0) &&
      (step !== 1 || adContent.trim().length > 0) &&
      (step !== 2 || (categoryId !== '' && serviceClass !== '')) &&
      (step !== 3 || objectiveValue.length > 0);
    const btnCls =
      'flex-1 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary-hover disabled:opacity-40 transition-colors';
    // Enter로 다음 단계(마지막 단계는 실행). textarea 줄바꿈은 Shift+Enter.
    const goNext = () => {
      if (step < totalSteps - 1) {
        if (canNext) setStep(step + 1);
      } else if (adTitle.trim() && adContent.trim() && hasImage) {
        void run();
      }
    };
    const onFormKeyDown = (e: React.KeyboardEvent) => {
      if (e.key !== 'Enter' || e.shiftKey) return;
      e.preventDefault();
      goNext();
    };
    // 모드 탭 — persona_set(세그먼트 비교)은 채팅에서 미지원, 고르면 전체 페이지로 안내.
    const modeTabs = (
      <div className="mb-3">
        <label className={labelCls}>분석 모드</label>
        <div className="flex flex-wrap gap-1.5">
          {MODE_TABS.map(m => (
            <button
              key={m.value}
              type="button"
              onClick={() => setAnalysisMode(m.value)}
              className={`${chipBase} ${analysisMode === m.value ? chipActive : chipIdle}`}
            >
              {m.label}
            </button>
          ))}
        </div>
        <p className="text-[11px] text-ink-tertiary mt-1.5">
          {MODE_TABS.find(m => m.value === analysisMode)?.desc}
        </p>
      </div>
    );

    if (analysisMode === 'persona_set') {
      return (
        <div className={cardCls}>
          {modeTabs}
          <p className="text-sm text-ink">
            세그먼트 비교는 세그먼트별로 조건을 나눠 편집해야 해서 채팅에서는 지원하지 않아요.
            전체 페이지에서 진행해주세요.
          </p>
          <button
            onClick={() => router.push('/simulation')}
            className="mt-3 w-full py-2 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary-hover transition-colors"
          >
            시뮬레이션 페이지로 이동 →
          </button>
        </div>
      );
    }
    return (
      <div className={cardCls} onKeyDown={onFormKeyDown}>
        {modeTabs}
        <div className="mb-3">
          <p className="text-sm font-semibold text-ink">
            🧪 시뮬레이션 정보 입력{' '}
            <span className="text-[11px] font-normal text-ink-tertiary">
              {step + 1}/{totalSteps} · {STEP_LABELS[step]}
            </span>
          </p>
          {/* 단계 진행 인디케이터 — 완료 단계는 클릭해 되돌아갈 수 있음. */}
          <div className="mt-2 flex items-center gap-1.5">
            {STEP_LABELS.map((lbl, i) => {
              const done = i < step;
              const current = i === step;
              return (
                <button
                  key={lbl}
                  type="button"
                  onClick={() => done && setStep(i)}
                  disabled={!done}
                  title={lbl}
                  aria-label={`${i + 1}단계 ${lbl}${current ? ' (현재)' : done ? ' (완료)' : ''}`}
                  className={`h-1.5 flex-1 rounded-full transition-colors ${
                    current
                      ? 'bg-primary'
                      : done
                        ? 'bg-primary/50 hover:bg-primary cursor-pointer'
                        : 'bg-surface-1 cursor-default'
                  }`}
                />
              );
            })}
          </div>
        </div>
        <div className="mb-3">
          <label className={labelCls}>광고 이미지 *</label>
          {previewSrc ? (
            <div className="flex items-center gap-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={previewSrc} alt="광고 이미지" className="w-12 h-12 rounded-lg object-cover border border-line" />
              <label className="text-xs text-primary cursor-pointer hover:underline">
                이미지 변경
                <input type="file" accept="image/*" className="hidden" onChange={onPickImage} />
              </label>
            </div>
          ) : (
            <label className="flex items-center justify-center gap-2 py-3 rounded-lg border border-dashed border-line text-xs text-ink-tertiary cursor-pointer hover:border-primary hover:text-primary transition-colors">
              + 광고 이미지 업로드 (필수)
              <input type="file" accept="image/*" className="hidden" onChange={onPickImage} />
            </label>
          )}
        </div>
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
            <div className="space-y-2">
              <div>
                <label className={labelCls}>카테고리 *</label>
                <div className="grid grid-cols-2 gap-2">
                  <select
                    className={inputCls}
                    value={categoryId}
                    onChange={e => {
                      setCategoryId(e.target.value ? Number(e.target.value) : '');
                      setServiceClass('');
                    }}
                    autoFocus
                  >
                    <option value="">대분류 선택</option>
                    {SIM_CATEGORIES.map(c => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                  <select
                    className={`${inputCls} disabled:opacity-50`}
                    value={serviceClass}
                    onChange={e => setServiceClass(e.target.value ? Number(e.target.value) : '')}
                    disabled={categoryId === ''}
                  >
                    <option value="">세부 분류 (NICE)</option>
                    {(SIM_CATEGORIES.find(c => c.id === categoryId)?.kinds ?? []).map(k => (
                      <option key={k.id} value={k.id}>
                        {k.id}류 · {k.description}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          )}
          {step === 3 && (
            <div>
              <label className={labelCls}>광고 목표 *</label>
              <div className="flex flex-wrap gap-1.5">
                {AD_GOALS.map(g => (
                  <button
                    key={g}
                    type="button"
                    onClick={() => setGoalItem(g)}
                    className={`${chipBase} ${goalItem === g ? chipActive : chipIdle}`}
                  >
                    {g}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => setGoalItem('기타')}
                  className={`${chipBase} ${goalItem === '기타' ? chipActive : chipIdle}`}
                >
                  기타
                </button>
              </div>
              {goalItem === '기타' && (
                <input
                  className={`${inputCls} mt-2`}
                  value={customGoal}
                  onChange={e => setCustomGoal(e.target.value)}
                  placeholder="광고 목표를 직접 입력하세요"
                  autoFocus
                />
              )}
            </div>
          )}
          {step === 4 && (
            <div className="space-y-3">
              {analysisMode === 'individual' ? (
                <p className="text-[11px] text-ink-tertiary">
                  1명 심층 분석 — 표본 1명 고정. 아래 조건(연령대·성별)으로 그 1명을 고릅니다.
                </p>
              ) : (
                <div>
                  <label className={labelCls}>가상 소비자 수: {sampleSize}명</label>
                  <input type="range" min={1} max={200} value={sampleSize} onChange={e => setSampleSize(Number(e.target.value))} className="w-full accent-[#3182F6]" />
                </div>
              )}
              <div>
                <label className={labelCls}>표본 추출 방식</label>
                <div className="flex gap-1.5">
                  {(
                    [
                      ['proportional', '인구 비례'],
                      ['stratified', '소수 그룹 보강'],
                    ] as ['proportional' | 'stratified', string][]
                  ).map(([v, lbl]) => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => setAllocation(v)}
                      className={`${chipBase} ${allocation === v ? chipActive : chipIdle}`}
                    >
                      {lbl}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className={labelCls}>연령대 (선택 · 복수 가능)</label>
                <div className="flex flex-wrap gap-1.5">
                  {AGE_BANDS.map(b => {
                    const on = ageBands.includes(b.label);
                    return (
                      <button
                        key={b.label}
                        type="button"
                        onClick={() =>
                          setAgeBands(prev =>
                            on ? prev.filter(x => x !== b.label) : [...prev, b.label],
                          )
                        }
                        className={`${chipBase} ${on ? chipActive : chipIdle}`}
                      >
                        {b.label}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div>
                <label className={labelCls}>성별 (선택)</label>
                <div className="flex gap-1.5">
                  {(
                    [
                      ['', '전체'],
                      ['F', '여성'],
                      ['M', '남성'],
                    ] as ['' | 'F' | 'M', string][]
                  ).map(([v, lbl]) => (
                    <button
                      key={lbl}
                      type="button"
                      onClick={() => setGender(v)}
                      className={`${chipBase} ${gender === v ? chipActive : chipIdle}`}
                    >
                      {lbl}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
        <div className="flex gap-2 mt-3">
          {step > 0 && (
            <button onClick={() => setStep(step - 1)} className="px-3 py-2 rounded-lg border border-line text-sm text-ink-tertiary">
              이전
            </button>
          )}
          {step < totalSteps - 1 ? (
            <button onClick={() => setStep(step + 1)} disabled={!canNext} className={btnCls}>
              다음
            </button>
          ) : (
            <button onClick={run} disabled={!adTitle.trim() || !adContent.trim() || !hasImage} className={btnCls}>
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
        className={`${cardCls} w-full text-left hover:border-primary transition-colors`}
        title="클릭하면 시뮬레이션 페이지에서 자세히 봐요"
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
        <p className="text-[10px] text-ink-muted mt-2">클릭하면 전체 화면에서 진행을 봐요 →</p>
      </button>
    );
  }

  if (phase === 'error') {
    return (
      <div className={cardCls}>
        <p className="text-sm text-[#F04452]">시뮬레이션 실패: {err}</p>
        <button onClick={() => setPhase('form')} className="mt-2 text-xs text-primary">
          다시 시도
        </button>
      </div>
    );
  }

  // phase === 'done' — 결과 요약·토론은 아래 별도 메시지(sim_result·debate_stream)로 이어진다.
  return (
    <div className={cardCls}>
      <p className="text-sm font-semibold text-ink">✅ 시뮬레이션 완료</p>
      <p className="mt-1 text-[12px] text-ink-tertiary">아래에서 결과 요약과 토론을 확인하세요.</p>
    </div>
  );
}
