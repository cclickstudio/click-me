// 발표 Q&A 부록 — 40개 예상 질문과, 답을 하며 보여줄 시각 자료(exhibit) 매핑.
// 질문에는 글로 쓴 정답을 달지 않는다 — 질문을 고르면 그 질문에 응할 때 근거로 쓸 자료만 보여준다.
// 같은 자료를 여러 질문이 공유하는 경우가 많다(예: DDD 구조도, 집행 파이프라인, 스케줄러 잡 현황).

import { Sparkles, Users, BarChart3, MessageSquare, Lock, Eye, Search, PlayCircle, ClipboardCheck } from 'lucide-react';
import { Pipeline, LayerStack, Matrix, Timeline, InfoCards, StatusRow, BarDistribution, StepBox, type Tone } from './primitives';

export type Exhibit = { title: string; note: string; render: () => React.ReactNode };

const iconProps = { size: 16, strokeWidth: 1.8 } as const;

function DDDStructure({ domain, extraLayer, note }: { domain: string; extraLayer?: { label: string; detail?: string; tone?: Tone }; note?: string }) {
  return (
    <div className="space-y-3">
      <LayerStack
        layers={[
          { label: `api/routers/${domain}`, detail: '전송 계층 — /api/* prefix로 등록', tone: 'neutral' },
          { label: `domain/${domain}/service`, detail: '유스케이스 · DB 영속 · SSE', tone: 'primary' },
          { label: 'contracts (포트) ← adapters (구현)', detail: '외부 연동 · mock 전환', tone: 'neutral' },
          { label: 'graph / agents', detail: 'LangGraph', tone: 'neutral' },
          ...(extraLayer ? [extraLayer] : []),
        ]}
      />
      <p className="text-xs text-ink-tertiary">wiring.py — mock ↔ 실연동 전환 유일 지점(Composition Root).{note ? ` ${note}` : ''}</p>
    </div>
  );
}

function LLMRoleMatrix({ highlight }: { highlight: string[] }) {
  const rows = [
    { label: '채팅', model: 'OpenAI gpt-4.1' },
    { label: '시뮬 반응', model: 'Gemini 2.5 Flash' },
    { label: '페르소나 토론자', model: 'gpt-4o-mini' },
    { label: '토론 Judge', model: 'Claude Haiku' },
    { label: '생성(제너레이터)', model: 'OpenAI gpt-4.1' },
  ];
  return (
    <Matrix
      columns={['모델']}
      rows={rows.map((r) => ({
        label: r.label,
        cells: [{ text: r.model, tone: highlight.includes(r.label) ? 'primary' : 'neutral' }],
      }))}
    />
  );
}

