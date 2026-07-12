// 발표 Q&A 부록 — 실제 최종발표 PPT·발표 스크립트·코드베이스 심층 조사(도메인별)를 근거로, 심사·청중이
// 실제로 물어볼 법한 질문과 그 답변에 쓸 시각 자료(exhibit)를 매핑한다. 지어낸 수치는 없다. PPT·코드가
// 스스로 인정한 한계·미해결 항목은 "미해결"로 그대로 노출한다. 실 보안 취약점(이미 수정 완료)의 공격
// 메커니즘 상세는 공개 페이지 특성상 의도적으로 제외했다(예: OAuth CSRF, 구 채팅/시뮬 무인증 접근).

import {
  AlertTriangle,
  Server,
  Sparkles,
  Users,
  BarChart3,
  MessageSquare,
  Compass,
  Lock,
} from 'lucide-react';
import { Pipeline, LayerStack, Matrix, Timeline, InfoCards, StatusRow, BarDistribution, StepBox, type Tone } from './primitives';

export type Exhibit = { title: string; note: string; render: () => React.ReactNode };

const iconProps = { size: 24, strokeWidth: 1.8 } as const;

export const EXHIBITS: Record<string, Exhibit> = {
  // ── 사업·문제정의 ──────────────────────────────────────────────
  'stat-production-time': {
    title: '캠페인 1건의 제작 기간',
    note: '출처: APQC 벤치마킹(광고 기획~제작 평균 소요 리서치).',
    render: () => (
      <InfoCards
        items={[{ label: '캠페인 1건 제작 기간', value: '2~3주', detail: '시안·카피 제작 기준', tone: 'danger' }]}
      />
    ),
  },
  'stat-refund': {
    title: '실패 시 회수 금액',
    note: '매체 광고비는 소진형으로 선지출되며, 실패해도 환불되지 않는 구조.',
    render: () => (
      <InfoCards
        items={[{ label: '광고 실패 시 회수 금액', value: '0원', detail: '검증 없이 선지출된 매체비는 소진되면 끝', tone: 'danger' }]}
      />
    ),
  },
  'stat-test-budget': {
    title: '테스트성 집행 예산',
    note: '출처: Meta(Facebook) 광고 비즈니스 가이드.',
    render: () => (
      <InfoCards
        items={[{ label: '테스트 삼아 돌려보는 데 드는 비용', value: '50~150만 원', tone: 'danger' }]}
      />
    ),
  },
  'stat-banner-blindness': {
    title: '광고를 무시하는 소비자',
    note: '출처: Nielsen Norman Group, Banner Blindness 리서치.',
    render: () => (
      <InfoCards
        items={[{ label: '광고를 인지조차 못 하고 지나치는 비율', value: '86%', tone: 'danger' }]}
      />
    ),
  },
  'execution-flow-problem': {
    title: '지금까지의 광고 집행 플로우',
    note: '검증 단계가 아예 없다 — 성패를 예산을 다 쓴 뒤에야 안다.',
    render: () => (
      <Pipeline
        steps={[
          { label: '기획·제작', detail: '시안·카피 제작', tone: 'neutral' },
          { label: '예산 배정·집행', detail: '검증 없이 광고비 선지출', tone: 'danger' },
          { label: '결과 확인', detail: '광고비 소진 후에야 확인', tone: 'danger' },
        ]}
      />
    ),
  },
  'service-overview': {
    title: '하나의 플랫폼 — 테스트·개선·집행 관리',
    note: '4개 기능이 한 플랫폼 안에서 이어진다(개별 툴 조합이 아님).',
    render: () => (
      <InfoCards
        items={[
          { label: '제너레이터', value: '집행 가능한 시안 3종', detail: '진단 반영 개선 시안 자동 생성', tone: 'warning' },
          { label: '시뮬레이션', value: '집행 전 반응 예측', detail: '4대 지표를 분포로 제공', tone: 'point' },
          { label: '매니지먼트', value: '집행 후 추적·이상 감지', detail: '집행은 사람 승인으로 통제', tone: 'success' },
          { label: 'AI 채팅', value: '전 과정을 대화로 지시', detail: '시뮬·분석·생성 결과 전달', tone: 'primary' },
        ]}
      />
    ),
  },
  'business-model': {
    title: '비즈니스 모델 — 구독형 3단계',
    note: '무료로 진입 장벽을 없애고, 팀·캠페인이 커질수록 함께 확장.',
    render: () => (
      <InfoCards
        items={[
          { label: '개인·무료', value: 'FREE', detail: '시뮬레이션 체험 · 성과 트래킹 1개', tone: 'neutral' },
          { label: '팀·구독', value: 'Subscribe', detail: '팀 협업·확장 시뮬레이션 · 무제한 트래킹·API 연동', tone: 'primary' },
          { label: '기업·맞춤', value: 'Custom', detail: '대규모·다채널 캠페인 · 전담 지원·맞춤 연동', tone: 'point' },
        ]}
      />
    ),
  },
  'wbs-timeline': {
    title: '개발 일정 — 약 8주 · 6인 · 3개 도메인 병렬',
    note: '주간 통합으로 일정 내 완수.',
    render: () => (
      <Timeline
        events={[
          { date: '2026-06-22', label: '기획·설계', detail: 'DDD 아키텍처·DB Schema·도메인 분리', tone: 'neutral' },
          { date: '2026-06-24', label: '핵심 기능 개발', detail: '시뮬레이션·매니지먼트·제너레이터 병렬 착수', tone: 'point' },
          { date: '2026-07-01', label: '통합·확장', detail: '채팅 오케스트레이션·CI/CD·보안', tone: 'warning' },
          { date: '2026-07-08', label: '안정화·발표 준비', detail: '문서 정리·기능 고도화', tone: 'success' },
        ]}
      />
    ),
  },
  'biz-goals': {
    title: '개발 목표 3원칙',
    note: '이 세 가지를 정확히 세워둔 덕에 이후 개발 순서·우선순위를 흔들리지 않고 정할 수 있었다.',
    render: () => (
      <StatusRow
        items={[
          { label: 'AI가 수치를 지어내지 않는다', state: 'primary', detail: '신뢰구간·집계 같은 정량 계산은 코드가 담당, LLM은 정성 판단만' },
          { label: '돈이 움직이는 결정은 사람이 승인한다', state: 'primary', detail: '집행(write)은 예외 없이 사람 승인' },
          { label: '네 기능을 하나의 흐름으로 연결한다', state: 'primary', detail: '제너레이터·시뮬레이션·매니지먼트·채팅이 개별 툴이 아니라 한 파이프라인' },
        ]}
      />
    ),
  },

  // ── 기술·인프라 ──────────────────────────────────────────────
  'infra-topology': {
    title: '기술 아키텍처',
    note: '단일 EC2 · Docker Compose — 확장성보다 8주 내 완주를 우선한 선택.',
    render: () => (
      <LayerStack
        layers={[
          { label: 'Nginx', detail: '리버스 프록시 · TLS 자동 갱신', tone: 'neutral' },
          { label: 'Frontend', detail: 'Next.js · Tailwind', tone: 'neutral' },
          { label: 'Backend — FastAPI 모놀리식(DDD)', detail: '시뮬레이션 · 매니지먼트 · 광고 생성 · 채팅 오케스트레이션', tone: 'primary' },
          { label: 'APScheduler 워커', detail: '이상 스캔 · 리포트', tone: 'neutral' },
          {
            label: '외부 연동',
            detail: 'AWS Cognito(인증) · NeonDB(pgvector, 하이브리드 RAG) · S3 · LLM API(OpenAI·Gemini·Anthropic) · Meta Marketing API · LangSmith',
            tone: 'neutral',
          },
        ]}
      />
    ),
  },
  'rag-architecture': {
    title: '하이브리드 RAG 검색',
    note: 'RRF(Reciprocal Rank Fusion)로 벡터 검색과 키워드 검색을 융합.',
    render: () => (
      <div className="space-y-3">
        <div className="flex flex-wrap gap-3">
          <StepBox label="벡터 검색" detail="pgvector 코사인" tone="neutral" />
          <StepBox label="키워드 검색" detail="PostgreSQL FTS" tone="neutral" />
        </div>
        <div className="ml-6 h-5 w-px bg-line-strong" />
        <StepBox label="RRF 융합" tone="primary" />
        <div className="ml-6 h-5 w-px bg-line-strong" />
        <StepBox label="지식베이스(KB) 조회 결과" tone="primary" />
      </div>
    ),
  },
  'cicd-pipeline': {
    title: 'CI/CD — 검증·빌드·배포·인증서 갱신 자동화',
    note: 'CI 실패 시 병합 차단으로 품질 게이트 유지.',
    render: () => (
      <Pipeline
        steps={[
          { label: 'Code Push', tone: 'neutral' },
          { label: 'GitHub Actions', detail: 'Ruff·pytest·Playwright(E2E)', tone: 'neutral' },
          { label: 'Image Build', tone: 'neutral' },
          { label: 'EC2', tone: 'neutral' },
          { label: 'Deploy', detail: 'Docker + Nginx', tone: 'success' },
        ]}
      />
    ),
  },
  'security-layers': {
    title: '운영·보안',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: "Let's Encrypt TLS", state: 'success', detail: '인증서 자동 발급·갱신' },
          { label: 'AWS Cognito', state: 'success', detail: 'JWT·RS256 기반 인증 체계' },
          { label: 'IAM 분리 · GitHub Secrets 최소화', state: 'success', detail: '배포 전용 권한 분리' },
        ]}
      />
    ),
  },
  'multi-llm': {
    title: '역할별 LLM 분리 배정',
    note: '하나의 모델에 몰지 않고, 역할별로 비용·품질 균형을 맞춤.',
    render: () => (
      <Matrix
        columns={['제공사']}
        rows={[
          { label: '채팅·생성', cells: [{ text: 'OpenAI' }] },
          { label: '시뮬레이션 반응', cells: [{ text: 'Gemini' }] },
          { label: '토론 Judge 등', cells: [{ text: 'Anthropic' }] },
        ]}
      />
    ),
  },
  'infra-portainer': {
    title: '컨테이너 상태 모니터링',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: 'GitHub Actions', state: 'neutral', detail: 'CI/CD 자동화' },
          { label: 'Docker 컨테이너화', state: 'neutral' },
          { label: 'Portainer', state: 'primary', detail: '컨테이너 상태 모니터링' },
        ]}
      />
    ),
  },
  'infra-needs-chain': {
    title: '테스트 실패 시 배포 차단',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '테스트(backend/frontend) 실패', state: 'danger', detail: '빌드 job 자체가 실행되지 않음(needs 체인)' },
          { label: '이미지 빌드 실패', state: 'danger', detail: '배포 job도 실행되지 않음' },
          { label: '동시 배포 요청', state: 'neutral', detail: '취소가 아니라 대기열(큐잉)' },
        ]}
      />
    ),
  },
  'infra-e2e-manual': {
    title: 'E2E(Playwright)는 수동 실행',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: 'workflow_dispatch로만 실행', state: 'neutral', detail: '매 PR/push마다 자동 실행 안 함' },
          { label: '이유 — 비용', state: 'muted', detail: '시뮬·토론 시나리오가 실제 LLM을 호출' },
          { label: '이유 — 데이터', state: 'muted', detail: '시드된 테스트 계정·프로젝트가 있어야 동작' },
        ]}
      />
    ),
  },
  'infra-secrets': {
    title: 'GitHub Secrets 최소화',
    note: '',
    render: () => (
      <InfoCards
        items={[
          { label: '실제 시크릿', value: '6개', detail: 'AWS 키 2개·EC2 HOST·EC2 SSH_KEY·OPENAI_API_KEY·E2E_DATABASE_URL', tone: 'neutral' },
          { label: '평문으로 두는 값', value: 'Cognito 설정값 등', detail: 'NEXT_PUBLIC_ 접두사라 어차피 프론트 번들에 노출되는 공개값', tone: 'neutral' },
        ]}
      />
    ),
  },
  'infra-docs-check': {
    title: '문서-코드 어긋남 방지',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: 'CI Docs drift check', state: 'success', detail: '라우터·페이지 추가 후 문서를 안 갱신하면 CI가 실패' },
        ]}
      />
    ),
  },
  'infra-migration-cleanup': {
    title: 'DB 마이그레이션 정리',
    note: '',
    render: () => (
      <Timeline
        events={[
          { date: '이전', label: '리비전 8개 지점 중복', detail: '브랜치 간 충돌로 upgrade head 막힘', tone: 'muted' },
          { date: '발표 전', label: '최소 조치', detail: '멱등 DDL(ADD COLUMN IF NOT EXISTS)만 적용', tone: 'warning' },
          { date: '이후', label: '완전 선형화', detail: '0001~0011로 재정리', tone: 'success' },
        ]}
      />
    ),
  },
  'infra-admin-delete': {
    title: '관리자 삭제는 소프트 삭제',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: 'Hard delete 아님', state: 'success', detail: 'status=INACTIVE 처리 + Cognito 계정 비활성화' },
          { label: '복원 가능', state: 'success', detail: 'status=ACTIVE로 되돌리면 복원' },
          { label: '완전 삭제(purge)', state: 'muted', detail: '별도 조작을 해야 실제로 행이 삭제됨' },
        ]}
      />
    ),
  },

  // ── 제너레이터 ──────────────────────────────────────────────
  'gen-korean-typo': {
    title: '이미지 속 한글 깨짐 — 실사례',
    note: '문제: AI가 이미지에 직접 쓴 한글 라벨이 깨짐.',
    render: () => (
      <StatusRow
        items={[
          { label: '광고 카피는 AI가 아닌 PIL로 직접 합성', state: 'success', detail: '오타율 0%' },
          { label: '광고 라벨 이미지 모델 전환', state: 'success', detail: 'OpenAI → Gemini, 오타율 89% 감소·비용 유지' },
        ]}
      />
    ),
  },
  'gen-langsmith-gap': {
    title: 'LangSmith 비용 관측 공백 — 미해결',
    note: 'PPT에도 결과가 비어 있던 항목 — 아직 해결 진행 중이라고 정직하게 답할 것.',
    render: () => (
      <StatusRow
        items={[
          { label: 'LangSmith가 비용의 85%를 관측하지 못함', state: 'danger', detail: '자동 추적은 LangChain/LangGraph로 도는 텍스트 LLM 한정' },
          { label: '이미지 생성 등 텍스트 LLM 밖 API 비용은 놓침', state: 'muted', detail: '해결 방안 진행 중(결과 미확정)' },
        ]}
      />
    ),
  },
  'gen-flow': {
    title: '시안 생성 흐름',
    note: '',
    render: () => (
      <Pipeline
        steps={[
          { label: '요구사항 입력', tone: 'neutral' },
          { label: '시안 3종 자동 생성', tone: 'warning' },
          { label: 'QA 기반 순위', tone: 'warning' },
        ]}
      />
    ),
  },
  'gen-diversity': {
    title: '시안 3종의 다양성 보장',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '전략 3계열을 프롬프트로 강제', state: 'warning', detail: '템플릿 A·C 계열 각 1개 + FOMO(B) 반드시 포함' },
          { label: 'LLM 호출이 통째로 실패해도', state: 'success', detail: '기본 3종(BENEFIT·FOMO·SOCIAL_PROOF)으로 보강' },
        ]}
      />
    ),
  },
  'gen-gemini-copy': {
    title: 'Gemini 모드에서도 카피는 텍스트 LLM 전담',
    note: '',
    render: () => (
      <Timeline
        events={[
          { date: '이전', label: '이미지 모델이 카피까지 생성', detail: '카피가 약 80% 확률로 통째 누락되는 버그 발견', tone: 'muted' },
          { date: '이후', label: '카피는 항상 gpt-4.1 텍스트 LLM', detail: '이미지 모델이 준 카피는 버림', tone: 'success' },
        ]}
      />
    ),
  },
  'gen-retry': {
    title: '이미지 생성 실패 시 재시도',
    note: '',
    render: () => (
      <Pipeline
        steps={[
          { label: '동시 요청 1개로 직렬화', tone: 'neutral' },
          { label: '503·429·이미지 누락 감지', tone: 'warning' },
          { label: '백오프 재시도(최대 3회)', tone: 'success' },
        ]}
      />
    ),
  },
  'gen-ranking-basis': {
    title: '시안 순위는 클릭률 예측이 아니다',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '예측 CTR 환산 아님', state: 'muted', detail: '이미지 모델은 카피 품질만 평가' },
          { label: 'QA 규칙 점수 기반 상대 순위', state: 'neutral' },
        ]}
      />
    ),
  },
  'gen-qa-honest': {
    title: '품질검증 7항목 중 3개만 실검증',
    note: '정직한 한계 — 팀도 문서에 이미 명시해둔 상태.',
    render: () => (
      <StatusRow
        items={[
          { label: '실제 규칙 기반 검증', state: 'success', detail: '글자 수 · CTA 존재 · 중복 여부 3항목' },
          { label: '항상 통과 처리(스텁)', state: 'muted', detail: '오타·가독성·타겟적합성·브랜드일관성 4항목' },
        ]}
      />
    ),
  },
  'gen-banned-words': {
    title: '과대광고 표현 필터',
    note: '',
    render: () => (
      <InfoCards
        items={[{ label: '금칙 표현', value: '15개', detail: '100%·보장·기적·완치·즉시효과·넘버원·최고·완벽·1위 등', tone: 'warning' }]}
      />
    ),
  },
  'gen-improve-redesign': {
    title: '개선 모드는 기존 이미지를 직접 고치지 않는다',
    note: '',
    render: () => (
      <Timeline
        events={[
          { date: '초기 설계', label: '기존 광고 이미지 직접 수정', detail: '텍스트 이중노출 문제로 폐기', tone: 'muted' },
          { date: '현재', label: '시뮬 피드백 기반 신규 생성', detail: '기존 이미지는 텍스트 힌트로만 사용(픽셀 로드 안 함)', tone: 'success' },
        ]}
      />
    ),
  },
  'gen-cutout-fallback': {
    title: '상품 이미지(누끼) 3단계 폴백',
    note: '',
    render: () => (
      <Pipeline
        steps={[
          { label: '요청에 담긴 누끼 직접 로드', tone: 'success' },
          { label: '같은 생성 건의 키 재구성', tone: 'warning' },
          { label: '즉석 배경 제거 후 검증', detail: '불투명도·연결성분 기준 통과해야 채택', tone: 'muted' },
        ]}
      />
    ),
  },
  'gen-chat-cutout-gap': {
    title: '채팅 경로는 아직 누끼 재사용 불가',
    note: '',
    render: () => (
      <StatusRow items={[{ label: '채팅에서 개선모드 진입 시', state: 'muted', detail: 'Simulation↔Generation DB 미연결로 누끼 추적 불가, null 폴백으로 생성' }]} />
    ),
  },
  'gen-loop-limit': {
    title: '자동 개선 루프의 한계값',
    note: '',
    render: () => (
      <InfoCards
        items={[
          { label: '목표 품질 점수', value: '0.8', tone: 'warning' },
          { label: '최대 반복 · 타임아웃', value: '3회 · 600초', tone: 'warning' },
        ]}
      />
    ),
  },
  'gen-loop-axis': {
    title: '개선 루프가 "무엇을 고칠지" 정하는 기준',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '4개 KPI 축 비교', state: 'neutral', detail: '클릭의향·구매의도·신뢰도·거부율' },
          { label: '목표 대비 가장 못 미치는 1축 선정', state: 'warning', detail: '그 축의 개선 패턴을 반복마다 고정 주입' },
        ]}
      />
    ),
  },
  'gen-font': {
    title: '한글 폰트 처리',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: 'Pretendard, CDN 런타임 로드', state: 'neutral', detail: '저장소에 내장하지 않고 다운로드해 캐시' },
          { label: '다운로드 실패 시', state: 'muted', detail: '보유 웨이트 중 가장 가까운 것으로 자동 폴백' },
        ]}
      />
    ),
  },
  'gen-contrast-bug': {
    title: '밝은 브랜드 컬러에서 버튼 글씨가 안 보이던 문제',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '파스텔·연회색 브랜드 컬러', state: 'danger', detail: '텍스트/배경 대비가 거의 없어 실측으로 확인됨' },
          { label: '휘도 임계값 기준 보정', state: 'success', detail: '강조색-검정 혼합으로 최소 대비 보장' },
        ]}
      />
    ),
  },
  'gen-inpaint-cost': {
    title: '인페인팅은 항상 켜짐 — 비용 트레이드오프 인지',
    note: '',
    render: () => (
      <StatusRow items={[{ label: '변종 1개당 이미지 API 2회 호출', state: 'warning', detail: '배경 생성 + 인페인팅, 비용 상승을 인지한 확정 결정' }]} />
    ),
  },
  'gen-restart': {
    title: '서버 재시작 시 진행 중이던 생성 작업',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '인프로세스 방식', state: 'muted', detail: '프로세스가 죽으면 pending에 고정' },
          { label: '30분 주기 정체 감지', state: 'neutral', detail: '관측만(자동 정정은 안 함)' },
          { label: '24시간 주기 품질 다이제스트', state: 'neutral' },
        ]}
      />
    ),
  },

  // ── 시뮬레이션 ──────────────────────────────────────────────
  'sim-ssr-flat': {
    title: 'SSR 도입 실패 근거 ① — 판별력 없음',
    note: '긍정·부정 반응의 앵커 유사도가 0.442~0.496로 거의 붙어 있음(폭 0.055) — y축을 확대 표시.',
    render: () => (
      <BarDistribution
        hue="danger"
        scaleMin={0.4}
        bars={[
          { label: '전혀 못 믿음', value: 0.454, display: '0.454' },
          { label: '의심스러움', value: 0.452, display: '0.452' },
          { label: '반신반의', value: 0.442, display: '0.442' },
          { label: '대체로 믿음', value: 0.496, display: '0.496' },
          { label: '충분히 믿음', value: 0.452, display: '0.452' },
        ]}
      />
    ),
  },
  'sim-ssr-inversion': {
    title: 'SSR 도입 실패 근거 ② — 점수 역전',
    note: '"전혀 못 믿겠다"는 부정 반응이 SSR에서는 오히려 높은 신뢰도로 뒤집힘.',
    render: () => (
      <InfoCards
        items={[
          { label: 'LLM 루브릭 판정', value: '신뢰도 2점', detail: '"못 믿겠다" 반응 — 정상 판정', tone: 'success' },
          { label: 'SSR 판정(같은 반응)', value: '신뢰도 4점 최빈값(63%)', detail: '"대체로 믿음"으로 역전 — 오판정', tone: 'danger' },
        ]}
      />
    ),
  },
  'sim-ssr-rollback': {
    title: 'SSR opt-in, 기본값은 롤백',
    note: '실패 근거가 명확해 하루 만에 기본값으로 되돌림.',
    render: () => (
      <Timeline
        events={[
          { date: '평상시', label: 'LLM 루브릭 채점(기본값)', tone: 'point' },
          { date: '2026-07-08', label: 'SSR 기본 ON 시도', tone: 'warning' },
          { date: '2026-07-09', label: '문제 확인 후 기본값 롤백', tone: 'success' },
        ]}
      />
    ),
  },
  'sim-ssr-flipflop': {
    title: 'SSR 기본값, 사흘 새 네 번 뒤집힘',
    note: '최종 결론: 임베딩 앵커 판별력 부족 + 극성 역전이 실측으로 확인돼 기본값 롤백으로 확정.',
    render: () => (
      <Timeline
        events={[
          { date: '7/8 오전', label: 'LLM → SSR 전환', tone: 'warning' },
          { date: '7/9 오전', label: '조기 전환 revert', detail: 'LLM으로 복귀', tone: 'muted' },
          { date: '7/9 낮', label: '테스트 어긋남 수정', detail: '다시 SSR로', tone: 'warning' },
          { date: '7/9 오후', label: '최종 LLM 롤백', detail: '기본값 확정', tone: 'success' },
        ]}
      />
    ),
  },
  'sim-dead-code': {
    title: 'exposure/deliberation 2단계 — 완전한 죽은 코드',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '초기 설계(2단계 LLM 체인)', state: 'muted', detail: '저장소 어디서도 import되지 않음' },
          { label: '실제 운영 경로', state: 'success', detail: '페르소나당 LLM 1콜 단일 설계로 대체' },
        ]}
      />
    ),
  },
  'sim-anchor-design': {
    title: 'SSR 앵커 설계',
    note: '',
    render: () => (
      <InfoCards
        items={[
          { label: '앵커 차원', value: '8개', detail: 'attention·sentiment·click_intent·comprehension·trust 등', tone: 'point' },
          { label: '척도 · 임베딩 모델', value: '각 5단계', detail: 'text-embedding-3-small', tone: 'point' },
        ]}
      />
    ),
  },
  'sim-bootstrap-detail': {
    title: '부트스트랩 신뢰구간 상세',
    note: '',
    render: () => (
      <InfoCards
        items={[
          { label: '반복 횟수', value: '2,000회', tone: 'point' },
          { label: '재현성', value: '시드 고정', detail: '같은 데이터엔 항상 같은 결과', tone: 'point' },
        ]}
      />
    ),
  },
  'sim-age-thresholds': {
    title: '페르소나 샘플링 임계값',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '최소 나이 14세', state: 'neutral', detail: 'OCEAN 논문 표본 하한' },
          { label: '개방형 연령 상한 84세 캡', state: 'neutral' },
          { label: '층화 셀당 최소 표본 10명', state: 'neutral' },
        ]}
      />
    ),
  },
  'sim-region-fallback': {
    title: '지역 데이터 결측 시 폴백',
    note: '',
    render: () => (
      <StatusRow items={[{ label: '행안부 원본에 시도 데이터 없을 때', state: 'muted', detail: '지역 가중치 폴백을 코드에 직접 고정(서울 18%·경기 26% 등 8개 항목)' }]} />
    ),
  },
  'sim-sample-principle': {
    title: '왜 전 국민을 다 시뮬레이션하지 않나',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '여론조사와 동일한 원리', state: 'neutral', detail: '표본 + 가중치로 전국 추정' },
          { label: '표본 부풀리기 금지', state: 'danger', detail: '가중치·복제로 가짜 정밀도 만드는 것 명시적 금지' },
          { label: '300명 미만 표본', state: 'muted', detail: '신뢰도 하향 표기' },
        ]}
      />
    ),
  },
  'sim-panel-bug': {
    title: '표본 5명 요청에 43명이 실행되던 버그',
    note: '',
    render: () => (
      <Timeline
        events={[
          { date: '버그', label: '고정 패널이 요청 수 무시', detail: '필터 통과분 전원 반환 — 비용 폭증', tone: 'danger' },
          { date: '수정', label: '결정적 서브샘플링', detail: '요청 수만큼만 시드 기반으로 자름', tone: 'success' },
        ]}
      />
    ),
  },
  'sim-debate-tiebreak': {
    title: '토론 결과가 갈릴 때',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: 'LLM 셀렉터 3표 다수결', state: 'point' },
          { label: '표가 갈리면', state: 'muted', detail: '결정론 폴백(id순)으로 되돌림' },
        ]}
      />
    ),
  },
  'sim-kobaco-gap': {
    title: 'KOBACO 실측 벤치마크의 빈틈',
    note: '정직한 한계 — 모든 카테고리에 실측치가 있는 건 아니다.',
    render: () => (
      <StatusRow
        items={[
          { label: '2019 KOBACO는 8대 업종만 조사', state: 'muted', detail: '교육 카테고리는 실측치 자체가 없음' },
          { label: '뷰티·패션·식품·음료', state: 'muted', detail: '구매의향 문항이 없어 참고 지표로만 대체' },
        ]}
      />
    ),
  },
  'sim-interest-conditional': {
    title: '관심층 한정 조건부 지표',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: 'Interest 통과자만 별도 집계', state: 'point', detail: 'Meta가 관심 유저를 선별 노출하는 특성 반영' },
          { label: '유효표본 5명 미만이면', state: 'muted', detail: '참고용 플래그 표기' },
        ]}
      />
    ),
  },
  'sim-brand-awareness-excluded': {
    title: '종합 점수에서 브랜드 인지도를 뺀 이유',
    note: '',
    render: () => (
      <StatusRow items={[{ label: '브랜드 식별은 전달력 지표', state: 'neutral', detail: '불쾌한 광고도 브랜드는 각인될 수 있어 품질 점수에서 의도적으로 제외' }]} />
    ),
  },
  'sim-segment-heatmap-gate': {
    title: '세그먼트 히트맵이 안 나올 때',
    note: '',
    render: () => (
      <StatusRow items={[{ label: '셀당 유효표본 20명 미만', state: 'muted', detail: '히트맵 대신 안내 문구로 대체' }]} />
    ),
  },
  'sim-validation-method': {
    title: '"실제 사람과 비슷한지" 검증 방식',
    note: '정직한 한계 — 외부 실측 비교가 아니라 내부 자기일관성 테스트.',
    render: () => (
      <StatusRow
        items={[
          { label: '내부 방향성 검증', state: 'neutral', detail: '"연령↑ → 거부율↑·구매의도↓" 가설을 5개 연령밴드로 검증' },
          { label: '외부 실측(KISDI 등) 비교', state: 'muted', detail: '원래 계획했으나 아직 미구현' },
        ]}
      />
    ),
  },
  'sim-report-timeout': {
    title: '리포트 생성 타임아웃 개선',
    note: '',
    render: () => (
      <InfoCards
        items={[
          { label: '개선 전', value: '93.7초', detail: '45개 시뮬 순차 호출 — 타임아웃', tone: 'danger' },
          { label: '개선 후', value: '17.7초', detail: '병렬화, 5.3배 단축', tone: 'success' },
        ]}
      />
    ),
  },
  'sim-json-truncation': {
    title: '토론 결론 JSON이 잘리던 버그',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '한국어는 토큰 소모가 커서 반복 발생', state: 'danger', detail: '결론 JSON이 중간에 잘림' },
          { label: 'max_tokens 확대 + 마크다운 제거', state: 'success', detail: '여러 차례에 걸쳐 수정' },
        ]}
      />
    ),
  },
  'sim-debate-size': {
    title: '토론 참여 인원 구성',
    note: '',
    render: () => (
      <Matrix
        columns={['인원', '모델']}
        rows={[
          { label: '일반인', cells: [{ text: '2~4명(기본 3)' }, { text: 'gpt-4o-mini' }] },
          { label: '도메인·마케팅 전문가', cells: [{ text: '고정 4명' }, { text: 'gpt-4o-mini' }] },
          { label: 'Judge', cells: [{ text: '1명' }, { text: 'Claude Haiku' }] },
        ]}
      />
    ),
  },
  'sim-reachability': {
    title: '도달 불가능한 표본 문제',
    note: '',
    render: () => (
      <Timeline
        events={[
          { date: '문제', label: '광고가 닿지 않을 사람까지 표본 포함', tone: 'danger' },
          { date: '해결', label: 'Meta 실측 도달 분포로 표본 재추출', tone: 'success' },
        ]}
      />
    ),
  },
  'sim-debate-before-after': {
    title: '페르소나 토론 재구성',
    note: '일반인끼리의 반응 교환만으로는 실무에 쓸 인사이트가 안 나옴.',
    render: () => (
      <div className="space-y-5">
        <div>
          <p className="mb-2 text-xs font-semibold text-ink-tertiary">BEFORE — 일반인 3명만</p>
          <Pipeline steps={[{ label: '반응 제시', tone: 'muted' }, { label: '반응에 대한 피드백', detail: '단순 반응 교환에 그침', tone: 'muted' }]} />
        </div>
        <div>
          <p className="mb-2 text-xs font-semibold text-ink-tertiary">AFTER — 역할 분리</p>
          <Pipeline
            steps={[
              { label: '일반인(기본 3)', detail: '소비자 반응 제시', tone: 'point' },
              { label: '도메인·마케팅 전문가(각 2)', detail: '해석 + 개선 방향 제시', tone: 'success' },
            ]}
          />
        </div>
      </div>
    ),
  },
  'sim-limits': {
    title: '시뮬레이션 정확도의 한계',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '예측은 실측을 100% 재현하지 않음', state: 'muted', detail: '대체하는 것은 감·내부 회의 수준' },
          { label: '도달 분포는 generic SNS 기준', state: 'muted', detail: '플랫폼 특정 정밀도에는 한계' },
          { label: '한국 소비심리(체면·동조·눈치)', state: 'muted', detail: '데이터 확보 전까지 반영하지 않는 원칙' },
        ]}
      />
    ),
  },

  // ── 매니지먼트 ──────────────────────────────────────────────
  'mgmt-rebalance-flow': {
    title: '예산 리밸런싱 — 감지→제안→승인→집행',
    note: 'CPC 격차 1.2배 초과 시에만 제안 — 노이즈성 제안을 걸러냄.',
    render: () => (
      <Pipeline
        steps={[
          { label: '감지', detail: 'APScheduler 24시간 실측 CPC 스캔', tone: 'neutral' },
          { label: '제안', detail: '격차 1.2배 초과 시 일예산 20% 이전 제안', tone: 'warning' },
          { label: '승인', icon: <Lock {...iconProps} />, detail: '사용자 승인 필수(HITL)', tone: 'warning' },
          { label: '집행', detail: '실패 시 복원 — 과금 오판 차단', tone: 'success' },
        ]}
      />
    ),
  },
  'mgmt-rebalance-example': {
    title: '리밸런싱 실제 예시',
    note: '성과와 무관하게 동일 배분되던 예산을, 실측 CPC 기준으로 재분배.',
    render: () => (
      <InfoCards
        items={[
          { label: '광고 A (CPC ₩1,000·저효율)', value: '₩500,000 → ₩300,000', tone: 'muted' },
          { label: '광고 B (CPC ₩500·A 대비 50%낮음)', value: '₩500,000 → ₩700,000', tone: 'success' },
        ]}
      />
    ),
  },
  'mgmt-meta-tier': {
    title: 'Meta API 등급 제약 — 실사례',
    note: '개발 지연과 실측 데이터 부재라는 실제 제약을 정면 돌파.',
    render: () => (
      <StatusRow
        items={[
          { label: 'Meta API Advanced 등급 승급 대기 중', state: 'warning', detail: '대기 기간 동안 필요한 기능 선제 구현' },
          { label: '사비로 실제 Meta 캠페인 집행', state: 'success', detail: '실측 데이터(CTR·CPC·CPM·CVR·ROAS) 확보' },
          { label: 'CVR → "클릭 후 설문 제출률"로 대체', state: 'muted', detail: '완전한 대체재는 아닌 임시 프록시 지표' },
        ]}
      />
    ),
  },
  'mgmt-hitl': {
    title: '집행은 항상 사람 승인',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '관측·집계·이상 감지', state: 'success', detail: '워커가 자율 수행' },
          { label: '실제 예산 집행(write)', state: 'warning', detail: '사람 승인 없이는 실행되지 않음' },
        ]}
      />
    ),
  },
  'mgmt-budget-tiers': {
    title: '예산 초과 3단계 안전장치',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '90% 도달 — 경고(WARN)', state: 'warning' },
          { label: '95% 도달 — 자동승인 불가(ESCALATE)', state: 'danger', detail: '반드시 사람 승인 라우팅' },
          { label: '100%대 — 차단(BLOCK)', state: 'danger' },
        ]}
      />
    ),
  },
  'mgmt-auto-approver': {
    title: '자동승인(AUTO)의 범위',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '조회 · 중지 · 감액(Tier 0~1)', state: 'success', detail: '자율 통과 가능' },
          { label: '재배분 · 증액 · 신규집행 · 소재교체(Tier 2~3)', state: 'danger', detail: '자동승인이면 무조건 거부, 사람 승인 필수' },
        ]}
      />
    ),
  },
  'mgmt-anomaly-guardrail': {
    title: '이상 감지 오탐 방지',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '관측 시간 3시간 미만', state: 'muted', detail: '판단 보류' },
          { label: '비교 기준값 없음', state: 'muted', detail: '자동 pause로 안 이어지게 별도 분리' },
          { label: '2회 연속 관측', state: 'success', detail: '이상으로 확정' },
        ]}
      />
    ),
  },
  'mgmt-notify-channel': {
    title: '이상 감지 알림 채널 설계',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '3가지 안 비교 후 하이브리드 채택', state: 'neutral', detail: '패널에 요약 + [상담하기] 클릭 시 채팅 진입' },
          { label: '중복 알림 억제', state: 'success', detail: '이중 방어로 같은 이상은 재통지 안 함' },
        ]}
      />
    ),
  },
  'mgmt-rebalance-timeout-bug': {
    title: '리밸런싱 집행 코드의 실제 버그',
    note: '',
    render: () => (
      <Timeline
        events={[
          { date: '발견', label: '증액 요청 타임아웃', detail: '실제로는 적용됐는데 응답만 유실됐을 가능성', tone: 'danger' },
          { date: '위험', label: '무조건 보상(원복)하면', detail: '증액+원복이 중복 반영될 수 있음', tone: 'warning' },
          { date: '수정', label: '타임아웃 시 무보상 처리', detail: '불확정 상태로 박제, 원복하지 않음', tone: 'success' },
        ]}
      />
    ),
  },
  'mgmt-mock-drift-bug': {
    title: '데모용 mock 데이터의 실제 버그',
    note: '',
    render: () => (
      <Timeline
        events={[
          { date: '버그', label: 'mock 예산 정본이 두 군데', detail: '리밸런싱 적용 시 값이 어긋나 충돌', tone: 'danger' },
          { date: '수정', label: '단일 정본으로 통일', tone: 'success' },
        ]}
      />
    ),
  },
  'mgmt-worker-proposal-only': {
    title: '워커는 제안만, 실행은 사람',
    note: '',
    render: () => (
      <StatusRow items={[{ label: '예산 재배분 워커', state: 'neutral', detail: '제안까지만 생성 — 실제 예산 이동은 항상 사람 승인' }]} />
    ),
  },
  'mgmt-worker-isolation': {
    title: '워커 실패는 격리됨',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '한 잡의 실패가 스케줄러 전체를 안 죽임', state: 'success' },
          { label: '연속 실패 알림·dead letter', state: 'muted', detail: '아직 범위 밖이라고 정직하게 문서화' },
        ]}
      />
    ),
  },
  'mgmt-eval-accuracy': {
    title: '진단 정확도 목표치',
    note: '',
    render: () => (
      <InfoCards
        items={[
          { label: '성과 미달 진단', value: '오탐 0건 · 정확도 99%+', tone: 'success' },
          { label: '게재 고장 진단', value: '목표 80%+', tone: 'success' },
        ]}
      />
    ),
  },
  'mgmt-chat-realtest': {
    title: '채팅으로 매니지먼트 실사용 테스트',
    note: '백엔드 로직 자체는 정상 — 원인은 LLM 라우팅·렌더링 쪽으로 좁혀짐.',
    render: () => (
      <StatusRow
        items={[
          { label: '복합 요청 시 오케스트레이터 간헐적 오류', state: 'muted' },
          { label: '타깃 질문에 다른 캠페인 소재로 답하는 맥락 혼선', state: 'muted' },
          { label: '일부 위젯 카드가 텍스트로만 표시', state: 'muted' },
        ]}
      />
    ),
  },
  'mgmt-dual-path-honest': {
    title: '제너레이터→매니지먼트 경로가 두 갈래',
    note: '둘 다 일시중지 상태로만 생성돼 실지출 없음 — 발표까지는 공존 인정, 완전 통합은 이후로.',
    render: () => (
      <StatusRow
        items={[
          { label: '제너레이터 직행 경로', state: 'muted', detail: '승인·감사 미적용' },
          { label: '매니지먼트 통제 경로', state: 'success', detail: '승인·감사 적용' },
        ]}
      />
    ),
  },
  'mgmt-result-read-gap': {
    title: '시뮬레이션 결과 재조회 API 공백',
    note: '',
    render: () => (
      <Timeline
        events={[
          { date: '이전', label: '재조회 API 없음', detail: '필요할 때마다 재실행(비용 발생)', tone: 'danger' },
          { date: '이후', label: '저장된 결과 읽기 엔드포인트 추가', tone: 'success' },
        ]}
      />
    ),
  },
  'mgmt-mock-trap': {
    title: 'USE_MOCK 설정의 함정',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '전역 USE_MOCK=true', state: 'danger', detail: '채팅 에이전트 자체가 통째로 꺼짐' },
          { label: 'MANAGEMENT_READER_MOCK', state: 'success', detail: '매니지먼트 읽기만 따로 mock 처리하는 전용 스위치' },
        ]}
      />
    ),
  },

  // ── 채팅 ──────────────────────────────────────────────
  'chat-rag-problem': {
    title: 'RAG 검색 정확도 문제',
    note: '단일 테이블 정보는 잘 가져오지만, 복합 테이블 정보는 놓침.',
    render: () => (
      <Pipeline
        steps={[
          { label: '초기 RAG', detail: '정답 문서가 상위에 안정적으로 노출 안 됨', tone: 'danger' },
        ]}
      />
    ),
  },
  'chat-rag-improvement': {
    title: 'RAG 개선 — 실측 지표',
    note: '출처: Ragas, LLM-as-Judge 기반 평가.',
    render: () => (
      <Matrix
        columns={['개선 전', '개선 후']}
        rows={[
          { label: 'Hit Rate@K(복합)', cells: [{ text: '0.800' }, { text: '1.000', tone: 'success' }] },
          { label: 'MRR(복합)', cells: [{ text: '0.634' }, { text: '0.833', tone: 'success' }] },
          { label: 'Faithfulness', cells: [{ text: '신규 측정' }, { text: '1.000', tone: 'success' }] },
          { label: 'Factual Correctness(복합)', cells: [{ text: '0.857' }, { text: '0.971', tone: 'success' }] },
        ]}
      />
    ),
  },
  'chat-rag-metric-split': {
    title: 'Hit Rate·MRR vs LLM-as-Judge — 각각 뭘 고쳤나',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: 'Hit Rate · MRR', state: 'primary', detail: '청크 크기 조정·리랭커 도입 등 통상적 방식으로 초기 검색 정확도 문제 해결' },
          { label: 'LLM-as-Judge(Context Precision·Faithfulness 등)', state: 'primary', detail: 'Ragas 문서 기법 차용 — 프롬프트 강화·랭킹 알고리즘·few-shot 보강으로 복합 테이블 문제 해결' },
        ]}
      />
    ),
  },
  'chat-hallucination': {
    title: '환각 억제 방법',
    note: '함정 질문 23개를 별도로 평가.',
    render: () => (
      <StatusRow
        items={[
          { label: 'CRAG 기반 자기교정', state: 'success' },
          { label: '근거 확인 → 재검색 → 답변 거절', state: 'success', detail: '근거 없으면 억지로 답하지 않음' },
        ]}
      />
    ),
  },
  'chat-orchestrator-history': {
    title: '채팅 오케스트레이터 구조 전환',
    note: '',
    render: () => (
      <Timeline
        events={[
          { date: '이전', label: '의도분류 + 수제 계획-실행 루프 2중 구조', detail: '유지보수 부담', tone: 'muted' },
          { date: '현재', label: 'deepagents 단일 호출로 통합', tone: 'success' },
        ]}
      />
    ),
  },
  'chat-subagent-reason': {
    title: 'deepagents 네이티브 서브에이전트를 안 쓴 이유',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '네이티브 서브에이전트', state: 'muted', detail: '메시지만 주고받는 얕은 위임 — 스레드 고정·기억 주입이 안 옮겨짐' },
          { label: '대신 선택한 방식', state: 'success', detail: '얇은 커스텀 tool로 도메인을 감싸 위임' },
        ]}
      />
    ),
  },
  'chat-mgmt-not-migrated': {
    title: '매니지먼트는 왜 새 채팅 구조로 안 옮겼나',
    note: '',
    render: () => (
      <StatusRow items={[{ label: '코드 대조로 확인', state: 'warning', detail: '전환하면 기존 장기기억 기능을 잃는다는 걸 발견 — 기존 구조 유지 + 배선만 연결' }]} />
    ),
  },
  'chat-tool-count': {
    title: '채팅 tool 구성',
    note: '',
    render: () => (
      <InfoCards
        items={[
          { label: '정의된 tool', value: '33개', tone: 'primary' },
          { label: '라우팅 방식', value: '시스템 프롬프트 1개', detail: '별도 분류 LLM 없이 규칙 인코딩', tone: 'primary' },
        ]}
      />
    ),
  },
  'chat-shortterm-bug': {
    title: '대화 맥락(단기 기억) 버그',
    note: '',
    render: () => (
      <Timeline
        events={[
          { date: '이전', label: '서브에이전트가 무상태', detail: '"표본 몇 명?" → "50명" 같은 후속 답변 불가', tone: 'danger' },
          { date: '이후', label: '최근 대화 이력 전달 + 컨텍스트 보존', tone: 'success' },
        ]}
      />
    ),
  },
  'chat-known-bug': {
    title: '현재 알려진 미해결 버그',
    note: '정직한 한계 — 문서에 남아 있는 미수정 항목.',
    render: () => (
      <StatusRow items={[{ label: '일반 지식 경로에서 현재 턴 질문 중복', state: 'danger', detail: '문서에 기록된 미해결 이슈' }]} />
    ),
  },
  'chat-ltm-upgrade': {
    title: '장기기억 검색 방식 개선',
    note: '',
    render: () => (
      <Timeline
        events={[
          { date: '이전', label: '최신 3개만(recency)', tone: 'muted' },
          { date: '이후', label: '임베딩 기반 top-k 검색', detail: '실 DB로 정확도 검증까지 완료', tone: 'success' },
        ]}
      />
    ),
  },
  'chat-session-no-trash': {
    title: '채팅 세션은 휴지통 복원이 안 됨',
    note: '정직한 한계 — 프로젝트·시뮬레이션과 다른 점.',
    render: () => (
      <StatusRow
        items={[
          { label: '프로젝트 · 시뮬레이션', state: 'success', detail: '소프트 삭제(휴지통) 있음' },
          { label: '채팅 세션', state: 'muted', detail: '즉시 영구 삭제 — 복원 경로 없음' },
        ]}
      />
    ),
  },
  'chat-gen-result-bug': {
    title: '생성 결과가 화면에서 사라지던 버그',
    note: '',
    render: () => (
      <Timeline
        events={[
          { date: '버그', label: '결과를 붙인 직후 이전 상태로 덮어써짐', tone: 'danger' },
          { date: '수정', label: '항상 최신 상태를 참조하도록 수정', tone: 'success' },
        ]}
      />
    ),
  },
  'chat-hallucinate-product': {
    title: '개선 시안 생성 시 엉뚱한 상품이 나오던 버그',
    note: '',
    render: () => (
      <Timeline
        events={[
          { date: '버그', label: '직전 시뮬 맥락 없이 요청 전달', detail: 'LLM이 다른 상품을 지어냄', tone: 'danger' },
          { date: '수정', label: '직전 시뮬 광고 정보를 그대로 전달', detail: '실측 재검증 완료', tone: 'success' },
        ]}
      />
    ),
  },
  'chat-order-bug': {
    title: '채팅 메시지 순서가 뒤바뀌던 버그',
    note: '',
    render: () => (
      <Timeline
        events={[
          { date: '버그', label: '한 턴의 질문·답변이 같은 시각으로 저장', detail: '정렬이 흔들림', tone: 'danger' },
          { date: '수정', label: '명시적 타임스탬프로 순서 고정', tone: 'success' },
        ]}
      />
    ),
  },
  'chat-form-policy': {
    title: '정보 부족 시 채팅의 응답 정책',
    note: '',
    render: () => (
      <StatusRow items={[{ label: '값이 하나도 없어도', state: 'success', detail: '먼저 되묻지 않고 생성을 시도, 부족한 값만큼 입력 폼을 띄움' }]} />
    ),
  },
  'chat-qa-passrate': {
    title: 'QA 실측 통과율(영역별)',
    note: '권한 영역은 이후 보완돼 현재는 해소된 상태.',
    render: () => (
      <Matrix
        columns={['통과율']}
        rows={[
          { label: '시뮬레이터', cells: [{ text: '95%', tone: 'success' }] },
          { label: '채팅 기본', cells: [{ text: '85%', tone: 'success' }] },
          { label: '채팅 내 시뮬/제너', cells: [{ text: '70%', tone: 'warning' }] },
          { label: '권한(당시 기준)', cells: [{ text: '50% → 이후 보완', tone: 'muted' }] },
        ]}
      />
    ),
  },

  // ── 한계·로드맵 ──────────────────────────────────────────────
  'limits-summary': {
    title: '현재의 한계 — 요약',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '예측은 실측을 100% 재현하지 않음', state: 'muted', detail: '대체하는 것은 감과 내부 회의' },
          { label: '도달 분포는 generic SNS 기준', state: 'muted', detail: '플랫폼 특정 정밀도 한계' },
          { label: '한국 소비심리(체면·동조·눈치) 미반영', state: 'muted', detail: '데이터 확보 전까지 반영하지 않는 원칙' },
        ]}
      />
    ),
  },
  'roadmap-future': {
    title: '개선 로드맵 — 향후 방향',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '실측 5건 축적 시 calibration 자동 해금', state: 'primary', detail: '쓸수록 고객 브랜드에 맞게 정교해지는 구조' },
          { label: 'Meta 중심 → Google 등 다채널 확장', state: 'primary' },
          { label: '플랫폼·브랜드 특정 침투율 데이터로 모집단 정밀화', state: 'primary', detail: '학술 척도 확보 시 소비심리 요인 반영' },
        ]}
      />
    ),
  },
};

