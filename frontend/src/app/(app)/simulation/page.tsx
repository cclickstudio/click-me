'use client';
// 도메인 시뮬레이터(/api/simulation/run) 동기 실행 화면 — 광고 입력 → 반응·루브릭·집계 표시

import { useState, useRef, useEffect, useLayoutEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useProjects } from '@/components/ProjectContext';
import { CreateProjectModal } from '@/components/ProjectPanel';
import { goalFromObjective } from '@/lib/metaObjective';
import { useChatController } from '@/components/chat/ChatController';
import ErrorCard from '@/components/chat/ErrorCard';
import { openReconnectingStream } from '@/lib/sse';
import { api, getAdminOrgId } from '@/lib/api';
import { saveSimComparison, saveSimResult } from '@/lib/simResultStore';
import { getJobs, setSimJob } from '@/lib/runningJobs';
import { SIM_CATEGORIES } from '@/lib/simCategories';
import { Select } from '@/components/ui/Select';
import type {
  AnalysisMode,
  SegmentInput,
  SimRunResult,
  SSEProgressEvent,
} from '@/lib/types';

type Step = 'setup' | 'running';
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
// 진행 중 run_id(localStorage) — 다른 탭 이동 후 복귀 시 SSE 재구독용(백엔드는 asyncio.create_task로
// 이미 이 페이지 SSE 연결과 무관하게 계속 돈다. 여기선 화면 복원만 담당).
const ACTIVE_SIM_KEY = 'sim_page_active_run';
const STAGE_LABEL: Record<string, string> = {
  ad_analysis: '광고 해석 중...',
  panel: '페르소나 패널 로드 중...',
  reaction: '페르소나 반응 생성 중...',
  aggregate: '결과 집계 중...',
};

type InputMode = 'image' | 'generated' | 'campaign';
type GenderFilter = '' | 'M' | 'F';

/* ─── 3-모드 분석(A-1) 탭 정의 ─── */
const MODE_TABS: { value: AnalysisMode; label: string; desc: string }[] = [
  {
    value: 'synthetic',
    label: '전체 합성',
    desc: '조건에 맞는 가상 소비자 표본 전체의 반응을 예측합니다.',
  },
  {
    value: 'individual',
    label: '1명 심층',
    desc: '가상 소비자 1명을 깊이 있게 분석합니다 (프로필 서사·반응 근거).',
  },
  {
    value: 'persona_set',
    label: '세그먼트 비교',
    desc: '여러 세그먼트를 나란히 비교해 어떤 타깃에 잘 통하는지 봅니다.',
  },
];

// persona_set 세그먼트 편집 행 — 라벨·연령대 1개·성별·표본수.
type SegmentDraft = {
  label: string;
  ageBand: string; // AGE_BANDS의 label 또는 '' (전 연령)
  gender: GenderFilter;
  sampleSize: number;
};

const emptySegment = (label: string): SegmentDraft => ({
  label,
  ageBand: '',
  gender: '',
  sampleSize: 20,
});

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
  'block text-xs font-semibold text-ink-secondary mb-1.5';
const sectionTitle =
  'text-sm font-semibold text-ink mb-2';
const chipBase =
  'px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors';
const chipActive =
  'border-primary bg-primary-subtle text-primary';
const chipIdle =
  'border-line text-ink-tertiary hover:border-primary';
const inputCls =
  'w-full px-3 py-2.5 rounded-xl border border-line bg-surface-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-primary placeholder:text-ink-muted dark:placeholder:text-ink-muted transition-colors';
const cardCls =
  'bg-card border border-line rounded-2xl p-6 transition-colors';

/* ─── 연령대 → age_min/age_max 변환 (다중 선택 시 하한~상한 범위) ─── */
const AGE_BANDS: { label: string; min: number; max: number }[] = [
  { label: '10대', min: 14, max: 19 },
  { label: '20대', min: 20, max: 29 },
  { label: '30대', min: 30, max: 39 },
  { label: '40대', min: 40, max: 49 },
  { label: '50대', min: 50, max: 59 },
  { label: '60대 이상', min: 60, max: 84 },
];

