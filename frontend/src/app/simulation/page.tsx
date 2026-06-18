'use client';
// 도메인 시뮬레이터(/api/simulation/run) 동기 실행 화면 — 광고 입력 → 반응·루브릭·집계 표시

import { useState, useRef, useEffect } from 'react';
import AppLayout from '@/components/AppLayout';
import { useProjects } from '@/components/ProjectContext';
import { DebatePanel } from '@/components/simulator/DebatePanel';
import { KpiCard } from '@/components/ui/KpiCard';
import { formatPercent } from '@/lib/utils';
import { api } from '@/lib/api';
import { SIM_CATEGORIES } from '@/lib/simCategories';
import type { SimRunResult, SSEProgressEvent } from '@/lib/types';

type Step = 'setup' | 'running' | 'result';
type InputMode = 'image' | 'url' | 'none';
type GenderFilter = '' | 'M' | 'F';

/* ─── enum 한글 라벨(백엔드 contracts/enums.py 동기화) ─── */
const EMOTION_LABEL: Record<string, string> = {
  curiosity: '호기심',
  delight: '즐거움',
  empathy: '공감',
  trust: '신뢰',
  indifference: '무관심',
  annoyance: '거부감',
  distrust: '불신',
  other: '기타',
};
const REJECTION_LABEL: Record<string, string> = {
  irrelevant: '무관함',
  offensive: '불쾌함',
  overpriced: '비쌈',
  overpromise: '과장',
  distrust: '불신',
  ad_fatigue: '광고 피로',
  other: '기타',
};
const DROP_LABEL: Record<string, string> = {
  no_reason_to_explore: '탐색 동기 없음',
  price_concern: '가격 부담',
  low_relevance: '낮은 관련성',
  unclear_message: '메시지 불명확',
  distrust: '불신',
  other: '기타',
};
const GENDER_LABEL: Record<string, string> = { M: '남성', F: '여성' };
const OCEAN_LABEL: Record<string, string> = {
  openness: '개방성',
  conscientiousness: '성실성',
  extraversion: '외향성',
  agreeableness: '친화성',
  neuroticism: '신경성',
};

/* ─── 광고 목표(일반인도 쉽게 고르는 단일 선택) ─── */
const AD_GOALS: { value: string; label: string; desc: string }[] = [
  {
    value: '관심 유도',
    label: '관심 유도',
    desc: '브랜드·제품을 더 많은 사람에게 알리고 흥미를 끕니다.',
  },
  {
    value: '클릭 유도',
    label: '클릭 유도',
    desc: '사이트·콘텐츠 방문이나 영상 시청을 유도합니다.',
  },
  {
    value: '가입·문의 유도',
    label: '가입·문의 유도',
    desc: '회원가입·상담·자료 신청 등 잠재고객을 확보합니다.',
  },
  {
    value: '구매 전환',
    label: '구매 전환',
    desc: '실제 구매·결제·예약 같은 전환을 늘립니다.',
  },
  {
    value: '재구매·단골',
    label: '재구매·단골',
    desc: '기존 고객의 재구매·구독 유지로 단골을 만듭니다.',
  },
];

/* ─── 공통 스타일(기존 simulation 페이지 컨벤션) ─── */
const labelCls =
  'block text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] mb-1.5';
const sectionTitle =
  'text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-2';
const chipBase =
  'px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors';
const chipActive =
  'border-[#3182F6] bg-[#EEF4FF] dark:bg-[#1E3A5F] text-[#3182F6]';
const chipIdle =
  'border-[#E5E8EB] dark:border-[#2D3748] text-[#8B95A1] dark:text-[#6B7280] hover:border-[#3182F6]';
const inputCls =
  'w-full px-3 py-2.5 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#252D3D] text-sm text-[#191F28] dark:text-[#F2F4F6] focus:outline-none focus:ring-2 focus:ring-[#3182F6] placeholder:text-[#B0B8C1] dark:placeholder:text-[#4B5563] transition-colors';
const cardCls =
  'bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 transition-colors';