export const EXHIBITS: Record<string, Exhibit> = {
  'generation-flow': {
    title: '신규 생성 vs 개선 모드',
    note: '신규는 3종+QA 순위, 개선 모드는 기존 광고 기반 1종만 생성.',
    render: () => (
      <div className="space-y-5">
        <div>
          <p className="mb-2 text-xs font-semibold text-ink-tertiary">신규 생성</p>
          <Pipeline
            steps={[
              { label: '요구사항 입력', tone: 'neutral' },
              { label: '시안 3종 자동 생성', tone: 'warning' },
              { label: 'QA 기반 순위', tone: 'warning' },
            ]}
          />
        </div>
        <div>
          <p className="mb-2 text-xs font-semibold text-ink-tertiary">기존 광고 개선</p>
          <Pipeline
            steps={[
              { label: '기존 광고 입력', tone: 'neutral' },
              { label: '개선 시안 1종 생성', tone: 'warning' },
            ]}
          />
        </div>
      </div>
    ),
  },
  'model-config-table': {
    title: '생성 모델 구성',
    note: 'GENERATOR_*_MODEL 설정 교체 — 이미지 모델만 모드에 따라 달라짐.',
    render: () => (
      <Matrix
        columns={['OpenAI 모드', 'Gemini 모드']}
        rows={[
          { label: '텍스트', cells: [{ text: 'gpt-4.1' }, { text: 'gpt-4.1' }] },
          { label: '비전', cells: [{ text: 'gpt-4o' }, { text: 'gpt-4o' }] },
          { label: '이미지', cells: [{ text: 'gpt-image-1', tone: 'warning' }, { text: 'gemini-2.5-flash-image', tone: 'warning' }] },
        ]}
      />
    ),
  },
  'qa-ranking': {
    title: 'QA 기반 순위 산정',
    note: '자동 생성된 3개 시안을 품질 검증 기준으로 평가해 기대 성과 순위를 매김.',
    render: () => (
      <Pipeline
        steps={[
          { label: '시안 3종 생성', tone: 'warning' },
          { label: 'QA 품질 평가', tone: 'warning' },
          { label: '기대 성과 순위', tone: 'warning' },
        ]}
      />
    ),
  },
  'pdf-report-mockup': {
    title: 'PDF 보고서 구성',
    note: '표지부터 개선 제안까지 전체 보고서 형태로 자동 생성.',
    render: () => (
      <LayerStack
        layers={[
          { label: '표지 · 캠페인 개요', tone: 'neutral' },
          { label: '시안 3종 이미지 + 카피', tone: 'warning' },
          { label: 'QA 순위 · 기대 성과 요약', tone: 'warning' },
          { label: '개선 제안', tone: 'neutral' },
        ]}
      />
    ),
  },
  'prediction-to-generation': {
    title: '예측 반영 → 생성 파이프라인',
    note: '시뮬레이터의 반응 예측 결과를 개선 방향으로 삼아 시안 생성에 반영.',
    render: () => (
      <Pipeline
        steps={[
          { label: '시뮬레이션 예측 결과', tone: 'point' },
          { label: '개선 방향 도출', tone: 'point' },
          { label: '시안 3종 생성', tone: 'warning' },
          { label: '기대 성과 순위', tone: 'warning' },
        ]}
      />
    ),
  },
  'scheduler-jobs': {
    title: '비동기 워커 잡 현황',
    note: '별도 MQ(SQS·Redis) 없이 asyncio + APScheduler 워커로 처리, 기본은 전부 off.',
    render: () => (
      <StatusRow
        items={[
          { label: 'management · 이상 스캔', state: 'muted', detail: '기본 off · *_SCHEDULER_ENABLED 플래그로 켬' },
          { label: 'management · 리밸런스 제안', state: 'muted', detail: '기본 off' },
          { label: 'management · 주간 리포트', state: 'muted', detail: '기본 off' },
          { label: 'generator · 품질 다이제스트', state: 'muted', detail: '기본 off' },
        ]}
      />
    ),
  },
  'rag-hybrid-search': {
    title: '하이브리드 검색 (RAG)',
    note: 'generator·management 지식베이스(KB) 조회에 사용.',
    render: () => (
      <div className="space-y-3">
        <div className="flex flex-wrap gap-3">
          <StepBox label="pgvector 코사인 유사도" tone="neutral" />
          <StepBox label="PostgreSQL FTS 키워드" tone="neutral" />
        </div>
        <div className="ml-6 h-5 w-px bg-line-strong" />
        <StepBox label="RRF 융합" tone="primary" />
        <div className="ml-6 h-5 w-px bg-line-strong" />
        <StepBox label="KB 조회 결과" tone="primary" />
      </div>
    ),
  },
  'ddd-generator': {
    title: 'generator 도메인 구조',
    note: '',
    render: () => <DDDStructure domain="generator" />,
  },
  'ddd-simulation': {
    title: 'simulation 도메인 구조',
    note: '구 평면 라우터 simulate.py는 미등록 데드코드로 삭제 대상.',
    render: () => <DDDStructure domain="simulation" />,
  },
  'ddd-management': {
    title: 'management 도메인 구조',
    note: '',
    render: () => (
      <DDDStructure
        domain="management"
        extraLayer={{ label: 'detection/ · execution/ · evals/', detail: 'management 전용 확장', tone: 'success' }}
      />
    ),
  },
  'ddd-chat': {
    title: 'chat 도메인 구조',
    note: 'Open Issue — 정리 대상.',
    render: () => (
      <DDDStructure
        domain="chat"
        extraLayer={{ label: '__init__.py docstring 정리 필요', detail: '실제 역할(지원 인프라)에 맞게 미정리 상태', tone: 'muted' }}
      />
    ),
  },
  'persona-pipeline': {
    title: '페르소나 샘플링 파이프라인',
    note: '실제 개인이 아닌, 인구 분포를 반영한 합성 페르소나.',
    render: () => (
      <Pipeline
        steps={[
          { label: '행안부 인구 쿼터', tone: 'point' },
          { label: 'OCEAN 5요인 조건부 샘플링', tone: 'point' },
          { label: '서울대·카카오 OCEAN(N=81만) + KISDI 미디어 데이터', tone: 'point' },
          { label: '합성 페르소나 완성', detail: '4단계 모두 적용 완료', tone: 'success' },
        ]}
        vertical
      />
    ),
  },
  'decision-goal': {
    title: '시뮬레이터의 목표 정의',
    note: '실측 캠페인이 쌓일수록 calibration이 해금되는 구조.',
    render: () => (
      <div className="space-y-3">
        <StatusRow
          items={[
            { label: '목표 아님 — 실제 사람과 동일한 응답', state: 'muted' },
            { label: '목표 — 직감·내부 검토보다 나은 의사결정 근거', state: 'success' },
          ]}
        />
        <InfoCards
          items={[
            { label: '실측 calibration 해금 조건', value: '연결 캠페인 5건+', tone: 'warning' },
            { label: '현재 확보 실측 캠페인', value: '5건 미만 (미해금)', tone: 'muted' },
          ]}
        />
      </div>
    ),
  },
  'aisas-funnel': {
    title: 'AISAS 퍼널 — 클릭 의향률',
    note: '「예측 CTR」 등 실측 스케일 환산 표기는 금지.',
    render: () => (
      <Pipeline
        steps={[
          { label: 'Attention', tone: 'neutral' },
          { label: 'Interest', tone: 'neutral' },
          { label: 'Search', tone: 'neutral' },
          { label: 'Action', detail: '클릭 의향률 = 통과 비율(신뢰구간)', tone: 'point' },
          { label: 'Share', tone: 'neutral' },
        ]}
      />
    ),
  },
  'scoring-pipeline': {
    title: '기본 스코어링 vs SSR(opt-in)',
    note: 'SIMULATION_SCORING=ssr 플래그로 전환.',
    render: () => (
      <div className="space-y-5">
        <div>
          <p className="mb-2 text-xs font-semibold text-ink-tertiary">기본 (default)</p>
          <Pipeline
            steps={[
              { label: 'LLM 루브릭 정합', tone: 'point' },
              { label: '페르소나 반응 LLM 정수', tone: 'point' },
              { label: '부트스트랩 신뢰구간 집계', tone: 'point' },
            ]}
          />
        </div>
        <div>
          <p className="mb-2 text-xs font-semibold text-ink-tertiary">SSR (opt-in)</p>
          <Pipeline
            steps={[
              { label: '반응 텍스트 임베딩', tone: 'warning' },
              { label: '구매의도·신뢰도 분포 재산정', tone: 'warning' },
            ]}
          />
        </div>
        <Timeline
          events={[
            { date: '2026-07-08', label: 'SSR 기본 ON', tone: 'warning' },
            { date: '2026-07-09', label: '익일 원복', tone: 'muted' },
          ]}
        />
      </div>
    ),
  },
  'exposure-deliberation': {
    title: '초기 설계(2단계) vs 실제 구현',
    note: 'exposure·deliberation 2단계 설계는 죽은 코드.',
    render: () => (
      <div className="space-y-5">
        <div>
          <p className="mb-2 text-xs font-semibold text-ink-tertiary">초기 설계 (죽은 코드)</p>
          <Pipeline steps={[{ label: 'exposure (노출)', tone: 'muted' }, { label: 'deliberation (숙고)', tone: 'muted' }]} />
        </div>
        <div>
          <p className="mb-2 text-xs font-semibold text-ink-tertiary">실제 구현 (SSR)</p>
          <Pipeline steps={[{ label: '구매의도 분포 재산정', tone: 'point' }, { label: '신뢰도 분포 재산정', tone: 'point' }]} />
        </div>
      </div>
    ),
  },
  'llm-role-matrix-sim': {
    title: '멀티 LLM 역할 배정',
    note: '역할별로 다른 모델을 배정해 비용·품질 균형을 맞춤.',
    render: () => <LLMRoleMatrix highlight={['시뮬 반응', '페르소나 토론자', '토론 Judge']} />,
  },
  'llm-role-matrix-chat': {
    title: '멀티 LLM 역할 배정',
    note: '역할별로 다른 모델을 배정해 비용·품질 균형을 맞춤.',
    render: () => <LLMRoleMatrix highlight={['채팅']} />,
  },
  'distribution-output': {
    title: '구매의도 분포 (형태 예시)',
    note: '수치는 형태를 보여주기 위한 예시 — 평균 단언 없이 분포 전체를 표시.',
    render: () => <BarDistribution hue="point" bars={[
      { label: '1점', value: 8 }, { label: '2점', value: 15 }, { label: '3점', value: 30 }, { label: '4점', value: 32 }, { label: '5점', value: 15 },
    ]} />,
  },
  'kpi-definitions': {
    title: '4대 KPI 정의',
    note: '스칼라 값이 아니라 신뢰구간·분포로 출력.',
    render: () => (
      <InfoCards
        items={[
          { label: '클릭 의향률', value: 'AISAS Action 통과율', detail: '신뢰구간으로 표기', tone: 'point' },
          { label: '구매의도', value: '1~5점 평균+분포', detail: '평균 단언 금지', tone: 'point' },
          { label: '신뢰도', value: '1~5점 평균', tone: 'point' },
          { label: '거부율', value: '거부 비율 + 사유 분해', tone: 'point' },
        ]}
      />
    ),
  },
  'bootstrap-ci': {
    title: '부트스트랩 신뢰구간',
    note: '재표본추출을 반복해 신뢰구간을 집계.',
    render: () => (
      <Pipeline
        steps={[
          { label: '페르소나 반응 샘플', tone: 'point' },
          { label: '반복 재표본추출 (Bootstrap)', tone: 'point' },
          { label: '신뢰구간 산출', tone: 'success' },
        ]}
      />
    ),
  },
  'execution-pipeline': {
    title: '감지 → 진단 → 승인 → 집행 → 감사',
    note: '집행(write)은 사람 승인(HITL) 필수.',
    render: () => (
      <Pipeline
        steps={[
          { label: '감지', icon: <Eye {...iconProps} />, tone: 'neutral' },
          { label: '진단', icon: <Search {...iconProps} />, tone: 'neutral' },
          { label: '승인', icon: <Lock {...iconProps} />, detail: '사람 승인 필수(HITL)', tone: 'warning' },
          { label: '집행', icon: <PlayCircle {...iconProps} />, tone: 'success' },
          { label: '감사', icon: <ClipboardCheck {...iconProps} />, tone: 'neutral' },
        ]}
      />
    ),
  },
  'execution-modes': {
    title: '집행 모드 3단계',
    note: '기본은 봉인 — writer가 DRY_RUN/VALIDATE/LIVE 3모드로 전환.',
    render: () => (
      <StatusRow
        items={[
          { label: 'DRY_RUN', state: 'success', detail: '실제 집행 없음 — 기본값' },
          { label: 'VALIDATE', state: 'warning', detail: '검증만 수행' },
          { label: 'LIVE', state: 'danger', detail: '실제 집행 — Tier 1은 자동 승인기 개입' },
        ]}
      />
    ),
  },
  'safety-status': {
    title: '현재 로컬 환경 안전 상태',
    note: '발표 전 이 값들이 바뀌지 않았는지 재확인 필요.',
    render: () => (
      <StatusRow
        items={[
          { label: 'USE_MOCK=false', state: 'success', detail: '읽기는 실 Meta 연동' },
          { label: 'MANAGEMENT_EXECUTION_MODE=dry_run', state: 'success', detail: '쓰기는 봉인 — 현재 안전' },
          {
            label: '주의',
            state: 'danger',
            detail: '이 값이 live로 바뀌면 Tier 1(PAUSE·DECREASE_BUDGET)은 AUTO_APPROVER로 즉시 집행됨',
          },
        ]}
      />
    ),
  },
  'platform-matrix': {
    title: '플랫폼 연동 현황',
    note: '목표·예산·플랫폼·성과 단일 창구 관리가 기획 목표, 현재 실연동은 Meta 기준.',
    render: () => (
      <Matrix
        columns={['상태']}
        rows={[
          { label: 'Meta', cells: [{ text: '실연동(읽기)', tone: 'success' }] },
          { label: '카카오', cells: [{ text: '계획 단계', tone: 'muted' }] },
          { label: '네이버', cells: [{ text: '계획 단계', tone: 'muted' }] },
        ]}
      />
    ),
  },
  'org-hierarchy': {
    title: '조직 · 팀 · 프로젝트 계층',
    note: '프로젝트별 세분 권한(project_members)은 계획 단계, ORM 미구현.',
    render: () => (
      <LayerStack
        layers={[
          { label: '조직 (Organization)', detail: '결제·플랜 단위 (free/professional/enterprise)', tone: 'primary' },
          { label: '팀 (Team)', detail: '조직 하위 협업 단위 — 실제 구현됨', tone: 'success' },
          { label: '프로젝트 (Project)', detail: '캠페인 단위, team_id로 소속', tone: 'success' },
          { label: '프로젝트별 뷰어/에디터/오너 세분 권한', detail: '계획 단계 — ORM 미구현', tone: 'muted' },
        ]}
      />
    ),
  },
  'security-layers': {
    title: '기밀 데이터 보호',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '평문 로그 금지', state: 'success', detail: '예산·크리에이티브 등 기밀 데이터' },
          { label: '암호화 저장', state: 'success', detail: '외부 플랫폼 API 키 — AES-256 또는 AWS Secrets Manager' },
        ]}
      />
    ),
  },
  'deep-agent-routing': {
    title: '통합 딥에이전트 tool 라우팅',
    note: 'deepagents 고유 서브에이전트 기능은 미사용 — 커스텀 tool 라우팅으로 연결.',
    render: () => (
      <div className="space-y-3">
        <StepBox label="채팅 (POST /api/chat/complete)" tone="primary" />
        <div className="ml-6 h-5 w-px bg-line-strong" />
        <StepBox label="통합 딥에이전트 (deep_agent_builder.py)" tone="primary" detail="deepagents 기반, 커스텀 tool 라우팅" />
        <div className="ml-6 h-5 w-px bg-line-strong" />
        <div className="flex flex-wrap gap-3">
          <StepBox label="management @tool" tone="success" />
          <StepBox label="generator @tool" tone="warning" />
          <StepBox label="simulation @tool" tone="point" />
        </div>
      </div>
    ),
  },
  'orchestrator-migration': {
    title: '오케스트레이터 전환',
    note: '구세대 코드는 테스트에서만 참조되는 데드코드로 발표 후 삭제 예정.',
    render: () => (
      <Timeline
        events={[
          { date: '구세대', label: 'orchestrator.py · intent.py · registry.py', detail: '테스트만 참조 — 데드코드', tone: 'muted' },
          { date: '구세대', label: 'routing.py (키워드 라우팅)', detail: 'LLM Deep Agent와 충돌해 미사용 — 데드코드', tone: 'muted' },
          { date: '현재', label: '통합 딥에이전트', detail: '3도메인 @tool 위임, 구현 완료', tone: 'primary' },
        ]}
      />
    ),
  },
  'roadmap-timeline': {
    title: '로드맵 · 기능 우선순위',
    note: '핵심 3기능(시뮬·매니지먼트·생성) 완료 후 채팅·팀 관리 착수.',
    render: () => (
      <div className="space-y-5">
        <Timeline
          events={[
            { date: '2026-06-12', label: '베이스라인', tone: 'success' },
            { date: '2026-07-08', label: '최종 구현', detail: '핵심 3기능 + 채팅·팀관리', tone: 'warning' },
            { date: '2026-07-14', label: '발표', tone: 'muted' },
          ]}
        />
        <StatusRow
          items={[
            { label: 'A/B 테스트', state: 'success', detail: 'UI 선반영' },
            { label: 'YouTube RAG', state: 'muted', detail: '최종 단계 구현 예정 — 아직 미완' },
          ]}
        />
      </div>
    ),
  },
  'memory-architecture': {
    title: '채팅 기억 구조',
    note: '장기기억과 CLIO는 독립적으로 운용.',
    render: () => (
      <LayerStack
        layers={[
          { label: '장기기억 회수', detail: 'tsvector 키워드 기반', tone: 'primary' },
          { label: 'CLIO', detail: '일반 지식 벡터 전용', tone: 'neutral' },
        ]}
      />
    ),
  },
  'sse-sequence': {
    title: 'SSE 스트리밍 흐름',
    note: '',
    render: () => (
      <Pipeline
        vertical
        steps={[
          { label: '클라이언트 요청 전송', tone: 'primary' },
          { label: '서버: gpt-4.1 스트리밍 생성 시작', tone: 'primary' },
          { label: 'SSE로 토큰 단위 전송', tone: 'primary' },
          { label: '클라이언트 실시간 렌더링', tone: 'success' },
        ]}
      />
    ),
  },
};