export default function SimulationRunPage() {
  const { projects, refreshDetails, refresh, loading: projectsLoading } = useProjects();
  // 화면 내 프로젝트 선택은 로컬 상태 — 사이드바(전역 선택)와 동기화하지 않는다.
  // 진입 시 전역 선택(localStorage)을 초기값으로만 읽고, 이후 변경은 이 화면에만 반영된다.
  const [localProjectId, setLocalProjectId] = useState<string | null>(null);
  useEffect(() => {
    setLocalProjectId(localStorage.getItem('selectedProjectId'));
  }, []);
  const selectedProject = projects.find(p => p.id === localProjectId) ?? null;
  const selectProject = (id: string | null) => setLocalProjectId(id);

  const router = useRouter();
  // N2 — 안읽음 뱃지: 직접 실행 완료로 채팅에 제안을 주입할 때 플로팅이 닫혀 있으면
  // pushUnread로 빨간 뱃지를 올린다. 닫힘 여부는 최신값을 ref로 읽는다(완료 콜백 클로저 staleness 회피).
  const { pushUnread, floatingOpen } = useChatController();
  const floatingOpenRef = useRef(floatingOpen);
  useEffect(() => {
    floatingOpenRef.current = floatingOpen;
  }, [floatingOpen]);
  const [step, setStep] = useState<Step>('setup');

  // 3-모드 분석(A-1) — synthetic(기본)·individual(1명)·persona_set(세그먼트 비교)
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>('synthetic');
  const [segments, setSegments] = useState<SegmentDraft[]>([
    emptySegment('세그먼트 A'),
    emptySegment('세그먼트 B'),
  ]);

  // Individual 모드 — 페르소나 지정 선택(미지정이면 기존대로 타깃 조건에서 자동 추출).
  const [personaPickerOpen, setPersonaPickerOpen] = useState(false);
  const [pickedPersona, setPickedPersona] = useState<{
    persona_id: string;
    age: number;
    gender: string;
    region: string;
    narrative_snippet: string;
  } | null>(null);
  const [personaOptions, setPersonaOptions] = useState<
    { persona_id: string; age: number; gender: string; region: string; narrative_snippet: string }[]
  >([]);
  const [personaOptionsTotal, setPersonaOptionsTotal] = useState(0);
  const [personaOptionsLoading, setPersonaOptionsLoading] = useState(false);

  // 광고 입력
  const [adId] = useState(`AD-${Date.now()}`);
  const [adContent, setAdContent] = useState('');
  const [inputMode, setInputMode] = useState<InputMode>('image');
  const [file, setFile] = useState<File | null>(null);
  // '생성한 광고' 입력 — 선택 프로젝트의 성공한 생성 후보(제품명-후보N) 목록
  const [genOptions, setGenOptions] = useState<
    { value: string; label: string; imageUrl: string }[]
  >([]);
  const [selectedGenValue, setSelectedGenValue] = useState('');
  const [genLoading, setGenLoading] = useState(false);
  const selectedGenImageUrl =
    genOptions.find(o => o.value === selectedGenValue)?.imageUrl ?? '';
  // '집행중 광고' 입력 — 집행 캠페인 소재(Meta) 이미지·카피 prefill
  const [campaigns, setCampaigns] = useState<{ campaign_id: string; name: string; state: string }[]>(
    [],
  );
  const [campaignsLoading, setCampaignsLoading] = useState(false);
  const [selectedCampaignId, setSelectedCampaignId] = useState('');
  const [campaignImageUrl, setCampaignImageUrl] = useState('');
  const [campaignImgError, setCampaignImgError] = useState(false);
  // 선택 캠페인의 Meta 실측 도달수(원값) — 표본 상한과 별개로 슬라이더 라벨에 표시.
  const [campaignReach, setCampaignReach] = useState<number | null>(null);
  // from_campaign 진입 시 프로젝트가 없을 때 뜨는 생성 모달.
  const [showCreateProject, setShowCreateProject] = useState(false);
  // VLM 읽기 사전확인 — url/campaign 모드의 이미지 URL을 백엔드가 읽을 수 있는지.
  const [vlmCheck, setVlmCheck] = useState<{
    status: 'idle' | 'checking' | 'ok' | 'fail';
    reason?: string;
  }>({ status: 'idle' });
  const activeCheckUrl = inputMode === 'campaign' ? campaignImageUrl.trim() : '';
  // 선택된 입력 소스의 이미지 URL(생성 후보/집행 캠페인). 'image' 모드는 파일 사용이라 빈 문자열.
  const selectedImageUrl =
    inputMode === 'generated'
      ? selectedGenImageUrl
      : inputMode === 'campaign'
        ? campaignImageUrl
        : '';

  // '생성한 광고' 모드 진입 시 — 선택 프로젝트의 성공한 생성 후보(제품명-후보N)를 로드한다.
  useEffect(() => {
    if (inputMode !== 'generated' || !selectedProject) return;
    let cancelled = false;
    setSelectedGenValue('');
    setGenLoading(true);
    (async () => {
      try {
        const gens = (await api.projects.generations(selectedProject.id, 20)) as Array<{
          id: string;
          status: string;
          product_name: string | null;
        }>;
        const completed = gens.filter(g => g.status === 'completed').slice(0, 10);
        const details = await Promise.all(
          completed.map(g =>
            api.generator
              .detail(g.id)
              .then(d => ({ g, d }))
              .catch(() => null),
          ),
        );
        if (cancelled) return;
        const opts: { value: string; label: string; imageUrl: string }[] = [];
        for (const entry of details) {
          if (!entry) continue;
          const { g, d } = entry as {
            g: { id: string; product_name: string | null };
            d: { candidates?: Array<{ candidate_id: string; idx: number; image_url: string | null }> };
          };
          const name = g.product_name || '광고';
          (d.candidates ?? [])
            .filter(c => c.image_url)
            .forEach((c, i) => {
              opts.push({
                value: `${g.id}:${c.candidate_id}`,
                label: `${name}-후보${(c.idx ?? i) + 1}`,
                imageUrl: c.image_url!.startsWith('http')
                  ? c.image_url!
                  : `${API_BASE}${c.image_url}`,
              });
            });
        }
        setGenOptions(opts);
      } catch {
        if (!cancelled) setGenOptions([]);
      } finally {
        if (!cancelled) setGenLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [inputMode, selectedProject?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const [adTitle, setAdTitle] = useState('');
  const [categoryId, setCategoryId] = useState<number | ''>('');
  const [serviceClass, setServiceClass] = useState<number | ''>('');
  const categories = SIM_CATEGORIES; // 하드코딩 마스터(DB/API 대체).
  // 광고 목표 — 일반인도 쉽게 고르는 단일 선택(+ 기타 직접 입력).
  const [goalItem, setGoalItem] = useState('');
  const [customGoal, setCustomGoal] = useState('');

  // VLM 읽기 사전확인 — url/campaign 모드 이미지 URL을 백엔드가 GET할 수 있는지(디바운스).
  useEffect(() => {
    if (!activeCheckUrl) {
      setVlmCheck({ status: 'idle' });
      return;
    }
    let cancelled = false;
    setVlmCheck({ status: 'checking' });
    const t = setTimeout(async () => {
      try {
        const r = await api.simulation.checkImage(activeCheckUrl);
        if (!cancelled) setVlmCheck(r.ok ? { status: 'ok' } : { status: 'fail', reason: r.reason });
      } catch {
        if (!cancelled) setVlmCheck({ status: 'fail', reason: '확인에 실패했어요.' });
      }
    }, 600);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [activeCheckUrl]);

  // '집행중 광고' 모드 진입 시 — 집행 캠페인 목록을 로드한다.
  useEffect(() => {
    if (inputMode !== 'campaign') return;
    let cancelled = false;
    setCampaignsLoading(true);
    (async () => {
      try {
        const resp = await api.management.campaigns();
        if (cancelled) return;
        setCampaigns(
          (resp?.campaigns ?? []).map(c => ({
            campaign_id: c.campaign_id,
            name: c.name,
            state: c.state,
          })),
        );
      } catch {
        if (!cancelled) setCampaigns([]);
      } finally {
        if (!cancelled) setCampaignsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [inputMode]);

  // 캠페인 선택 → 그 소재의 이미지·카피를 시뮬 입력으로 prefill(카피는 비어 있을 때만).
  const onSelectCampaign = async (id: string) => {
    setSelectedCampaignId(id);
    setCampaignImageUrl('');
    setCampaignImgError(false);
    if (!id) return;
    try {
      const t = await api.management.campaignTargeting(id);
      if (t.ad_image_url) setCampaignImageUrl(t.ad_image_url);
      if (t.ad_headline && !adTitle.trim()) setAdTitle(t.ad_headline);
      if (t.ad_body && !adContent.trim()) setAdContent(t.ad_body);
      if (t.category_id && categoryId === '') setCategoryId(t.category_id);
      if (t.service_class && serviceClass === '') setServiceClass(t.service_class);
      // 광고 목표·연령·성별도 Meta 값으로 prefill(비어 있을 때만 — 사용자 수정 보존).
      const goal = goalFromObjective(t.objective);
      if (goal && !goalItem) setGoalItem(goal);
      if (t.gender && !gender) setGender(t.gender);
      if ((t.age_min != null || t.age_max != null) && ageBands.length === 0) {
        const lo = t.age_min ?? 18;
        const hi = t.age_max ?? 65;
        const bands = AGE_BANDS.filter(b => b.min <= hi && b.max >= lo).map(b => b.label);
        if (bands.length) setAgeBands(bands);
      }
      // 가상 소비자 수 = Meta 실측 도달수 기반 추천값(reader가 10~200으로 클램프). reach는 원값 표시용.
      setCampaignReach(typeof t.reach === 'number' ? t.reach : null);
      if (t.suggested_persona_count) setSampleSize(t.suggested_persona_count);
    } catch {
      /* 조회 실패 — 이미지 없이 진행 */
    }
  };

  // compare '이 캠페인으로 시뮬 돌리기' 진입 — URL의 from_campaign을 집행중 광고로 자동 선택·prefill.
  useEffect(() => {
    const cid = new URLSearchParams(window.location.search).get('from_campaign');
    if (!cid) return;
    setInputMode('campaign');
    setSelectedCampaignId(cid);
    void onSelectCampaign(cid);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // from_campaign 진입 시 프로젝트 자동 처리: 1개면 자동선택 · 0개면 생성 모달 · 여러개면 사용자 선택 유도.
  useEffect(() => {
    const cid = new URLSearchParams(window.location.search).get('from_campaign');
    if (!cid || projectsLoading || selectedProject) return;
    if (projects.length === 1) {
      selectProject(projects[0].id);
    } else if (projects.length === 0) {
      setShowCreateProject(true);
    }
  }, [projectsLoading, projects, selectedProject]);

  // 시뮬레이션 설정
  const [sampleSize, setSampleSize] = useState(20);
  const [allocation, setAllocation] = useState<'proportional' | 'stratified'>(
    'proportional'
  );
  const [ageBands, setAgeBands] = useState<string[]>([]);
  const [gender, setGender] = useState<GenderFilter>('');

  const [error, setError] = useState<string | null>(null);

  // SSE 진행률 — 실행 중 단계·퍼센트 표시.
  const [pct, setPct] = useState(0);
  const [stageMsg, setStageMsg] = useState('');
  // persona_set 진행 — 어느 세그먼트를 처리 중인지(segment_index/total).
  const [segProgress, setSegProgress] = useState<{
    label: string;
    index: number;
    total: number;
  }>({ label: '', index: 0, total: 0 });
  const esRef = useRef<(() => void) | null>(null); // SSE 재연결 구독 close 함수(X2)

  // 언마운트 시 스트림 정리(백엔드 런 자체는 asyncio.create_task라 계속 돈다 — 화면 구독만 해제).
  useEffect(() => () => esRef.current?.(), []);

  // 진행 중 run_id가 있으면(다른 탭 갔다 돌아온 경우 포함) setup 폼이 먼저 그려지는 깜빡임 없이
  // running 화면부터 낙관적으로 띄운 뒤, 상태 조회 결과로 확정/롤백한다.
  // useLayoutEffect — 브라우저 페인트 전에 반영(useEffect는 페인트 후라 setup 폼이 잠깐 보임).
  useLayoutEffect(() => {
    const raw = localStorage.getItem(ACTIVE_SIM_KEY);
    if (!raw) return;
    let stored: { run_id: string; mode: AnalysisMode } | null = null;
    try {
      stored = JSON.parse(raw);
    } catch {
      localStorage.removeItem(ACTIVE_SIM_KEY);
      return;
    }
    if (!stored?.run_id) return;
    setStep('running'); // 낙관적 — 아래 상태 조회로 확정하거나 되돌린다.
    api.simulation
      .status(stored.run_id)
      .then(st => {
        if (st.status !== 'RUNNING') {
          localStorage.removeItem(ACTIVE_SIM_KEY);
          setStep('setup');
          return;
        }
        setAnalysisMode(stored!.mode);
        setSimJob(stored!.run_id);
        setPct(st.pct ?? 0);
        setStageMsg(st.stage ? STAGE_LABEL[st.stage] ?? '' : '');
        subscribeRun(stored!.run_id, stored!.mode);
      })
      .catch(() => {
        // 상태 확인 실패 — 낙관적으로 띄운 화면은 되돌리되 키는 유지(다음 마운트에 재시도).
        setStep('setup');
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 광고 공통 필드(3-모드 공용) — start·compare 요청에 함께 실린다.
  function adCommonFields() {
    return {
      ad_id: adId.trim() || `AD-${Date.now()}`,
      ad_content: adContent || undefined,
      ad_image: inputMode === 'image' ? file : undefined,
      ad_image_url: selectedImageUrl || undefined,
      project_id: selectedProject?.id ?? undefined,
      ad_title: adTitle || undefined,
      ad_objective:
        (goalItem === '기타' ? customGoal.trim() : goalItem) || undefined,
      product_category:
        categories.find(c => c.id === categoryId)?.name || undefined,
      service_class:
        typeof serviceClass === 'number' ? serviceClass : undefined,
      // 집행중 광고 기반 시뮬 — 완료 후 서버가 캠페인↔시뮬 자동 링크(성과 비교 '집행 전 예측' 채움).
      // 링크는 from_campaign_id + organization_id가 함께 있을 때만 걸린다(simulation_service).
      from_campaign_id:
        inputMode === 'campaign' && selectedCampaignId ? selectedCampaignId : undefined,
      // '생성한 광고로 시뮬' — 옵션 value는 `${generationId}:${candidateId}`. 앞의 generation id를
      // 넘겨 ads.generation_id로 영속(채팅 개선모드가 상품 누끼를 역추적해 재사용).
      generation_id:
        inputMode === 'generated' && selectedGenValue
          ? selectedGenValue.split(':')[0]
          : undefined,
      organization_id: getAdminOrgId() ?? undefined,
    };
  }

  // SegmentDraft → 계약상의 SegmentInput(연령대 1개 + 성별 → target_filter).
  function buildSegments(): SegmentInput[] {
    return segments.map(s => {
      const band = AGE_BANDS.find(b => b.label === s.ageBand);
      const target_filter: SegmentInput['target_filter'] = {};
      if (band) {
        target_filter.age_min = band.min;
        target_filter.age_max = band.max;
      }
      if (s.gender) target_filter.gender = s.gender;
      return {
        label: s.label.trim() || '세그먼트',
        target_filter,
        sample_size: s.sampleSize,
      };
    });
  }

  // Individual 모드 — 현재 타깃 조건(연령대·성별)으로 패널에서 페르소나 후보를 불러온다.
  async function loadPersonaOptions(offset = 0) {
    setPersonaOptionsLoading(true);
    try {
      const bands = AGE_BANDS.filter(b => ageBands.includes(b.label));
      const params: { gender?: string; age_min?: number; age_max?: number; limit: number; offset: number } = {
        limit: 20,
        offset,
      };
      if (bands.length > 0) {
        params.age_min = Math.min(...bands.map(b => b.min));
        params.age_max = Math.max(...bands.map(b => b.max));
      }
      if (gender) params.gender = gender;
      const res = await api.simulation.panelPersonas(params);
      setPersonaOptions(prev => (offset === 0 ? res.items : [...prev, ...res.items]));
      setPersonaOptionsTotal(res.total);
    } catch {
      setPersonaOptions([]);
      setPersonaOptionsTotal(0);
    } finally {
      setPersonaOptionsLoading(false);
    }
  }

  // SSE 구독 — 최초 실행·타 탭 복귀 후 복원 공용(mode를 인자로 받아 완료 라우팅을 결정 —
  // 복원 시엔 analysisMode state가 아직 갱신 전일 수 있어 클로저 값 대신 인자를 쓴다).
  function subscribeRun(run_id: string, mode: AnalysisMode) {
    // SSE 자동 재연결(X2) — 일시 끊김은 지수 backoff로 재구독, 정상 수신 시 리셋.
    // 종료(completed/error)면 재연결 안 함. 최대 재시도 초과 시에만 에러 처리.
    esRef.current = openReconnectingStream(
      () => api.simulation.stream(run_id),
      {
        label: 'sim',
        isTerminal: d =>
          (d as SSEProgressEvent).event === 'completed' ||
          (d as SSEProgressEvent).event === 'error',
        onGiveUp: msg => {
          setError(msg);
          esRef.current = null;
          setSimJob(null); // 동시실행 슬롯 해제
          localStorage.removeItem(ACTIVE_SIM_KEY);
          setStep('setup');
        },
        onEvent: raw => {
          const data = raw as SSEProgressEvent;

          if (data.event === 'error') {
            setError(data.message ?? '시뮬레이션 진행 중 오류');
            esRef.current = null;
            setSimJob(null); // 동시실행 슬롯 해제
            localStorage.removeItem(ACTIVE_SIM_KEY);
            setStep('setup');
            return;
          }

          if (typeof data.pct === 'number') setPct(data.pct);
          // reaction 단계는 message("반응 N/total")가 더 구체적이라 우선.
          if (data.stage)
            setStageMsg(data.message ?? STAGE_LABEL[data.stage] ?? '');
          // persona_set — 세그먼트 진행(segment_index/total) 표시.
          if (
            data.segment_label ||
            typeof data.segment_index === 'number' ||
            typeof data.segment_total === 'number'
          ) {
            setSegProgress(prev => ({
              label: data.segment_label ?? prev.label,
              index: data.segment_index ?? prev.index,
              total: data.segment_total ?? prev.total,
            }));
          }

          if (data.event !== 'completed') return;
          setPct(100);
          esRef.current = null;
          setSimJob(null); // 동시실행 슬롯 해제
          localStorage.removeItem(ACTIVE_SIM_KEY);

          if (mode === 'persona_set') {
            // 세그먼트 비교 — compareResult 후 sessionStorage 브리지로 넘긴다.
            api.simulation
              .compareResult(run_id)
              .then(cmp => {
                saveSimComparison(run_id, {
                  comparison: cmp,
                  adTitle: adTitle || undefined,
                  adDescription: adContent || undefined,
                });
                router.push(`/simulation/${run_id}`);
              })
              .catch(e => {
                setError(e instanceof Error ? e.message : '결과 조회 실패');
                setStep('setup');
              });
            return;
          }

          api.simulation
            .result(run_id)
            .then((r: SimRunResult) => {
              // DB 저장됐으면 simulation_id, 아니면 run_id로 키·라우팅(폴백).
              const routeId = r.simulation_id ?? r.run_id;
              saveSimResult(routeId, {
                result: r,
                adTitle: adTitle || undefined,
                adDescription: adContent || undefined,
                mode,
              });
              // N1 — 전용 페이지 직접 실행이 끝나면, 결과 + "개선해서 다시 돌리기" 제안을
              // 자동 주입. 기존 대화에 끼워넣지 않고 '새 채팅 세션'을 만들어 거기에 제안한다.
              const pid = selectedProject?.id;
              if (pid) refreshDetails(pid); // 완료된 시뮬을 좌측 패널에 즉시 반영
              if (pid && r.simulation_id) {
                const injectKey = `n1_injected_${run_id}`; // 동일 run 1회만(중복 주입 방지)
                if (!localStorage.getItem(injectKey)) {
                  localStorage.setItem(injectKey, '1');
                  const simId = r.simulation_id;
                  const sessionTitle = `${adTitle || '광고'} 시뮬 결과·개선`;
                  api.chat.createSession(pid, sessionTitle).then(created => {
                    const sid = created.id;
                    void api.chat
                      .appendWidgets(sid, [
                        {
                          content: '시뮬레이션 결과예요.',
                          meta: {
                            source: 'simulation',
                            label: '시뮬레이션',
                            widget: {
                              type: 'sim_result',
                              data: { simulation_id: simId },
                            },
                          },
                        },
                        {
                          content:
                            '결과를 바탕으로 광고를 개선해서 다시 돌려볼까요?',
                          meta: {
                            source: 'simulation',
                            label: '개선 제안',
                            approval: {
                              action: 'rerun_simulation',
                              label: '개선해서 다시 돌리기',
                              reasons: [
                                '전용 페이지에서 직접 돌린 결과를 채팅에서 이어 개선할 수 있어요.',
                              ],
                            },
                          },
                        },
                      ])
                      .then(() => {
                        // N2 — 패널이 닫혀 있으면 안읽음 뱃지를 올린다(2건 주입 → +1, 알림은 1회).
                        if (!floatingOpenRef.current) pushUnread();
                      })
                      .catch(() => {});
                  }).catch(() => {});
                }
              }
              router.push(`/simulation/${routeId}`);
            })
            .catch(e => {
              setError(e instanceof Error ? e.message : '결과 조회 실패');
              setStep('setup');
            });
        },
      }
    );
  }

  async function run() {
    // 동시실행 제한 — 시뮬은 한 번에 하나(채팅 위젯과 store 공유).
    if (getJobs().sim) {
      setError(
        '이미 다른 시뮬레이션이 진행 중이에요. 끝난 뒤 다시 시도하세요.'
      );
      return;
    }
    setError(null);
    setPct(0);
    setStageMsg('');
    setSegProgress({ label: '', index: 0, total: 0 });
    setStep('running');

    try {
      // 모드별로 run_id 확보 — persona_set은 compare, 그 외는 start.
      let run_id: string;
      if (analysisMode === 'persona_set') {
        const res = await api.simulation.compare({
          ...adCommonFields(),
          segments: buildSegments(),
        });
        run_id = res.run_id;
      } else {
        // 사용자가 연령대·성별을 고르면 그 조건으로, 아무것도 안 고르면 자동(AUTO).
        // individual + 페르소나 지정 시엔 age/gender 대신 persona_id로 그 1명을 정확히 지정.
        const targetFilter: Record<string, unknown> = {};
        if (analysisMode === 'individual' && pickedPersona) {
          targetFilter.persona_id = pickedPersona.persona_id;
        }
        const bands = AGE_BANDS.filter(b => ageBands.includes(b.label));
        if (!targetFilter.persona_id && bands.length > 0) {
          targetFilter.age_min = Math.min(...bands.map(b => b.min));
          targetFilter.age_max = Math.max(...bands.map(b => b.max));
        }
        if (!targetFilter.persona_id && gender) targetFilter.gender = gender;
        const targetMode =
          targetFilter.persona_id || bands.length > 0 || gender !== ''
            ? 'MANUAL'
            : 'AUTO';
        // 비동기 시작 → run_id 받고 SSE로 진행률 구독(결과는 completed 후 GET).
        const res = await api.simulation.start({
          ...adCommonFields(),
          target_filter: targetFilter,
          target_mode: targetMode,
          // individual은 표본 1명 고정.
          sample_size: analysisMode === 'individual' ? 1 : sampleSize,
          allocation,
          analysis_mode: analysisMode,
        });
        run_id = res.run_id;
      }

      setSimJob(run_id); // 동시실행 슬롯 점유(시뮬 1개 제한)
      // 타 탭 이동 후 복귀 복원용 — 완료/에러 시 subscribeRun이 정리한다.
      localStorage.setItem(ACTIVE_SIM_KEY, JSON.stringify({ run_id, mode: analysisMode }));
      subscribeRun(run_id, analysisMode);
    } catch (e) {
      setSimJob(null); // 동시실행 슬롯 해제
      setError(e instanceof Error ? e.message : '시뮬레이션 실행 실패');
      setStep('setup');
    }
  }

  /* ─── STEP: setup ─── */
  if (step === 'setup') {
    const previewUrl = file ? URL.createObjectURL(file) : null;
    // 광고 이미지 필수 — 개선 모드가 시뮬 이미지를 개선 대상으로 불러오므로 항상 있어야 한다.
    const imageReady =
      inputMode === 'image' ? file !== null : selectedImageUrl.trim() !== '';
    const goalReady =
      goalItem === '기타' ? customGoal.trim() !== '' : goalItem !== '';
    // persona_set은 세그먼트가 2개 이상, 각 라벨·표본수가 유효해야 비교가 의미 있다.
    const segmentsReady =
      segments.length >= 2 &&
      segments.every(s => s.label.trim() !== '' && s.sampleSize >= 1);
    const canRun =
      selectedProject !== null &&
      adTitle.trim() !== '' &&
      adContent.trim() !== '' &&
      imageReady &&
      categoryId !== '' &&
      serviceClass !== '' &&
      goalReady &&
      (analysisMode !== 'persona_set' || segmentsReady);
    return (
      <div className='px-8 py-8 max-w-5xl mx-auto'>
        <div className='mb-6'>
          <h1 className='text-2xl font-bold text-ink'>
            시뮬레이터 실행
          </h1>
          <p className='text-sm text-ink-tertiary mt-1'>
            AI 가상 소비자에게 광고 반응을 미리 테스트합니다
          </p>
        </div>

        {error && <ErrorCard message={error} onRetry={run} className='mb-5' />}

        {/* ── 3-모드 분석 선택 (A-1) ── */}
        <div className={`${cardCls} mb-5`}>
          <label className={labelCls}>분석 모드</label>
          <div className='flex flex-wrap gap-2'>
            {MODE_TABS.map(m => (
              <button
                key={m.value}
                type='button'
                onClick={() => {
                  setAnalysisMode(m.value);
                  // 다른 모드로 바꾸면 individual 전용 페르소나 지정은 무의미 — 정리.
                  if (m.value !== 'individual') {
                    setPickedPersona(null);
                    setPersonaPickerOpen(false);
                  }
                }}
                className={`${chipBase} ${analysisMode === m.value ? chipActive : chipIdle}`}>
                {m.label}
              </button>
            ))}
          </div>
          <p className='text-[11px] text-ink-tertiary mt-2'>
            {MODE_TABS.find(m => m.value === analysisMode)?.desc}
          </p>
        </div>

        {/* ── 프로젝트 선택 (광고 입력 위, 풀너비) ── */}
        <div className={`${cardCls} mb-5`}>
          <label className={labelCls}>
            프로젝트 <span className='text-[#F74D4D]'>*</span>
          </label>
          {projects.length === 0 ? (
            <div className='flex items-center gap-3'>
              <p className='text-sm text-ink-tertiary'>
                선택할 프로젝트가 없습니다.
              </p>
              <button
                type='button'
                onClick={() => setShowCreateProject(true)}
                className='px-3 py-1.5 rounded-lg bg-primary hover:bg-primary-hover text-white text-xs font-semibold transition-colors'>
                + 프로젝트 만들기
              </button>
            </div>
          ) : (
            <Select
              aria-label='프로젝트 선택'
              placeholder='프로젝트를 선택하세요'
              value={selectedProject?.id ?? ''}
              onChange={v => selectProject(v || null)}
              options={projects.map(p => ({ value: p.id, label: p.name }))}
            />
          )}
        </div>

        {/* from_campaign 진입 등에서 프로젝트가 없을 때 — 캠페인명으로 프리필된 생성 모달. */}
        {showCreateProject && (
          <CreateProjectModal
            defaultName={
              new URLSearchParams(window.location.search).get('from_name') ?? ''
            }
            onClose={() => {
              setShowCreateProject(false);
              // from_campaign 진입이었으면 성과비교로 복귀(그 외엔 그냥 닫힘).
              if (new URLSearchParams(window.location.search).get('from_campaign')) {
                router.back();
              }
            }}
            onCreated={async created => {
              setShowCreateProject(false);
              await refresh();
              if (created?.id) selectProject(created.id);
            }}
          />
        )}

        <div className='grid grid-cols-[1fr_1fr] gap-5 items-stretch'>
          {/* ── 왼쪽: 광고 입력 ── */}
          <div className={`${cardCls} flex flex-col gap-5`}>
            <p className='text-sm font-semibold text-ink'>
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
              <label className={labelCls}>
                제품 설명 <span className='text-[#F74D4D]'>*</span>
              </label>
              <textarea
                value={adContent}
                onChange={e => setAdContent(e.target.value)}
                rows={3}
                placeholder='제품 특징이나 광고 카피를 입력하세요.'
                className={`${inputCls} resize-none`}
              />
            </div>

            {/* 이미지 입력 방식 — 남는 세로 공간을 채워 좌우 높이 정렬 */}
            <div className='flex flex-1 flex-col'>
              <label className={labelCls}>
                광고 이미지 <span className='text-[#F74D4D]'>*</span>
              </label>
              <div className='flex gap-2 mb-3'>
                {(
                  [
                    ['image', '파일 업로드'],
                    ['generated', '생성한 광고'],
                    ['campaign', '집행중 광고'],
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
                <label className='relative flex flex-1 min-h-0 flex-col items-center justify-center border-2 border-dashed border-line rounded-xl cursor-pointer hover:border-primary transition-colors overflow-hidden'>
                  {previewUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={previewUrl}
                      alt='미리보기'
                      className='absolute inset-0 h-full w-full object-contain'
                    />
                  ) : (
                    <span className='text-sm text-ink-tertiary'>
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
              {inputMode === 'generated' && (
                <div className='flex flex-1 min-h-0 flex-col gap-3'>
                  {!selectedProject ? (
                    <p className='text-sm text-ink-tertiary'>
                      먼저 위에서 프로젝트를 선택하세요.
                    </p>
                  ) : genLoading ? (
                    <p className='text-sm text-ink-tertiary'>
                      생성한 광고를 불러오는 중...
                    </p>
                  ) : genOptions.length === 0 ? (
                    <p className='text-sm text-ink-tertiary'>
                      이 프로젝트에 성공한 생성 내역이 없어요.
                    </p>
                  ) : (
                    <>
                      <Select
                        aria-label='생성한 광고 후보 선택'
                        placeholder='생성한 광고 후보 선택'
                        value={selectedGenValue}
                        onChange={setSelectedGenValue}
                        options={genOptions.map(o => ({
                          value: o.value,
                          label: o.label,
                        }))}
                      />
                      {selectedGenImageUrl && (
                        <div className='relative flex flex-1 min-h-0 items-center justify-center overflow-hidden rounded-xl border border-line bg-[#F8F9FA] dark:bg-[#1C2333]'>
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={selectedGenImageUrl}
                            alt='선택한 생성 광고'
                            className='absolute inset-0 h-full w-full object-contain'
                          />
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
              {inputMode === 'campaign' && (
                <div className='flex flex-1 min-h-0 flex-col gap-3'>
                  {campaignsLoading ? (
                    <p className='text-sm text-ink-tertiary'>
                      집행 캠페인을 불러오는 중...
                    </p>
                  ) : campaigns.length === 0 ? (
                    <p className='text-sm text-ink-tertiary'>
                      집행 중인 캠페인이 없어요. (Meta 연결·집행 광고가 있어야 표시돼요.)
                    </p>
                  ) : (
                    <>
                      <Select
                        aria-label='집행 광고(캠페인) 선택'
                        placeholder='집행 광고(캠페인) 선택'
                        value={selectedCampaignId}
                        onChange={onSelectCampaign}
                        options={campaigns.map(c => ({
                          value: c.campaign_id,
                          label: `${c.name}${c.state ? ` · ${c.state}` : ''}`,
                        }))}
                      />
                      {selectedCampaignId && !campaignImageUrl && (
                        <p className='text-xs text-ink-tertiary'>
                          이 캠페인 소재에 이미지가 없어요.
                        </p>
                      )}
                      {campaignImageUrl && (
                        <div className='relative flex flex-1 min-h-0 items-center justify-center overflow-hidden rounded-xl border border-line bg-[#F8F9FA] dark:bg-[#1C2333]'>
                          {campaignImgError ? (
                            <p className='px-4 text-center text-xs text-ink-tertiary'>
                              브라우저 미리보기는 Meta 제한으로 안 보일 수 있어요. 아래 VLM 확인을 참고하세요.
                            </p>
                          ) : (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              key={campaignImageUrl}
                              src={campaignImageUrl}
                              alt='집행 광고 소재'
                              className='absolute inset-0 h-full w-full object-contain'
                              onError={() => setCampaignImgError(true)}
                            />
                          )}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
              {inputMode === 'campaign' &&
                vlmCheck.status !== 'idle' &&
                activeCheckUrl && (
                  <p
                    className={`mt-1 text-[11px] ${
                      vlmCheck.status === 'ok'
                        ? 'text-emerald-600 dark:text-emerald-400'
                        : vlmCheck.status === 'fail'
                          ? 'text-[#F04452]'
                          : 'text-ink-tertiary'
                    }`}>
                    {vlmCheck.status === 'checking'
                      ? '🔎 VLM이 읽을 수 있는지 확인 중...'
                      : vlmCheck.status === 'ok'
                        ? '✅ VLM이 읽을 수 있어요'
                        : `❌ ${vlmCheck.reason ?? '불러올 수 없어요'}`}
                  </p>
                )}
            </div>
          </div>

          {/* ── 오른쪽: 광고 설정 + 시뮬레이션 설정 + 타깃 설정 (세로 스택) ── */}
          <div className='flex flex-col gap-5'>
            {/* 광고 설정 — 제품 카테고리 & 광고 목표 */}
            <div className={`${cardCls} flex flex-col gap-5`}>
              <p className='text-sm font-semibold text-ink'>
                광고 설정
              </p>

              {/* 제품 카테고리 & 세부 분류 */}
              <div>
                <label className={labelCls}>
                  제품 카테고리 <span className='text-[#F74D4D]'>*</span>
                </label>
                <div className='grid grid-cols-2 gap-3'>
                  <Select
                    aria-label='제품 대분류'
                    placeholder='대분류 선택'
                    value={categoryId === '' ? '' : String(categoryId)}
                    onChange={v => {
                      setCategoryId(v ? Number(v) : '');
                      setServiceClass('');
                    }}
                    options={categories.map(c => ({
                      value: String(c.id),
                      label: c.name,
                    }))}
                  />
                  <Select
                    aria-label='제품 세부 분류'
                    placeholder='세부 분류 (NICE)'
                    value={serviceClass === '' ? '' : String(serviceClass)}
                    onChange={v => setServiceClass(v ? Number(v) : '')}
                    disabled={!categoryId}
                    options={(
                      categories.find(c => c.id === categoryId)?.kinds ?? []
                    ).map(k => ({
                      value: String(k.id),
                      label: `${k.id}류 · ${k.description}`,
                    }))}
                  />
                </div>
              </div>

              {/* 광고 목표 — 쉬운 단일 선택(칩) + 기타 직접 입력 */}
              <div>
                <label className={labelCls}>
                  광고 목표 <span className='text-[#F74D4D]'>*</span>
                </label>
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
                  <button
                    type='button'
                    onClick={() =>
                      setGoalItem(goalItem === '기타' ? '' : '기타')
                    }
                    className={`${chipBase} ${goalItem === '기타' ? chipActive : chipIdle}`}>
                    기타
                  </button>
                </div>
                {goalItem === '기타' && (
                  <input
                    type='text'
                    value={customGoal}
                    onChange={e => setCustomGoal(e.target.value)}
                    placeholder='광고 목표를 직접 입력하세요'
                    className={`${inputCls} mt-2`}
                  />
                )}
                <p className='text-[11px] text-ink-tertiary mt-1.5'>
                  {goalItem === '기타'
                    ? '원하는 광고 목표를 직접 적어주세요.'
                    : (AD_GOALS.find(g => g.value === goalItem)?.desc ??
                      '이 광고로 가장 원하는 결과를 하나 고르세요. 광고가 의도대로 전달됐는지 함께 비교합니다.')}
                </p>
              </div>
            </div>

            {/* persona_set은 세그먼트 편집, 그 외는 시뮬 설정 + 타깃 설정 */}
            {analysisMode === 'persona_set' ? (
              /* ── 세그먼트 비교 편집 ── */
              <div className={`${cardCls} flex flex-col gap-4`}>
                <div className='flex items-center justify-between'>
                  <p className='text-sm font-semibold text-ink'>
                    비교할 세그먼트
                  </p>
                  <button
                    type='button'
                    onClick={() =>
                      setSegments(prev => [
                        ...prev,
                        emptySegment(
                          `세그먼트 ${String.fromCharCode(65 + prev.length)}`
                        ),
                      ])
                    }
                    className={`${chipBase} ${chipIdle}`}>
                    + 세그먼트 추가
                  </button>
                </div>
                <p className='text-[11px] text-ink-tertiary -mt-2'>
                  각 세그먼트의 타깃·표본을 정하면, 완료 후 KPI를 나란히 비교합니다.
                </p>

                {segments.map((s, i) => (
                  <div
                    key={i}
                    className='rounded-xl border border-line p-4 flex flex-col gap-3'>
                    <div className='flex items-center gap-2'>
                      <input
                        type='text'
                        value={s.label}
                        onChange={e =>
                          setSegments(prev =>
                            prev.map((x, j) =>
                              j === i ? { ...x, label: e.target.value } : x
                            )
                          )
                        }
                        placeholder='세그먼트 이름'
                        className={`${inputCls} flex-1`}
                      />
                      {segments.length > 2 && (
                        <button
                          type='button'
                          onClick={() =>
                            setSegments(prev => prev.filter((_, j) => j !== i))
                          }
                          className='shrink-0 px-2.5 py-2 rounded-lg text-xs font-medium text-red-500 border border-red-200 dark:border-red-900/40 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors'>
                          삭제
                        </button>
                      )}
                    </div>

                    <div className='grid grid-cols-2 gap-3'>
                      <div>
                        <label className={labelCls}>연령대</label>
                        <Select
                          aria-label='연령대'
                          value={s.ageBand}
                          onChange={v =>
                            setSegments(prev =>
                              prev.map((x, j) =>
                                j === i ? { ...x, ageBand: v } : x
                              )
                            )
                          }
                          options={[
                            { value: '', label: '전 연령' },
                            ...AGE_BANDS.map(b => ({
                              value: b.label,
                              label: b.label,
                            })),
                          ]}
                        />
                      </div>
                      <div>
                        <label className={labelCls}>성별</label>
                        <Select
                          aria-label='성별'
                          value={s.gender}
                          onChange={v =>
                            setSegments(prev =>
                              prev.map((x, j) =>
                                j === i
                                  ? { ...x, gender: v as GenderFilter }
                                  : x
                              )
                            )
                          }
                          options={[
                            { value: '', label: '전체' },
                            { value: 'F', label: '여성' },
                            { value: 'M', label: '남성' },
                          ]}
                        />
                      </div>
                    </div>

                    <div>
                      <label className={labelCls}>
                        표본 수:{' '}
                        <span className='text-primary font-bold'>
                          {s.sampleSize}명
                        </span>
                      </label>
                      <input
                        type='range'
                        min={1}
                        max={200}
                        value={s.sampleSize}
                        onChange={e =>
                          setSegments(prev =>
                            prev.map((x, j) =>
                              j === i
                                ? { ...x, sampleSize: Number(e.target.value) }
                                : x
                            )
                          )
                        }
                        className='w-full accent-[#3182F6] mt-1'
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <>
                {/* 시뮬레이션 설정 — synthetic은 표본 슬라이더, individual은 1명 고정 */}
                <div className={`${cardCls} flex flex-col gap-5`}>
                  <p className='text-sm font-semibold text-ink'>
                    시뮬레이션 설정
                  </p>

                  {analysisMode === 'individual' ? (
                    // individual — 표본 1명 고정(슬라이더 숨김).
                    <div className='bg-primary-subtle border border-primary/20 rounded-xl px-4 py-4'>
                      <p className='text-sm font-semibold text-primary'>
                        가상 소비자 1명 심층 분석
                      </p>
                      <p className='text-[11px] text-ink-secondary mt-1'>
                        1명 모드는 표본이 1명으로 고정됩니다. 아래 타깃 조건에
                        맞는 페르소나 1명을 깊이 있게 분석합니다.
                      </p>
                    </div>
                  ) : (
                    <>
                      {/* 표본 수 */}
                      <div className='bg-surface-1 border border-line rounded-xl px-4 py-4'>
                        <label className={labelCls}>
                          가상 소비자 수:{' '}
                          <span className='text-primary font-bold'>
                            {sampleSize}명
                          </span>
                        </label>
                        {campaignReach != null && campaignReach > 0 && (
                          <p className='text-[11px] text-ink-tertiary mb-1'>
                            실제 Meta 도달 {campaignReach.toLocaleString()}명 → 표본 최대 200명
                          </p>
                        )}
                        <input
                          type='range'
                          min={1}
                          max={200}
                          value={sampleSize}
                          onChange={e => setSampleSize(Number(e.target.value))}
                          className='w-full accent-[#3182F6] mt-1'
                        />
                        <div className='flex justify-between text-[10px] text-ink-muted mt-1'>
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
                        <p className='text-[11px] text-ink-tertiary mt-1.5'>
                          {allocation === 'proportional'
                            ? '실제 인구 비율대로 뽑습니다 (기본 권장).'
                            : '소수 그룹도 충분히 포함되게 보강합니다 (정밀하지만 신뢰구간이 넓어짐).'}
                        </p>
                      </div>
                    </>
                  )}
                </div>

                {/* ── 타깃 설정 (미지정 시 자동 추정) ── */}
                <div className={`${cardCls} flex flex-col gap-5`}>
                  <p className='text-sm font-semibold text-ink'>
                    타깃 설정
                  </p>
                  <p className='text-[11px] text-ink-tertiary -mt-2'>
                    지정하지 않으면 자동으로 타깃을 추정합니다.
                  </p>

                  <div>
                    <p className={sectionTitle}>
                      연령대{' '}
                      <span className='text-[10px] font-normal text-ink-muted'>
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
                      <span className='text-[10px] font-normal text-ink-muted'>
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

                  {/* Individual 모드 — 자동 추출 대신 패널에서 특정 페르소나를 직접 지정 */}
                  {analysisMode === 'individual' && (
                    <div>
                      <p className={sectionTitle}>
                        페르소나 지정{' '}
                        <span className='text-[10px] font-normal text-ink-muted'>
                          선택 — 안 고르면 위 조건에서 자동 추출
                        </span>
                      </p>
                      {pickedPersona ? (
                        <div className='flex items-center justify-between rounded-lg border border-primary/30 bg-primary-subtle px-3 py-2'>
                          <div>
                            <p className='text-sm font-semibold text-ink'>
                              {pickedPersona.age}세 {pickedPersona.gender === 'F' ? '여성' : '남성'} · {pickedPersona.region}
                            </p>
                            <p className='text-[11px] text-ink-secondary line-clamp-1'>
                              {pickedPersona.narrative_snippet}
                            </p>
                          </div>
                          <button
                            type='button'
                            onClick={() => setPickedPersona(null)}
                            className='shrink-0 ml-2 text-xs text-[#F74D4D] font-medium'>
                            선택 해제
                          </button>
                        </div>
                      ) : (
                        <button
                          type='button'
                          onClick={() => {
                            setPersonaPickerOpen(v => !v);
                            if (!personaPickerOpen) void loadPersonaOptions(0);
                          }}
                          className={`${chipBase} ${personaPickerOpen ? chipActive : chipIdle}`}>
                          {personaPickerOpen ? '목록 닫기' : '패널에서 고르기'}
                        </button>
                      )}

                      {personaPickerOpen && !pickedPersona && (
                        <div className='mt-2 max-h-64 overflow-y-auto rounded-lg border border-line divide-y divide-line'>
                          {personaOptions.length === 0 && !personaOptionsLoading && (
                            <p className='text-[11px] text-ink-tertiary px-3 py-3'>
                              조건에 맞는 페르소나가 없어요. 연령대·성별 조건을 넓혀보세요.
                            </p>
                          )}
                          {personaOptions.map(p => (
                            <button
                              key={p.persona_id}
                              type='button'
                              onClick={() => {
                                setPickedPersona(p);
                                setPersonaPickerOpen(false);
                              }}
                              className='w-full text-left px-3 py-2 hover:bg-accent transition-colors'>
                              <p className='text-xs font-semibold text-ink'>
                                {p.age}세 {p.gender === 'F' ? '여성' : '남성'} · {p.region}
                              </p>
                              <p className='text-[11px] text-ink-tertiary line-clamp-1'>
                                {p.narrative_snippet}
                              </p>
                            </button>
                          ))}
                          {personaOptionsLoading && (
                            <p className='text-[11px] text-ink-tertiary px-3 py-3'>불러오는 중...</p>
                          )}
                          {!personaOptionsLoading && personaOptions.length < personaOptionsTotal && (
                            <button
                              type='button'
                              onClick={() => void loadPersonaOptions(personaOptions.length)}
                              className='w-full text-center text-xs text-primary font-medium px-3 py-2'>
                              더 보기 ({personaOptions.length}/{personaOptionsTotal})
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>

        {/* ── 실행 버튼 (하단 전체 너비) ── */}
        <div className='mt-5'>
          <button
            onClick={run}
            disabled={!canRun}
            className='w-full flex items-center justify-center gap-2 py-3.5 bg-primary hover:bg-primary-hover disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl text-sm font-semibold transition-colors'>
            <svg className='w-4 h-4' fill='currentColor' viewBox='0 0 24 24'>
              <path d='M8 5v14l11-7z' />
            </svg>
            시뮬레이터 실행
          </button>
          {selectedProject === null ? (
            <p className='text-[11px] text-[#F74D4D] text-center mt-2'>
              위에서 프로젝트를 먼저 선택해 주세요.
            </p>
          ) : (
            <p className='text-[11px] text-ink-muted text-center mt-2'>
              가상 소비자 수에 따라 수 초~수십 초 걸립니다.
            </p>
          )}
        </div>
      </div>
    );
  }

  /* ─── STEP: running ─── */
  if (step === 'running') {
    return (
      <div className='px-8 py-8 max-w-5xl mx-auto'>
        <div className={`${cardCls} flex flex-col gap-6 py-16`}>
          <div className='flex flex-col items-center gap-4'>
            <div className='w-10 h-10 border-4 border-line border-t-[#3182F6] dark:border-t-[#5B9DF9] rounded-full animate-spin' />
            {/* persona_set — 세그먼트 진행(segment_index/total) 표시 */}
            {analysisMode === 'persona_set' && segProgress.total > 0 && (
              <span className='px-2.5 py-1 rounded-full text-[11px] font-semibold bg-primary-subtle text-primary'>
                세그먼트 {segProgress.index}/{segProgress.total}
                {segProgress.label ? ` · ${segProgress.label}` : ''}
              </span>
            )}
            <p className='text-sm font-medium text-ink-secondary'>
              {stageMsg ||
                (analysisMode === 'persona_set'
                  ? '세그먼트별로 광고 반응을 생성하는 중...'
                  : analysisMode === 'individual'
                    ? '가상 소비자 1명이 광고에 반응하는 중...'
                    : `${sampleSize}명 페르소나가 광고에 반응하는 중...`)}
            </p>
          </div>
          <div className='w-full max-w-md mx-auto space-y-2'>
            <div className='flex justify-between text-xs'>
              <span className='text-ink-tertiary'>진행률</span>
              <span className='font-medium text-ink'>
                {pct}%
              </span>
            </div>
            <div className='w-full bg-surface-1 rounded-full h-2 overflow-hidden'>
              <div
                className='h-full bg-primary rounded-full transition-all duration-300'
                style={{ width: `${pct}%` }}
              />
            </div>
            <p className='text-xs text-ink-muted text-center pt-1'>
              {analysisMode === 'persona_set'
                ? '세그먼트마다 광고 해석 → 반응 생성 → 집계를 반복합니다.'
                : '광고 해석 → 패널 로드 → 반응 생성 → 집계'}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return null;
}