type Q = { id: string; q: string; exhibitKey: keyof typeof EXHIBITS };
type Domain = { id: string; label: string; icon: React.ReactNode; accent: Tone; questions: Q[] };

export const DOMAINS: Domain[] = [
  {
    id: 'business',
    label: '사업·문제정의',
    accent: 'danger',
    icon: <AlertTriangle size={16} strokeWidth={1.8} />,
    questions: [
      { id: 'b1', q: '캠페인 하나 만드는 데 2~3주가 걸린다는 근거는 뭔가요?', exhibitKey: 'stat-production-time' },
      { id: 'b2', q: '광고가 실패하면 정말 한 푼도 못 돌려받나요?', exhibitKey: 'stat-refund' },
      { id: 'b3', q: '테스트 삼아 돌려보는 데도 50~150만 원이나 든다는 게 정확한 수치인가요?', exhibitKey: 'stat-test-budget' },
      { id: 'b4', q: '광고 86%를 무시한다는 통계는 어디서 가져왔나요?', exhibitKey: 'stat-banner-blindness' },
      { id: 'b5', q: '지금까지는 왜 사전 검증 없이 광고비부터 썼던 건가요?', exhibitKey: 'execution-flow-problem' },
      { id: 'b6', q: '기존 광고 대행사나 매체 자체 도구랑 뭐가 다른가요?', exhibitKey: 'service-overview' },
      { id: 'b7', q: '무료 플랜을 주면 수익은 어떻게 내나요?', exhibitKey: 'business-model' },
      { id: 'b8', q: '개발 기간이 8주밖에 안 됐는데 정말 다 동작하나요?', exhibitKey: 'wbs-timeline' },
      { id: 'b9', q: '이 프로젝트를 만들 때 가장 중요하게 지킨 원칙이 있나요?', exhibitKey: 'biz-goals' },
    ],
  },
  {
    id: 'infra',
    label: '기술·인프라',
    accent: 'neutral',
    icon: <Server size={16} strokeWidth={1.8} />,
    questions: [
      { id: 't1', q: '서버가 EC2 한 대뿐인데 트래픽이 몰리면 어떻게 되나요?', exhibitKey: 'infra-topology' },
      { id: 't2', q: '왜 마이크로서비스가 아니라 DDD 모놀리식으로 짰나요?', exhibitKey: 'infra-topology' },
      { id: 't3', q: 'LLM을 OpenAI·Gemini·Anthropic 세 개나 쓰는 이유가 뭔가요?', exhibitKey: 'multi-llm' },
      { id: 't4', q: 'RAG는 정확히 어떻게 동작하나요?', exhibitKey: 'rag-architecture' },
      { id: 't5', q: '배포와 보안은 어떻게 관리하나요?', exhibitKey: 'cicd-pipeline' },
      { id: 't6', q: '테스트는 어떻게 하고, 실패하면 배포가 막히나요?', exhibitKey: 'security-layers' },
      { id: 't7', q: '컨테이너 상태는 어떻게 모니터링하나요?', exhibitKey: 'infra-portainer' },
      { id: 't8', q: '테스트가 실패하면 배포가 진행되나요?', exhibitKey: 'infra-needs-chain' },
      { id: 't9', q: 'E2E 테스트는 왜 매 PR마다 안 도나요?', exhibitKey: 'infra-e2e-manual' },
      { id: 't10', q: 'GitHub Secrets는 몇 개나 쓰나요?', exhibitKey: 'infra-secrets' },
      { id: 't11', q: '문서와 코드가 어긋나는 걸 어떻게 막나요?', exhibitKey: 'infra-docs-check' },
      { id: 't12', q: 'DB 마이그레이션 이력이 꼬였던 적 있나요?', exhibitKey: 'infra-migration-cleanup' },
      { id: 't13', q: '관리자가 조직·회원을 삭제하면 데이터가 완전히 사라지나요?', exhibitKey: 'infra-admin-delete' },
    ],
  },
  {
    id: 'generator',
    label: '제너레이터',
    accent: 'warning',
    icon: <Sparkles size={16} strokeWidth={1.8} />,
    questions: [
      { id: 'g1', q: 'AI가 만든 광고 이미지에 한글이 깨진다는 문제가 있었다던데, 어떻게 해결했나요?', exhibitKey: 'gen-korean-typo' },
      { id: 'g2', q: 'LangSmith로 비용을 추적한다면서 85%를 못 본다는 게 무슨 말인가요?', exhibitKey: 'gen-langsmith-gap' },
      { id: 'g3', q: '시안 3종은 어떤 흐름으로 만들어지나요?', exhibitKey: 'gen-flow' },
      { id: 'g4', q: '시안 3종이 서로 안 겹치게(다양성) 어떻게 보장하나요?', exhibitKey: 'gen-diversity' },
      { id: 'g5', q: 'Gemini로 이미지를 만들 때 문구도 Gemini가 쓰나요?', exhibitKey: 'gen-gemini-copy' },
      { id: 'g6', q: '이미지 생성 API가 실패하거나 느려지면 어떻게 되나요?', exhibitKey: 'gen-retry' },
      { id: 'g7', q: '시안 순위는 클릭률 예측을 기반으로 매기나요?', exhibitKey: 'gen-ranking-basis' },
      { id: 'g8', q: '품질검증 항목을 전부 실제로 검사하나요?', exhibitKey: 'gen-qa-honest' },
      { id: 'g9', q: "'1위', '100% 효과' 같은 과대광고 표현은 걸러지나요?", exhibitKey: 'gen-banned-words' },
      { id: 'g10', q: '개선 모드는 기존 광고 이미지를 직접 고치는 건가요?', exhibitKey: 'gen-improve-redesign' },
      { id: 'g11', q: '상품 이미지(누끼)를 못 찾으면 어떻게 하나요?', exhibitKey: 'gen-cutout-fallback' },
      { id: 'g12', q: '채팅에서 개선모드로 들어가면 아까 만든 누끼를 재사용하나요?', exhibitKey: 'gen-chat-cutout-gap' },
      { id: 'g13', q: '자동 개선 루프는 몇 번까지 반복되나요?', exhibitKey: 'gen-loop-limit' },
      { id: 'g14', q: '어떤 지표가 부족하면 뭘 고칠지는 어떻게 정하나요?', exhibitKey: 'gen-loop-axis' },
      { id: 'g15', q: '한글 폰트는 어떻게 처리하나요? 라이선스 문제는 없나요?', exhibitKey: 'gen-font' },
      { id: 'g16', q: '브랜드 컬러가 밝으면 버튼 글씨가 안 보이는 문제 없었나요?', exhibitKey: 'gen-contrast-bug' },
      { id: 'g17', q: '인페인팅을 항상 켜두면 비용이 2배 아닌가요?', exhibitKey: 'gen-inpaint-cost' },
      { id: 'g18', q: '서버가 재시작되면 생성 중이던 작업은 어떻게 되나요?', exhibitKey: 'gen-restart' },
    ],
  },
  {
    id: 'simulation',
    label: '시뮬레이션',
    accent: 'point',
    icon: <Users size={16} strokeWidth={1.8} />,
    questions: [
      { id: 's1', q: '최신 논문 기법(SSR)을 도입했다가 하루 만에 롤백했다던데, 정확히 뭐가 문제였나요?', exhibitKey: 'sim-ssr-flat' },
      { id: 's2', q: '그 SSR 판정이 구체적으로 어떻게 틀렸는데요?', exhibitKey: 'sim-ssr-inversion' },
      { id: 's3', q: '그럼 지금은 어떤 방식으로 점수를 매기나요?', exhibitKey: 'sim-ssr-rollback' },
      { id: 's4', q: 'SSR을 며칠 새 여러 번 켰다 껐다 했다던데, 정확히 몇 번이나 바뀌었나요?', exhibitKey: 'sim-ssr-flipflop' },
      { id: 's5', q: '페르소나 토론에서 나온 피드백이 실제로 마케팅에 쓸모가 있나요?', exhibitKey: 'sim-debate-before-after' },
      { id: 's6', q: '예측이 실제 결과랑 얼마나 맞나요?', exhibitKey: 'sim-limits' },
      { id: 's7', q: '한국인 특유의 눈치·체면 문화도 반영되나요?', exhibitKey: 'sim-limits' },
      { id: 's8', q: '초기에 설계했던 2단계(즉각반응→숙고) 구조는 진짜 아예 안 쓰이나요?', exhibitKey: 'sim-dead-code' },
      { id: 's9', q: 'SSR 앵커는 몇 차원, 몇 단계로 설계했나요?', exhibitKey: 'sim-anchor-design' },
      { id: 's10', q: '신뢰구간은 몇 번 반복해서 계산하고, 매번 값이 바뀌나요?', exhibitKey: 'sim-bootstrap-detail' },
      { id: 's11', q: '페르소나 샘플링에 나이 제한 같은 임계값이 있나요?', exhibitKey: 'sim-age-thresholds' },
      { id: 's12', q: '행안부 데이터에 지역 정보가 없으면 어떻게 하나요?', exhibitKey: 'sim-region-fallback' },
      { id: 's13', q: '전 국민을 다 시뮬레이션하지 않고 표본만 쓰는 이유는요?', exhibitKey: 'sim-sample-principle' },
      { id: 's14', q: '표본 5명만 요청했는데 43명이 실행되는 비용 버그가 있었다던데요?', exhibitKey: 'sim-panel-bug' },
      { id: 's15', q: '토론에서 의견이 갈리면 어떻게 결론을 내나요?', exhibitKey: 'sim-debate-tiebreak' },
      { id: 's16', q: '실측 벤치마크(KOBACO)가 모든 광고 카테고리에 다 있나요?', exhibitKey: 'sim-kobaco-gap' },
      { id: 's17', q: "'관심 있는 사람만' 따로 보는 지표도 있나요?", exhibitKey: 'sim-interest-conditional' },
      { id: 's18', q: '리포트 종합점수에 브랜드 인지도는 왜 안 들어가나요?', exhibitKey: 'sim-brand-awareness-excluded' },
      { id: 's19', q: '세그먼트 히트맵이 안 나올 때가 있던데요?', exhibitKey: 'sim-segment-heatmap-gate' },
      { id: 's20', q: '실제 사람과 비슷한지 어떻게 검증했나요? 외부 설문과 비교했나요?', exhibitKey: 'sim-validation-method' },
      { id: 's21', q: '리포트가 느려서 타임아웃 났던 적 있나요?', exhibitKey: 'sim-report-timeout' },
      { id: 's22', q: '토론 결론이 중간에 잘리는 버그가 있었나요?', exhibitKey: 'sim-json-truncation' },
      { id: 's23', q: '토론 참여 인원은 고정인가요?', exhibitKey: 'sim-debate-size' },
      { id: 's24', q: '광고가 닿지도 않을 사람까지 표본에 포함되는 문제가 있었다는데 어떻게 고쳤나요?', exhibitKey: 'sim-reachability' },
    ],
  },
  {
    id: 'management',
    label: '매니지먼트',
    accent: 'success',
    icon: <BarChart3 size={16} strokeWidth={1.8} />,
    questions: [
      { id: 'm1', q: '예산을 AI가 알아서 옮긴다는데, 잘못 옮기면 어떡하나요?', exhibitKey: 'mgmt-rebalance-flow' },
      { id: 'm2', q: '실제로 리밸런싱이 어떻게 동작하는지 예시로 보여줄 수 있나요?', exhibitKey: 'mgmt-rebalance-example' },
      { id: 'm3', q: 'Meta 광고 API 등급 제약이라는 게 무슨 뜻인가요?', exhibitKey: 'mgmt-meta-tier' },
      { id: 'm4', q: 'CVR을 설문 제출률로 대신했다는데, 정확도가 떨어지지 않나요?', exhibitKey: 'mgmt-meta-tier' },
      { id: 'm5', q: '예산 집행은 항상 사람이 승인해야 하나요, 완전 자동화는 없나요?', exhibitKey: 'mgmt-hitl' },
      { id: 'm6', q: '예산 초과 안전장치가 몇 단계로 되어 있나요?', exhibitKey: 'mgmt-budget-tiers' },
      { id: 'm7', q: '자동승인(AUTO)이 통과되는 범위는 정확히 어디까지인가요?', exhibitKey: 'mgmt-auto-approver' },
      { id: 'm8', q: '이상 감지 오탐(false alarm)은 어떻게 줄이나요?', exhibitKey: 'mgmt-anomaly-guardrail' },
      { id: 'm9', q: '이상 감지 알림을 채팅으로 줄지 별도 패널로 줄지 어떻게 정했나요?', exhibitKey: 'mgmt-notify-channel' },
      { id: 'm10', q: '리밸런싱 집행 코드에서 실제로 발견된 버그가 있나요?', exhibitKey: 'mgmt-rebalance-timeout-bug' },
      { id: 'm11', q: '데모용 mock 데이터에도 버그가 있었나요?', exhibitKey: 'mgmt-mock-drift-bug' },
      { id: 'm12', q: '예산 재배분 워커가 실제로 돈을 옮기나요?', exhibitKey: 'mgmt-worker-proposal-only' },
      { id: 'm13', q: '워커 하나가 실패하면 전체 스케줄러가 멈추나요?', exhibitKey: 'mgmt-worker-isolation' },
      { id: 'm14', q: '성과 미달 진단의 정확도 목표는 얼마인가요?', exhibitKey: 'mgmt-eval-accuracy' },
      { id: 'm15', q: '채팅으로 매니지먼트 기능을 실제로 써보니 문제가 없었나요?', exhibitKey: 'mgmt-chat-realtest' },
      { id: 'm16', q: '생성(제너레이터)에서 매니지먼트로 넘어가는 경로가 두 갈래라던데, 왜 하나로 안 합쳤나요?', exhibitKey: 'mgmt-dual-path-honest' },
      { id: 'm17', q: '시뮬레이션 결과를 나중에 다시 조회하는 기능이 없었다는 게 무슨 뜻인가요?', exhibitKey: 'mgmt-result-read-gap' },
      { id: 'm18', q: 'USE_MOCK 설정에서 실수하기 쉬운 함정이 있나요?', exhibitKey: 'mgmt-mock-trap' },
    ],
  },
  {
    id: 'chat',
    label: '채팅',
    accent: 'primary',
    icon: <MessageSquare size={16} strokeWidth={1.8} />,
    questions: [
      { id: 'c1', q: '채팅이 엉뚱한 답을 하지는 않나요? 할루시네이션 대책은요?', exhibitKey: 'chat-hallucination' },
      { id: 'c2', q: 'RAG 검색이 처음엔 왜 부정확했나요?', exhibitKey: 'chat-rag-problem' },
      { id: 'c3', q: '그래서 어떻게 개선했고, 얼마나 좋아졌나요?', exhibitKey: 'chat-rag-improvement' },
      { id: 'c4', q: '이 성능 지표는 어떻게 측정한 건가요, 믿을 수 있나요?', exhibitKey: 'chat-rag-improvement' },
      { id: 'c5', q: 'Hit Rate·MRR과 LLM-as-Judge는 각각 뭘 해결한 건가요?', exhibitKey: 'chat-rag-metric-split' },
      { id: 'c6', q: '채팅 오케스트레이터를 처음부터 지금 구조로 만들었나요?', exhibitKey: 'chat-orchestrator-history' },
      { id: 'c7', q: 'deepagents의 서브에이전트 기능은 왜 안 썼나요?', exhibitKey: 'chat-subagent-reason' },
      { id: 'c8', q: '매니지먼트 도메인은 왜 새 채팅 구조로 전환하지 않았나요?', exhibitKey: 'chat-mgmt-not-migrated' },
      { id: 'c9', q: '채팅 tool은 몇 개나 있고, LLM이 어떤 tool을 부를지는 어떻게 판단하나요?', exhibitKey: 'chat-tool-count' },
      { id: 'c10', q: '대화 맥락(단기 기억)에 실제 버그가 있었나요?', exhibitKey: 'chat-shortterm-bug' },
      { id: 'c11', q: '지금 알려진 미해결 버그가 있나요?', exhibitKey: 'chat-known-bug' },
      { id: 'c12', q: '장기기억 검색은 최신순인가요, 관련도순인가요?', exhibitKey: 'chat-ltm-upgrade' },
      { id: 'c13', q: '채팅 세션을 삭제하면 휴지통에서 복원할 수 있나요?', exhibitKey: 'chat-session-no-trash' },
      { id: 'c14', q: '생성 결과가 화면에서 갑자기 사라지는 버그가 있었나요?', exhibitKey: 'chat-gen-result-bug' },
      { id: 'c15', q: '시뮬 결과로 개선 시안을 만들 때 엉뚱한 상품이 나온 적 있나요?', exhibitKey: 'chat-hallucinate-product' },
      { id: 'c16', q: '채팅 메시지 순서가 뒤바뀌는 버그가 있었나요?', exhibitKey: 'chat-order-bug' },
      { id: 'c17', q: '정보가 부족하면 채팅이 되묻나요, 바로 진행하나요?', exhibitKey: 'chat-form-policy' },
      { id: 'c18', q: 'QA에서 실제 통과율이 영역별로 몇 %였나요?', exhibitKey: 'chat-qa-passrate' },
    ],
  },
  {
    id: 'limits',
    label: '한계·로드맵',
    accent: 'muted',
    icon: <Compass size={16} strokeWidth={1.8} />,
    questions: [
      { id: 'l1', q: '가장 정직하게 인정하는 기술적 한계가 뭔가요?', exhibitKey: 'limits-summary' },
      { id: 'l2', q: '앞으로 어떻게 개선할 계획인가요?', exhibitKey: 'roadmap-future' },
      { id: 'l3', q: '실측 기반으로 예측을 보정하는 기능은 언제쯤 되나요?', exhibitKey: 'roadmap-future' },
    ],
  },
];

export type { Domain };