type Q = { id: string; q: string; exhibitKey: keyof typeof EXHIBITS };
type Domain = { id: string; label: string; icon: React.ReactNode; accent: Tone; questions: Q[] };

export const DOMAINS: Domain[] = [
  {
    id: 'generator',
    label: '제너레이터',
    accent: 'warning',
    icon: <Sparkles size={16} strokeWidth={1.8} />,
    questions: [
      { id: 'g1', q: '시안은 몇 개나 생성하나요?', exhibitKey: 'generation-flow' },
      { id: 'g2', q: '어떤 이미지 생성 모델을 쓰나요?', exhibitKey: 'model-config-table' },
      { id: 'g3', q: '생성된 시안의 순위는 어떻게 매기나요?', exhibitKey: 'qa-ranking' },
      { id: 'g4', q: '결과를 PDF로 받을 수 있나요?', exhibitKey: 'pdf-report-mockup' },
      { id: 'g5', q: '시뮬레이션 결과가 생성에 반영되나요?', exhibitKey: 'prediction-to-generation' },
      { id: 'g6', q: '품질 다이제스트는 무엇인가요?', exhibitKey: 'scheduler-jobs' },
      { id: 'g7', q: 'RAG는 어디에 쓰이나요?', exhibitKey: 'rag-hybrid-search' },
      { id: 'g8', q: '제너레이터 도메인도 DDD 구조인가요?', exhibitKey: 'ddd-generator' },
      { id: 'g9', q: '이미지 생성 모델을 OpenAI와 Gemini 중 선택할 수 있나요?', exhibitKey: 'model-config-table' },
      { id: 'g10', q: '개선 모드와 신규 생성 모드는 뭐가 다른가요?', exhibitKey: 'generation-flow' },
    ],
  },
  {
    id: 'simulation',
    label: '시뮬레이션',
    accent: 'point',
    icon: <Users size={16} strokeWidth={1.8} />,
    questions: [
      { id: 's1', q: '페르소나는 어떻게 만드나요? 실제 사람 데이터인가요?', exhibitKey: 'persona-pipeline' },
      { id: 's2', q: '시뮬레이션 결과가 실제와 얼마나 정확한가요?', exhibitKey: 'decision-goal' },
      { id: 's3', q: '클릭 의향률이 실제 CTR과 같은 건가요?', exhibitKey: 'aisas-funnel' },
      { id: 's4', q: 'SSR이 뭔가요? 왜 기본이 아니라 opt-in인가요?', exhibitKey: 'scoring-pipeline' },
      { id: 's5', q: '초기에 설계했던 2단계(노출+숙고) 구조는 왜 안 쓰나요?', exhibitKey: 'exposure-deliberation' },
      { id: 's6', q: '시뮬레이션에는 어떤 LLM을 쓰나요?', exhibitKey: 'llm-role-matrix-sim' },
      { id: 's7', q: '결과가 하나의 숫자(스칼라)로 나오나요?', exhibitKey: 'distribution-output' },
      { id: 's8', q: '시뮬레이터의 4대 KPI는 무엇인가요?', exhibitKey: 'kpi-definitions' },
      { id: 's9', q: '시뮬레이션 도메인도 DDD 구조로 이전됐나요?', exhibitKey: 'ddd-simulation' },
      { id: 's10', q: '신뢰구간은 어떻게 계산하나요?', exhibitKey: 'bootstrap-ci' },
    ],
  },
  {
    id: 'management',
    label: '매니지먼트',
    accent: 'success',
    icon: <BarChart3 size={16} strokeWidth={1.8} />,
    questions: [
      { id: 'm1', q: '실제 메타(Meta) 광고 계정과 연동되나요?', exhibitKey: 'execution-pipeline' },
      { id: 'm2', q: '자동으로 예산을 바꾸거나 집행하나요? 위험하지 않나요?', exhibitKey: 'execution-modes' },
      { id: 'm3', q: '이상 탐지·리밸런스 같은 비동기 작업은 어떤 구조로 도나요?', exhibitKey: 'scheduler-jobs' },
      { id: 'm4', q: '지금 실제로 라이브 자동 집행이 켜져 있나요?', exhibitKey: 'safety-status' },
      { id: 'm5', q: '승인 단계는 실제로 어떻게 이뤄지나요?', exhibitKey: 'execution-pipeline' },
      { id: 'm6', q: '여러 광고 플랫폼(카카오·네이버 등)도 지원하나요?', exhibitKey: 'platform-matrix' },
      { id: 'm7', q: '팀 단위로 캠페인을 나눠 관리할 수 있나요?', exhibitKey: 'org-hierarchy' },
      { id: 'm8', q: '매니지먼트 도메인도 DDD 구조인가요?', exhibitKey: 'ddd-management' },
      { id: 'm9', q: '기밀 데이터(예산·API 키)는 어떻게 보호하나요?', exhibitKey: 'security-layers' },
      { id: 'm10', q: '이상 탐지는 어떤 주기로 도나요?', exhibitKey: 'scheduler-jobs' },
    ],
  },
  {
    id: 'chat',
    label: '채팅',
    accent: 'primary',
    icon: <MessageSquare size={16} strokeWidth={1.8} />,
    questions: [
      { id: 'c1', q: '채팅은 어떤 모델을 쓰나요?', exhibitKey: 'llm-role-matrix-chat' },
      { id: 'c2', q: '채팅에서 시뮬레이션·매니지먼트·생성 기능을 다 쓸 수 있나요?', exhibitKey: 'deep-agent-routing' },
      { id: 'c3', q: 'deepagents의 서브에이전트 기능을 쓰나요?', exhibitKey: 'deep-agent-routing' },
      { id: 'c4', q: '예전에 있던 오케스트레이터와의 관계는요?', exhibitKey: 'orchestrator-migration' },
      { id: 'c5', q: 'YouTube RAG는 지금 실제로 되나요?', exhibitKey: 'roadmap-timeline' },
      { id: 'c6', q: '채팅이 우선순위가 낮다고 들었는데 왜인가요?', exhibitKey: 'roadmap-timeline' },
      { id: 'c7', q: '채팅에서 대화 맥락(장기기억)은 어떻게 관리하나요?', exhibitKey: 'memory-architecture' },
      { id: 'c8', q: '채팅 응답은 실시간 스트리밍인가요?', exhibitKey: 'sse-sequence' },
      { id: 'c9', q: '채팅 도메인도 DDD 구조를 따르나요?', exhibitKey: 'ddd-chat' },
      { id: 'c10', q: '채팅으로 실제 집행(예산 변경 등)까지 할 수 있나요?', exhibitKey: 'execution-pipeline' },
    ],
  },
];

export type { Domain };