/* ─── 연령대 → age_min/age_max 변환 (다중 선택 시 하한~상한 범위) ─── */
const AGE_BANDS: { label: string; min: number; max: number }[] = [
  { label: '10대', min: 14, max: 19 },
  { label: '20대', min: 20, max: 29 },
  { label: '30대', min: 30, max: 39 },
  { label: '40대', min: 40, max: 49 },
  { label: '50대', min: 50, max: 59 },
  { label: '60대 이상', min: 60, max: 84 },
];

function aisasFunnel(a: SimRunResult['reactions'][number]['aisas']): string {
  const stages: [keyof typeof a, string][] = [
    ['attention', 'A'],
    ['interest', 'I'],
    ['search', 'S'],
    ['action', 'A'],
    ['share', 'S'],
  ];
  return stages.map(([k, label]) => (a[k] ? label : '·')).join('');
}

export default function SimulationRunPage() {
  const { selectedProject } = useProjects();
  const [step, setStep] = useState<Step>('setup');

  // 광고 입력
  const [adId, setAdId] = useState(`AD-${Date.now()}`);
  const [adContent, setAdContent] = useState('');
  const [inputMode, setInputMode] = useState<InputMode>('none');
  const [file, setFile] = useState<File | null>(null);
  const [imageUrl, setImageUrl] = useState('');
  const [adTitle, setAdTitle] = useState('');
  const [categoryId, setCategoryId] = useState<number | ''>('');
  const [serviceClass, setServiceClass] = useState<number | ''>('');
  const categories = SIM_CATEGORIES; // 하드코딩 마스터(DB/API 대체).
  // 광고 목표 — 일반인도 쉽게 고르는 단일 선택.
  const [goalItem, setGoalItem] = useState('');

  // 시뮬레이션 설정
  const [sampleSize, setSampleSize] = useState(20);
  const [targetMode, setTargetMode] = useState<'AUTO' | 'MANUAL'>('AUTO');
  const [allocation, setAllocation] = useState<'proportional' | 'stratified'>(
    'proportional'
  );
  const [ageBands, setAgeBands] = useState<string[]>([]);
  const [gender, setGender] = useState<GenderFilter>('');

  const [result, setResult] = useState<SimRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showFailed, setShowFailed] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  // SSE 진행률 — 실행 중 단계·퍼센트 표시.
  const [pct, setPct] = useState(0);
  const [stageMsg, setStageMsg] = useState('');
  const esRef = useRef<EventSource | null>(null);

  // 언마운트 시 스트림 정리.
  useEffect(() => () => esRef.current?.close(), []);

  const toggleExpand = (id: string) =>
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  async function run() {
    setError(null);
    setPct(0);
    setStageMsg('');
    setStep('running');
    const targetFilter: Record<string, unknown> = {};
    // 직접 지정일 때만 타깃 조건 반영. 연령대 → 선택 구간들의 하한~상한.
    if (targetMode === 'MANUAL') {
      const bands = AGE_BANDS.filter(b => ageBands.includes(b.label));
      if (bands.length > 0) {
        targetFilter.age_min = Math.min(...bands.map(b => b.min));
        targetFilter.age_max = Math.max(...bands.map(b => b.max));
      }
      if (gender) targetFilter.gender = gender;
    }

    try {
      // 비동기 시작 → run_id 받고 SSE로 진행률 구독(결과는 completed 후 GET).
      const { run_id } = await api.simulation.start({
        ad_id: adId.trim() || `AD-${Date.now()}`,
        ad_content: adContent || undefined,
        ad_image: inputMode === 'image' ? file : undefined,
        ad_image_url: inputMode === 'url' ? imageUrl || undefined : undefined,
        project_id: selectedProject?.id ?? undefined,
        target_filter: targetFilter,
        target_mode: targetMode,
        sample_size: sampleSize,
        allocation,
        ad_title: adTitle || undefined,
        product_category:
          categories.find(c => c.id === categoryId)?.name || undefined,
        service_class:
          typeof serviceClass === 'number' ? serviceClass : undefined,
        ad_objective: goalItem || undefined,
      });

      const es = api.simulation.stream(run_id);
      esRef.current = es;

      const STAGE_LABEL: Record<string, string> = {
        ad_analysis: '광고 해석 중...',
        panel: '페르소나 패널 로드 중...',
        reaction: '페르소나 반응 생성 중...',
        aggregate: '결과 집계 중...',
      };

      es.onmessage = (ev: MessageEvent) => {
        let data: SSEProgressEvent;
        try {
          data = JSON.parse(ev.data) as SSEProgressEvent;
        } catch {
          return;
        }

        if (data.event === 'error') {
          setError(data.message ?? '시뮬레이션 진행 중 오류');
          es.close();
          esRef.current = null;
          setStep('setup');
          return;
        }

        if (typeof data.pct === 'number') setPct(data.pct);
        // reaction 단계는 message("반응 N/total")가 더 구체적이라 우선.
        if (data.stage)
          setStageMsg(data.message ?? STAGE_LABEL[data.stage] ?? '');

        if (data.event === 'completed') {
          setPct(100);
          es.close();
          esRef.current = null;
          api.simulation
            .result(run_id)
            .then(r => {
              setResult(r);
              setStep('result');
            })
            .catch(e => {
              setError(e instanceof Error ? e.message : '결과 조회 실패');
              setStep('setup');
            });
        }
      };

      es.onerror = () => {
        if (esRef.current) {
          setError('스트림 연결이 끊겼습니다.');
          es.close();
          esRef.current = null;
          setStep('setup');
        }
      };
    } catch (e) {
      setError(e instanceof Error ? e.message : '시뮬레이션 실행 실패');
      setStep('setup');
    }
  }

  /* ─── STEP: setup ─── */
  if (step === 'setup') {
    const previewUrl = file ? URL.createObjectURL(file) : null;
    return (
      <AppLayout>
        <div className='px-8 py-8 max-w-5xl mx-auto'>
          <div className='mb-6'>
            <h1 className='text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]'>
              시뮬레이터 실행
            </h1>
            <p className='text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1'>
              AI 가상 소비자에게 광고 반응을 미리 테스트합니다
            </p>
          </div>

          {error && (
            <div className='mb-5 px-4 py-2.5 bg-[#FEF2F2] dark:bg-[#3B0D0D] rounded-xl border border-[#FECACA] dark:border-[#7F1D1D] text-sm text-[#DC2626] dark:text-[#FCA5A5]'>
              {error}
            </div>
          )}

          <div className='grid grid-cols-[1fr_1fr] gap-5 items-start'>
            {/* ── 왼쪽: 광고 입력 ── */}
            <div className={`${cardCls} flex flex-col gap-5`}>
              <p className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]'>
                광고 입력
              </p>

              <div>
                <label className={labelCls}>
                  광고 제품명 <span className='text-[#F74D4D]'>*</span>
                </label>
                <input
                  type='text'
                  value={adTitle}
                  onChange={e => setAdTitle(e.target.value)}
                  placeholder='제로콜라 제로슈거'
                  className={inputCls}
                />
              </div>

              <div>
                <label className={labelCls}>제품 설명</label>
                <textarea
                  value={adContent}
                  onChange={e => setAdContent(e.target.value)}
                  rows={4}
                  placeholder='제품 특징이나 광고 카피를 입력하세요. 이미지 없이 텍스트만으로도 해석됩니다.'
                  className={`${inputCls} resize-none`}
                />
              </div>

              {/* 이미지 입력 방식 */}
              <div>
                <label className={labelCls}>광고 이미지 (선택)</label>
                <div className='flex gap-2 mb-3'>
                  {(
                    [
                      ['none', '없음'],
                      ['image', '파일 업로드'],
                      ['url', '이미지 URL'],
                    ] as [InputMode, string][]
                  ).map(([m, lbl]) => (
                    <button
                      key={m}
                      type='button'
                      onClick={() => setInputMode(m)}
                      className={`${chipBase} ${inputMode === m ? chipActive : chipIdle}`}>
                      {lbl}
                    </button>
                  ))}
                </div>

                {inputMode === 'image' && (
                  <label className='flex flex-col items-center justify-center h-40 border-2 border-dashed border-[#E5E8EB] dark:border-[#2D3748] rounded-xl cursor-pointer hover:border-[#3182F6] transition-colors overflow-hidden'>
                    {previewUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={previewUrl}
                        alt='미리보기'
                        className='w-full h-full object-contain'
                      />
                    ) : (
                      <span className='text-sm text-[#8B95A1] dark:text-[#6B7280]'>
                        클릭하여 이미지 선택 (최대 10MB)
                      </span>
                    )}
                    <input
                      type='file'
                      accept='image/*'
                      className='hidden'
                      onChange={e => setFile(e.target.files?.[0] ?? null)}
                    />
                  </label>
                )}
                {inputMode === 'url' && (
                  <input
                    type='text'
                    value={imageUrl}
                    onChange={e => setImageUrl(e.target.value)}
                    placeholder='https://example.com/ad.png'
                    className={inputCls}
                  />
                )}
              </div>

              {/* 제품 카테고리 & 세부 분류 */}
              <div>
                <label className={labelCls}>제품 카테고리 (선택)</label>
                <div className='grid grid-cols-2 gap-3'>
                  <select
                    value={categoryId}
                    onChange={e => {
                      setCategoryId(
                        e.target.value ? Number(e.target.value) : ''
                      );
                      setServiceClass('');
                    }}
                    className={inputCls}>
                    <option value=''>대분류 선택</option>
                    {categories.map(c => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                  <select
                    value={serviceClass}
                    onChange={e =>
                      setServiceClass(
                        e.target.value ? Number(e.target.value) : ''
                      )
                    }
                    disabled={!categoryId}
                    className={`${inputCls} disabled:opacity-50`}>
                    <option value=''>세부 분류 (NICE)</option>
                    {(
                      categories.find(c => c.id === categoryId)?.kinds ?? []
                    ).map(k => (
                      <option key={k.id} value={k.id}>
                        {k.id}류 · {k.description}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* 광고 목표 — 쉬운 단일 선택(칩) */}
              <div>
                <label className={labelCls}>광고 목표 (선택)</label>
                <div className='flex flex-wrap gap-2'>
                  {AD_GOALS.map(g => (
                    <button
                      key={g.value}
                      type='button'
                      onClick={() =>
                        setGoalItem(goalItem === g.value ? '' : g.value)
                      }
                      className={`${chipBase} ${goalItem === g.value ? chipActive : chipIdle}`}>
                      {g.label}
                    </button>
                  ))}
                </div>
                <p className='text-[11px] text-[#8B95A1] dark:text-[#6B7280] mt-1.5'>
                  {AD_GOALS.find(g => g.value === goalItem)?.desc ??
                    '이 광고로 가장 원하는 결과를 하나 고르세요. 광고가 의도대로 전달됐는지 함께 비교합니다.'}
                </p>
              </div>
            </div>

            {/* ── 오른쪽: 시뮬레이션 설정 ── */}
            <div className={`${cardCls} flex flex-col gap-5`}>
              <p className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]'>
                시뮬레이션 설정
              </p>

              {/* 표본 수 */}
              <div className='bg-[#F9FAFB] dark:bg-[#252D3D] border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl px-4 py-4'>
                <label className={labelCls}>
                  가상 소비자 수:{' '}
                  <span className='text-[#3182F6] font-bold'>
                    {sampleSize}명
                  </span>
                </label>
                <input
                  type='range'
                  min={1}
                  max={200}
                  value={sampleSize}
                  onChange={e => setSampleSize(Number(e.target.value))}
                  className='w-full accent-[#3182F6] mt-1'
                />
                <div className='flex justify-between text-[10px] text-[#B0B8C1] dark:text-[#4B5563] mt-1'>
                  <span>1명</span>
                  <span>200명</span>
                </div>
              </div>

              {/* 표본 추출 방식 */}
              <div>
                <p className={sectionTitle}>표본 추출 방식</p>
                <div className='flex gap-2'>
                  {(
                    [
                      ['proportional', '인구 비례 (기본)'],
                      ['stratified', '소수 그룹 보강'],
                    ] as ['proportional' | 'stratified', string][]
                  ).map(([v, lbl]) => (
                    <button
                      key={v}
                      type='button'
                      onClick={() => setAllocation(v)}
                      className={`${chipBase} ${allocation === v ? chipActive : chipIdle}`}>
                      {lbl}
                    </button>
                  ))}
                </div>
                <p className='text-[11px] text-[#8B95A1] dark:text-[#6B7280] mt-1.5'>
                  {allocation === 'proportional'
                    ? '실제 인구 비율대로 뽑습니다 (기본 권장).'
                    : '소수 그룹도 충분히 포함되게 보강합니다 (정밀하지만 신뢰구간이 넓어짐).'}
                </p>
              </div>
            </div>
          </div>

          {/* ── 타깃 설정 (전체 너비) ── */}
          <div className={`${cardCls} flex flex-col gap-5 mt-5`}>
            <p className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]'>
              타깃 설정
            </p>
            <div className='grid grid-cols-1 md:grid-cols-3 gap-5'>
              {/* 타깃 지정 방식 */}
              <div>
                <p className={sectionTitle}>타깃 지정 방식</p>
                <div className='flex gap-2'>
                  {(
                    [
                      ['AUTO', '자동'],
                      ['MANUAL', '직접 지정'],
                    ] as ['AUTO' | 'MANUAL', string][]
                  ).map(([v, lbl]) => (
                    <button
                      key={v}
                      type='button'
                      onClick={() => setTargetMode(v)}
                      className={`${chipBase} ${targetMode === v ? chipActive : chipIdle}`}>
                      {lbl}
                    </button>
                  ))}
                </div>
              </div>

              {/* 타깃 조건(연령대·성별) — 직접 지정(MANUAL)일 때만 표시 */}
              {targetMode === 'MANUAL' && (
                <>
                  <div>
                    <p className={sectionTitle}>
                      연령대{' '}
                      <span className='text-[10px] font-normal text-[#B0B8C1] dark:text-[#4B5563]'>
                        복수 선택 가능
                      </span>
                    </p>
                    <div className='flex flex-wrap gap-2'>
                      {AGE_BANDS.map(b => {
                        const on = ageBands.includes(b.label);
                        return (
                          <button
                            key={b.label}
                            type='button'
                            onClick={() =>
                              setAgeBands(prev =>
                                on
                                  ? prev.filter(x => x !== b.label)
                                  : [...prev, b.label]
                              )
                            }
                            className={`${chipBase} ${on ? chipActive : chipIdle}`}>
                            {b.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div>
                    <p className={sectionTitle}>
                      성별{' '}
                      <span className='text-[10px] font-normal text-[#B0B8C1] dark:text-[#4B5563]'>
                        선택
                      </span>
                    </p>
                    <div className='flex gap-2'>
                      {(
                        [
                          ['', '전체'],
                          ['F', '여성'],
                          ['M', '남성'],
                        ] as [GenderFilter, string][]
                      ).map(([v, lbl]) => (
                        <button
                          key={lbl}
                          type='button'
                          onClick={() => setGender(v)}
                          className={`${chipBase} ${gender === v ? chipActive : chipIdle}`}>
                          {lbl}
                        </button>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* ── 실행 버튼 (하단 전체 너비) ── */}
          <div className='mt-5'>
            <button
              onClick={run}
              disabled={!adTitle.trim()}
              className='w-full flex items-center justify-center gap-2 py-3.5 bg-[#3182F6] hover:bg-[#1B6EEB] disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl text-sm font-semibold transition-colors'>
              <svg className='w-4 h-4' fill='currentColor' viewBox='0 0 24 24'>
                <path d='M8 5v14l11-7z' />
              </svg>
              시뮬레이터 실행
            </button>
            <p className='text-[11px] text-[#B0B8C1] dark:text-[#4B5563] text-center mt-2'>
              가상 소비자 수에 따라 수 초~수십 초 걸립니다.
            </p>
          </div>
        </div>
      </AppLayout>
    );
  }

  /* ─── STEP: running ─── */
  if (step === 'running') {
    return (
      <AppLayout>
        <div className='px-8 py-8 max-w-5xl mx-auto'>
          <div className={`${cardCls} flex flex-col gap-6 py-16`}>
            <div className='flex flex-col items-center gap-4'>
              <div className='w-10 h-10 border-4 border-[#E5E8EB] dark:border-[#2D3748] border-t-[#3182F6] rounded-full animate-spin' />
              <p className='text-sm font-medium text-[#4E5968] dark:text-[#9CA3AF]'>
                {stageMsg || `${sampleSize}명 페르소나가 광고에 반응하는 중...`}
              </p>
            </div>
            <div className='w-full max-w-md mx-auto space-y-2'>
              <div className='flex justify-between text-xs'>
                <span className='text-[#8B95A1] dark:text-[#6B7280]'>
                  진행률
                </span>
                <span className='font-medium text-[#191F28] dark:text-[#F2F4F6]'>
                  {pct}%
                </span>
              </div>
              <div className='w-full bg-[#F2F4F6] dark:bg-[#252D3D] rounded-full h-2 overflow-hidden'>
                <div
                  className='h-full bg-[#3182F6] rounded-full transition-all duration-300'
                  style={{ width: `${pct}%` }}
                />
              </div>
              <p className='text-xs text-[#B0B8C1] dark:text-[#4B5563] text-center pt-1'>
                광고 해석 → 패널 로드 → 반응 생성 → 집계
              </p>
            </div>
          </div>
        </div>
      </AppLayout>
    );
  }

  /* ─── STEP: result ─── */
  if (step === 'result' && result) {
    const agg = result.aggregate;
    const reactions = result.reactions ?? [];
    const passed = reactions.filter(r => r.qa_passed);
    const failed = reactions.filter(r => !r.qa_passed);
    const ad = result.ad_analysis;
    const shown = showFailed ? reactions : passed;
    const personaMap = new Map(
      (result.personas ?? []).map(p => [p.persona_id, p])
    );

    return (
      <AppLayout>
        <div className='px-8 py-8 max-w-7xl mx-auto space-y-6'>
          <div className='flex items-center justify-between'>
            <div>
              <h1 className='text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]'>
                시뮬레이터 결과
              </h1>
              <p className='text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1'>
                run_id {result.run_id.slice(0, 8)} · 반응 {reactions.length}건
                (QA 통과 {passed.length})
                {result.simulation_id && ' · DB 저장됨'}
              </p>
            </div>
            <button
              onClick={() => {
                setStep('setup');
                setResult(null);
                setAdId(`AD-${Date.now()}`);
              }}
              className='px-4 py-2 border border-[#E5E8EB] dark:border-[#2D3748] rounded-lg text-sm text-[#8B95A1] dark:text-[#6B7280] hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors'>
              새 시뮬레이션
            </button>
          </div>

          {/* 4대 KPI */}
          {agg && (
            <>
              <div className='grid grid-cols-2 md:grid-cols-4 gap-4'>
                <KpiCard
                  label='클릭 의향률 (AISAS Action)'
                  value={formatPercent(agg.click_intent_rate)}
                  sub={`95% CI ${formatPercent(agg.ci_low)} ~ ${formatPercent(agg.ci_high)}`}
                />
                <KpiCard
                  label='구매의도 (1~5 평균)'
                  value={agg.purchase_intent.toFixed(2)}
                  sub={agg.variance_warning ? '⚠ 응답 집중 경고' : undefined}
                  trend={agg.variance_warning ? 'down' : 'neutral'}
                />
                <KpiCard
                  label='신뢰도 (1~5 평균)'
                  value={agg.trust_avg.toFixed(2)}
                />
                <KpiCard
                  label='거부율'
                  value={formatPercent(agg.rejection_rate)}
                  trend={agg.rejection_rate > 0.3 ? 'down' : 'neutral'}
                />
              </div>
              <div className='flex flex-wrap gap-2 text-xs'>
                <span className='px-3 py-1 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]'>
                  유효표본수(effective_n) {agg.effective_n}
                </span>
                <span className='px-3 py-1 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]'>
                  집계 엔진 {agg.engine_version}
                </span>
                {ad?.intent_mismatch && (
                  <span className='px-3 py-1 rounded-full bg-[#FFF8E6] dark:bg-[#2D2000] text-[#F4A100]'>
                    ⚠ 의도-반응 불일치 감지
                  </span>
                )}
              </div>
            </>
          )}

          {/* 분석 데이터(왼쪽) + 토론(오른쪽) 가로 배치 */}
          <div className='grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch'>
            {/* 왼쪽: 분석 데이터 */}
            <div className='space-y-6'>
              {/* 광고 해석 */}
              {ad && (
                <div className={cardCls}>
                  <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-3'>
                    광고 해석 (VLM/LLM 감지)
                  </h2>
                  <div className='grid grid-cols-2 md:grid-cols-4 gap-3 text-sm'>
                    {[
                      ['감지 업종', ad.detected_industry],
                      ['감지 목표', ad.detected_objective],
                      ['감지 타깃', ad.detected_target],
                      ['감지 메시지', ad.detected_message],
                    ].map(([k, v]) => (
                      <div key={k}>
                        <p className='text-xs text-[#8B95A1] dark:text-[#6B7280]'>
                          {k}
                        </p>
                        <p className='text-[#191F28] dark:text-[#F2F4F6] mt-0.5'>
                          {v || '—'}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 루브릭 */}
              {result.rubric_scores.length > 0 && (
                <div className={cardCls}>
                  <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-3'>
                    루브릭 평가 (차원별 점수)
                  </h2>
                  <div className='space-y-2.5'>
                    {result.rubric_scores.map(s => (
                      <div
                        key={s.dimension}
                        className='flex items-center gap-3'>
                        <span className='w-40 text-xs text-[#4E5968] dark:text-[#9CA3AF] truncate'>
                          {s.dimension}
                        </span>
                        <div className='flex-1 h-2 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] overflow-hidden'>
                          <div
                            className='h-full bg-[#3182F6] rounded-full'
                            style={{ width: `${s.score}%` }}
                          />
                        </div>
                        <span className='w-10 text-right text-xs font-semibold text-[#191F28] dark:text-[#F2F4F6]'>
                          {s.score}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 페르소나 반응 */}
              <div className={cardCls}>
                <div className='flex items-center justify-between mb-3'>
                  <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]'>
                    페르소나 반응 ({shown.length})
                  </h2>
                  {failed.length > 0 && (
                    <button
                      onClick={() => setShowFailed(v => !v)}
                      className='text-xs text-[#8B95A1] dark:text-[#6B7280] hover:text-[#3182F6]'>
                      {showFailed
                        ? 'QA 통과분만 보기'
                        : `QA 탈락 ${failed.length}건 포함`}
                    </button>
                  )}
                </div>
                <div className='space-y-3 max-h-[600px] overflow-y-auto'>
                  {shown.map(r => {
                    const p = personaMap.get(r.persona_id);
                    const isOpen = expanded.has(r.persona_id);
                    return (
                      <div
                        key={r.persona_id}
                        className={`border-l-2 pl-3 py-1 ${
                          r.qa_passed
                            ? 'border-[#3182F6]'
                            : 'border-[#F04452] opacity-60'
                        }`}>
                        {/* 페르소나 기본 정보 */}
                        <div className='flex flex-wrap items-center gap-2 text-[11px] mb-1'>
                          <button
                            type='button'
                            onClick={() => p && toggleExpand(r.persona_id)}
                            className='font-medium text-[#191F28] dark:text-[#F2F4F6] hover:text-[#3182F6]'>
                            {p ? (
                              <>
                                {p.age}세 {GENDER_LABEL[p.gender] ?? p.gender} ·{' '}
                                {p.region}
                                <span className='ml-1 text-[#B0B8C1] dark:text-[#4B5563]'>
                                  {isOpen ? '▲' : '▼'}
                                </span>
                              </>
                            ) : (
                              r.persona_id
                            )}
                          </button>
                          <span className='text-[10px] text-[#B0B8C1] dark:text-[#4B5563]'>
                            {r.persona_id}
                          </span>
                        </div>

                        {/* 반응 요약 */}
                        <div className='flex flex-wrap items-center gap-2 text-[11px] mb-1'>
                          <span className='font-mono text-[#3182F6]'>
                            {aisasFunnel(r.aisas)}
                          </span>
                          <span className='text-[#4E5968] dark:text-[#9CA3AF]'>
                            구매 {r.purchase_intent}·신뢰 {r.trust}
                          </span>
                          <span className='px-1.5 py-0.5 rounded bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]'>
                            {EMOTION_LABEL[r.emotion_tag] ?? r.emotion_tag}
                          </span>
                          {r.rejected && (
                            <span className='px-1.5 py-0.5 rounded bg-[#FEF2F2] dark:bg-[#3B0D0D] text-[#DC2626]'>
                              거부
                              {r.rejection_reason_tag
                                ? `·${REJECTION_LABEL[r.rejection_reason_tag] ?? r.rejection_reason_tag}`
                                : ''}
                            </span>
                          )}
                          {r.drop_stage && (
                            <span className='text-[#B0B8C1] dark:text-[#4B5563]'>
                              이탈 {r.drop_stage}
                              {r.drop_reason_tag
                                ? `·${DROP_LABEL[r.drop_reason_tag] ?? r.drop_reason_tag}`
                                : ''}
                            </span>
                          )}
                          {r.exposure_context && (
                            <span className='text-[#B0B8C1] dark:text-[#4B5563]'>
                              노출 {r.exposure_context}
                            </span>
                          )}
                          {!r.qa_passed && (
                            <span className='text-[#F04452]'>
                              QA 탈락
                              {r.qa_fail_reason ? `·${r.qa_fail_reason}` : ''}
                            </span>
                          )}
                        </div>

                        {r.utterance && (
                          <p className='text-sm text-[#4E5968] dark:text-[#9CA3AF]'>
                            {r.utterance}
                          </p>
                        )}

                        {/* 페르소나 상세 (펼침) */}
                        {isOpen && p && (
                          <div className='mt-2 p-3 rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D] text-[11px] space-y-2'>
                            <div>
                              <span className='text-[#8B95A1] dark:text-[#6B7280]'>
                                OCEAN
                              </span>
                              <div className='flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5 text-[#4E5968] dark:text-[#9CA3AF]'>
                                {Object.entries(p.ocean).map(([dim, v]) => (
                                  <span key={dim}>
                                    {OCEAN_LABEL[dim] ?? dim} {v.toFixed(2)}
                                  </span>
                                ))}
                              </div>
                            </div>
                            {Object.keys(p.consumption_values).length > 0 && (
                              <div>
                                <span className='text-[#8B95A1] dark:text-[#6B7280]'>
                                  소비가치
                                </span>
                                <p className='mt-0.5 text-[#4E5968] dark:text-[#9CA3AF] break-all'>
                                  {JSON.stringify(p.consumption_values)}
                                </p>
                              </div>
                            )}
                            {Object.keys(p.media_behavior).length > 0 && (
                              <div>
                                <span className='text-[#8B95A1] dark:text-[#6B7280]'>
                                  미디어 행동
                                </span>
                                <p className='mt-0.5 text-[#4E5968] dark:text-[#9CA3AF] break-all'>
                                  {JSON.stringify(p.media_behavior)}
                                </p>
                              </div>
                            )}
                            {Object.keys(p.socioeconomic).length > 0 && (
                              <div>
                                <span className='text-[#8B95A1] dark:text-[#6B7280]'>
                                  사회경제
                                </span>
                                <p className='mt-0.5 text-[#4E5968] dark:text-[#9CA3AF] break-all'>
                                  {JSON.stringify(p.socioeconomic)}
                                </p>
                              </div>
                            )}
                            {p.profile_narrative && (
                              <div>
                                <span className='text-[#8B95A1] dark:text-[#6B7280]'>
                                  프로필 서사
                                </span>
                                <p className='mt-0.5 text-[#4E5968] dark:text-[#9CA3AF]'>
                                  {p.profile_narrative}
                                </p>
                              </div>
                            )}
                            <span className='inline-block text-[10px] text-[#B0B8C1] dark:text-[#4B5563]'>
                              가중치 {p.weight}
                            </span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* 오른쪽: 토론 (채팅 + 결과 박스, 자체 height 고정) */}
            <div>
              <DebatePanel
                reactions={reactions}
                adAnalysis={ad ?? null}
                personas={result.personas ?? []}
                simulationId={result.simulation_id}
              />
            </div>
          </div>

          {/* 최종 결과 (리포트 — 추후 박스 추가 예정, 지금은 자리만) */}
          <div className={cardCls}>
            <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-2'>
              최종 결과
            </h2>
            <p className='text-xs text-[#8B95A1] dark:text-[#6B7280]'>
              리포트가 준비되면 여기에 표시됩니다.
            </p>
          </div>

          <p className='text-xs text-[#B0B8C1] dark:text-[#4B5563] border-t border-[#E5E8EB] dark:border-[#2D3748] pt-4'>
            본 결과는 AI 시뮬레이션 기반 예측이며 의사결정 보조 근거입니다. 클릭
            의향률은 실측 CTR이 아닙니다(calibration 전).
          </p>
        </div>
      </AppLayout>
    );
  }

  return null;
}
