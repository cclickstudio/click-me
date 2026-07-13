// 발표 Q&A 부록 — 실제 최종발표 PPT·발표 스크립트·코드베이스 심층 조사(도메인별)를 근거로, 심사·청중이
// 실제로 물어볼 법한 질문과 그 답변에 쓸 시각 자료(exhibit)를 매핑한다. 지어낸 수치는 없다. PPT·코드가
// 스스로 인정한 한계·미해결 항목은 "미해결"로 그대로 노출한다. 실 보안 취약점(이미 수정 완료)의 공격
// 메커니즘 상세는 공개 페이지 특성상 의도적으로 제외했다(예: OAuth CSRF, 구 채팅/시뮬 무인증 접근).

import {
  AlertTriangle,
  Server,
  Users,
  BarChart3,
  MessageSquare,
  Compass,
  Lock,
  ExternalLink,
  ArrowDown,
  ArrowUp,
} from 'lucide-react';
import { Pipeline, LayerStack, Matrix, Timeline, InfoCards, StatusRow, BarDistribution, StepBox, ShotGrid, type Tone } from './primitives';
// 제너레이터 도메인은 별도 모듈로 분리해 관리한다(질문 목록 + 시각 자료).
import { GENERATOR_DOMAIN, GENERATOR_EXHIBITS } from './exhibits-generator';

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

  // ── 제너레이터 (exhibits-generator.tsx에서 관리) ──────────────
  ...GENERATOR_EXHIBITS,

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
  'sim-ssr-fix': {
    title: 'SSR 재설계 — 봉인 해금 조건 이행(검증 통과)',
    note: '앵커를 반응 문체로 재작성 + softmax 정규화 + 임베딩 모델 상향. 강도 5단계 대조 세트 실측 — 기본값 전환은 팀 합의 후(현재 opt-in).',
    render: () => (
      <Matrix
        columns={['구 SSR', '재설계 SSR']}
        rows={[
          { label: '강한 부정(기대 1~2)', cells: [{ text: '3.26', tone: 'danger' }, { text: '1.23', tone: 'success' }] },
          { label: '중립(기대 3)', cells: [{ text: '3.19', tone: 'danger' }, { text: '2.99', tone: 'success' }] },
          { label: '강한 긍정(기대 4~5)', cells: [{ text: '3.47', tone: 'danger' }, { text: '4.12', tone: 'success' }] },
        ]}
      />
    ),
  },
  'sim-fixed-panel': {
    title: '고정 패널 — A/B 비교의 통계적 타당성',
    note: '리서치 업계의 고정 패널 개념과 동일 — grounding 원천인 KISDI 미디어패널 자체가 동일표본 추적조사.',
    render: () => (
      <StatusRow
        items={[
          { label: 'A/B를 서로 다른 랜덤 패널로 비교하면', state: 'danger', detail: '패널 구성 차이가 광고 차이와 교락 — 시안 비교가 통계적으로 무효' },
          { label: '고정 패널(1,000명 · 시드 고정 · 버전 기록)', state: 'success', detail: '동일 패널에 노출하는 짝지은 비교로 전환 + 재현성 확보' },
          { label: '캐시는 프로필만', state: 'neutral', detail: '반응은 광고마다 새로 생성 — 응답 재활용 아님(보고서 방법론에 명시)' },
        ]}
      />
    ),
  },
  'sim-oversampling': {
    title: '층화 과대표집 — 얇은 연령층 표본 보강',
    note: 'sample_size 300 이상이면 자동 stratified 전환. 대가(가중 편차로 유효표본 감소)는 리포트에 숫자로 표기.',
    render: () => (
      <InfoCards
        items={[
          { label: '60대+ 표본(300명 비례 추출)', value: '18명', detail: '셀이 얇아 세그먼트 지표가 노이즈', tone: 'danger' },
          { label: '층화 과대표집 후', value: '50명', detail: '서로 다른 실제 페르소나를 새로 추출 — 총 300콜 불변(재배분)', tone: 'success' },
          { label: '가중 복원', value: 'w=0.510', detail: '집계 비중은 18명일 때와 동일, 추정만 50명 기반으로 안정', tone: 'point' },
        ]}
      />
    ),
  },
  'sim-penetration-bug': {
    title: '메타 침투율이 1.0을 넘던 사건',
    note: '나눗셈(침투율) 계산 자체를 제거해 1.0 초과가 구조적으로 재발 불가.',
    render: () => (
      <Timeline
        events={[
          { date: '문제', label: '침투율(도달÷인구)이 1.0 초과', detail: '복수 계정으로 메타 추산 도달이 census 인구를 초과', tone: 'danger' },
          { date: '추가 발견', label: '대체재 KISDI 지표도 오염', detail: '소셜피드 비중이 사실상 유튜브 시청만 집계', tone: 'muted' },
          { date: '해결', label: '메타 광고 관리자 실측 도달 분포를 직접 사용', detail: '인구비중 곱 단계 제거(연령 marginal)', tone: 'success' },
        ]}
      />
    ),
  },
  'sim-tv-fallback': {
    title: '"메타 광고를 TV에서 봤어요" — 모순 반응 버그',
    note: '숫자는 안 깨지는데 서사가 깨지는 LLM 시뮬레이션 특유의 버그 — 결과물을 직접 읽어야 잡힌다.',
    render: () => (
      <Timeline
        events={[
          { date: '버그', label: '고령층 페르소나의 노출맥락이 TV로 기록', detail: '소셜 후보가 비면 TV·신문으로 조용히 폴백', tone: 'danger' },
          { date: '수정', label: '노출맥락을 소셜피드로만 한정', detail: '후보가 없어도 비소셜 폴백 금지 — 모순을 만들 바엔 폴백하지 않음', tone: 'success' },
        ]}
      />
    ),
  },
  'sim-ai-bias': {
    title: '페르소나 다양성은 LLM이 아니라 데이터가 강제',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '속성은 실데이터 통계 샘플링', state: 'success', detail: '행안부 인구 · KISDI 미디어 · OCEAN 성격 실분포에서 추출' },
          { label: 'LLM은 마지막에 인물 서사만 입힘', state: 'neutral', detail: 'LLM이 인구 구성을 정하지 않음 — 동질화 방지 설계' },
        ]}
      />
    ),
  },
  'sim-no-ctr': {
    title: '"예측 CTR ○%"를 말하지 않는 이유',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '실측 스케일(CTR %) 환산 금지', state: 'danger', detail: '실측 근거 없이 단언하지 않는다는 의도적 원칙' },
          { label: '클릭 의향률 + 신뢰구간으로만 표기', state: 'success', detail: '연결 캠페인 실측 5건 누적 시 calibration 해금' },
        ]}
      />
    ),
  },
  'sim-sycophancy': {
    title: '듣기 좋은 결과만 내놓지 않는 장치',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '거부율이 4대 KPI에 별도 존재', state: 'success', detail: '거부 비율 + 사유 분해를 그대로 노출' },
          { label: '분포 전체 표시 — 평균 단언 금지', state: 'neutral', detail: '부정 반응을 평균 뒤에 숨기지 않음' },
        ]}
      />
    ),
  },
  'sim-target-filter': {
    title: '특정 고객층만 골라 테스트',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '타깃 지정(target_filter) 지원', state: 'success', detail: '연령·성별 등 특정 층만 골라 시뮬레이션' },
          { label: '타깃 내부도 실분포 유지', state: 'neutral', detail: '필터 안에서 재정규화 후 비례 추출 — 내부 구성이 왜곡되지 않음' },
        ]}
      />
    ),
  },
  'sim-privacy': {
    title: '페르소나와 개인정보',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '실존 개인 데이터 미포함', state: 'success', detail: '통계 분포 기반 합성 인물 — 개인 단위 원천 데이터 없음' },
          { label: '연령·성별·지역 등 집계 분포에서 샘플링', state: 'neutral', detail: '행안부·KISDI 공표 통계 수준의 입력만 사용' },
        ]}
      />
    ),
  },
  'sim-responsibility': {
    title: '예측이 틀렸을 때의 책임 구조',
    note: '포지셔닝 — 실측 대체가 아니라 "감·내부 회의보다 나은 의사결정 근거".',
    render: () => (
      <StatusRow
        items={[
          { label: '시뮬레이션은 근거 제공까지', state: 'neutral', detail: '신뢰구간·표본 부족 플래그로 불확실성을 함께 표기' },
          { label: '돈이 움직이는 결정은 사람이 승인(HITL)', state: 'success', detail: '집행 판단의 주체는 항상 광고주 — 예측을 단정으로 팔지 않음' },
        ]}
      />
    ),
  },
  'sim-call-count': {
    title: '표본 1,000명 = LLM 1,000콜?',
    note: '반응 콜만 표본 수에 비례 — 나머지는 캐시·공유로 상수. 그리고 표본 크기 300명 이상이면 배분 방식이 자동으로 층화 과대표집(stratified)으로 전환된다(사용자 선택이 아니라 sample_size로 결정). 과대표집은 얇은 연령층(예 60대+)에 표본 예산을 더 배정해 실제 페르소나를 더 많이 새로 뽑고 붐비는 층(20대)에서 그만큼 덜 뽑는 재배분이라, 복제·부풀리기가 아니고 총 콜 수도 그대로다. 뽑은 만큼 가중치(w=인구비중/표본비중)로 되돌려 대표성은 동일하게 유지한다. 1,000명이면 얇은 층이 이미 충분히 두꺼워 floor가 거의 안 걸려 과대표집 결과가 단순 비례 추출에 수렴한다. 근거: docs/simulation/Persona/표본 가중 설명.md · 표본 노이즈 설명.md.',
    render: () => (
      <StatusRow
        items={[
          { label: '페르소나 프로필 생성', state: 'success', detail: '고정 패널 캐시 — 시뮬레이션 시점 추가 콜 0회' },
          { label: '광고 해석(VLM)·루브릭', state: 'success', detail: '광고당 1회만 — 전 페르소나가 공유' },
          { label: '반응 생성', state: 'warning', detail: '표본 수만큼 1인 1콜 — 단, 300명 표본+가중으로 1,000명 규모를 대표 가능(콜 수 ≠ 대표 인원)' },
          { label: '300명↑ → 자동 층화 과대표집', state: 'point', detail: '얇은 층을 더 뽑고 붐비는 층을 덜 뽑는 재배분(복제 아님) → 총 콜 불변, 가중으로 대표성 복원. 1,000명이면 과대표집이 단순 비례에 수렴' },
        ]}
      />
    ),
  },
  'sim-cost-100': {
    title: '100명 시뮬레이션 1회 ≈ $2.5 (약 3,500원)',
    note: '실측(2026-07-13) — 실제 반응 프롬프트 1콜의 토큰 usage(입력 847·출력 2,343, thinking 포함) × 100 + Gemini 공식 단가(3.5 Flash $1.50/$9.00, 2.5 Flash $0.30/$2.50 per 1M, ai.google.dev/gemini-api/docs/pricing). 환율 1,400원 가정. 배치 API 사용 시 단가 50% 추가 할인.',
    render: () => (
      <InfoCards
        items={[
          { label: '반응 100콜 — Gemini 3.5 Flash', value: '$2.24', detail: '비용의 90%. 콜당 입력 847·출력 2,343토큰 실측', tone: 'warning' },
          { label: '해석·루브릭 1콜 + QA 버퍼 10%', value: '$0.23', detail: '표본 수와 무관한 상수 + 재시도 여유', tone: 'neutral' },
          { label: '합계 (프로필은 패널 캐시로 0콜)', value: '≈ 3,500원', detail: '기존 사전 검증(FGI 600만~1,500만 원)의 수천분의 1', tone: 'success' },
        ]}
      />
    ),
  },
  'sim-concurrency': {
    title: '동시 고객 100개사 — 정직한 현재 규모',
    note: '정직한 한계 — 확장 시 잡 큐 도입 재검토가 Open Issue로 문서화되어 있음.',
    render: () => (
      <StatusRow
        items={[
          { label: '현재 단일 EC2 + 인프로세스 async', state: 'muted', detail: '8주 내 완주를 우선한 선택 — 100개사 동시 실행은 현 단계 목표가 아님' },
          { label: '확장 경로는 설계에 반영됨', state: 'neutral', detail: '반응 생성이 병렬 단위라 잡 큐(SQS 등)·워커 분리로 수평 확장 가능한 구조' },
        ]}
      />
    ),
  },
  'sim-llm-resilience': {
    title: 'LLM 가격 인상·장애 대비',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '폴백 체인 기본 ON', state: 'success', detail: 'Gemini 503/실패 시 GPT로 자동 전환 — 단일 벤더 장애에 무중단' },
          { label: '모델 교체는 설정 한 줄', state: 'success', detail: '반응·해석 모델을 env로 교체 — 가격 변동 시 벤더 이동 용이' },
          { label: '3사 멀티 LLM 운용 경험', state: 'neutral', detail: 'OpenAI·Google·Anthropic을 역할별로 이미 병행 사용 중' },
        ]}
      />
    ),
  },
  'sim-real-campaign': {
    title: '실제 배포 광고와의 비교 — 현재 위치',
    note: '"없다"가 아니라 "쌓는 구조가 이미 있다" — 실측 5건 누적 시 calibration 자동 해금.',
    render: () => (
      <StatusRow
        items={[
          { label: 'KOBACO 실측 벤치마크 참고 제시', state: 'neutral', detail: '2019 소비자행태조사 원자료 반영 — 단 8대 업종 한정·문항 불일치 한계 명시' },
          { label: '사비로 실제 Meta 캠페인 집행', state: 'success', detail: 'CTR·CPC·CPM 등 실측 데이터 확보(매니지먼트 실연동)' },
          { label: '실측 5건 누적 시 calibration 해금', state: 'primary', detail: '예측↔실측 보정이 자동으로 켜지는 설계' },
        ]}
      />
    ),
  },
  'sim-improvement-case': {
    title: '"개선했더니 성과가 올랐다"는 사례 — 정직한 답',
    note: '정직한 한계 — 실 집행 인과 사례는 아직 없다. 있는 것과 없는 것을 구분해 답할 것.',
    render: () => (
      <StatusRow
        items={[
          { label: '내부 지표 개선은 확인됨', state: 'success', detail: '시뮬 진단 → 개선 시안 생성 루프에서 4대 KPI 축 개선을 반복 검증' },
          { label: '실제 집행 성과 인과 사례', state: 'muted', detail: '아직 미확보 — 실측 calibration 해금 이후 검증 가능' },
        ]}
      />
    ),
  },
  'sim-confidentiality': {
    title: '업로드한 광고 시안의 기밀 유지',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: 'LLM API 입력은 모델 학습에 사용되지 않음', state: 'success', detail: 'OpenAI·Google API 데이터 정책 — 소비자용 챗봇과 다른 계약' },
          { label: '기밀 데이터 평문 로그 금지', state: 'success', detail: '예산·크리에이티브는 로그에 남기지 않는 내부 정책' },
          { label: '외부 플랫폼 API 키 암호화 저장', state: 'neutral', detail: 'AES-256 또는 AWS Secrets Manager' },
        ]}
      />
    ),
  },
  'sim-persona-pipeline': {
    title: '페르소나 생성 방식 — 데이터가 만들고 LLM은 서사·반응만',
    note: '핵심 원리 — 다양성은 "실데이터 통계 샘플링"이 강제하고, LLM은 맨 끝 두 단계에서만 등장한다. 단계 ①~③은 LLM을 전혀 안 쓰는 순수 통계 쿼터 샘플링(결정적 seed)이고, 여기서 이미 "서로 다른 1,000명"이 확정된다. LLM에게 "30대 여성 만들어줘"라고 시키면 학습 데이터 평균으로 수렴해 다들 비슷해지기(동질화) 때문에, 속성은 전부 한국 실통계에서 뽑고 LLM은 ④에서 그 속성을 인물 소개로 풀고 ⑤에서 "그 사람 본인처럼" 광고에 반응하는 일만 한다. ④는 패널 빌드 때 1회만 호출해 캐시하고, ⑤만 광고마다 새로 돈다. 최종 KPI(클릭의향률·구매의도 평균·신뢰구간)는 LLM이 아니라 집계 엔진이 반응 JSON을 코드로 가중 평균·부트스트랩한 값이다. 상세: docs/simulation/Persona/페르소나 생성 파이프라인 설명.md · 페르소나 생성 전략.md.',
    render: () => (
      <div className="space-y-5">
        <Pipeline
          steps={[
            { label: '① 인구통계', detail: '나이·성별·지역 — 행안부 쿼터(정수 비례)', tone: 'point' },
            { label: '② 성격 OCEAN', detail: '서울대-카카오 5유형 · 연령×성별 조건화', tone: 'point' },
            { label: '③ 미디어·소득·소비가치', detail: 'KISDI 미디어패널 · 대학내일 실분포', tone: 'point' },
            { label: '④ 인물 서사 (LLM 1회)', detail: '정해진 속성을 소개글로 → 패널 캐시', tone: 'neutral' },
            { label: '⑤ 광고 반응 (LLM · 광고마다)', detail: '"이 사람 본인처럼" → 집계용 JSON', tone: 'warning' },
          ]}
        />
        <div>
          <p className="mb-2 text-sm font-semibold text-ink-tertiary">
            ⑤ 광고 반응 단계에서 LLM에 실제로 넘어가는 프롬프트 — 우측 ← 는 각 줄이 어느 데이터에서 오는지(값 빈 줄은 자동 생략)
          </p>
          <pre className="overflow-x-auto whitespace-pre rounded-xl border border-line bg-surface-1 p-4 font-mono text-xs leading-relaxed text-ink-secondary">
{`당신은 아래 한국 소비자 '본인'입니다. 지금 인스타그램·페이스북(메타) 피드를 넘겨보다가
아래 광고를 마주쳤습니다. 이 사람의 성격·형편·미디어 습관에 충실하게, 광고에 솔직하게
반응하세요. 피드 광고라 관심이 없으면 손가락으로 즉시 넘길 수 있습니다.
교과서적 정답이 아니라 이 사람의 실제 반응을.

[나]
- 27세 M, 경기도                                       ← population 실데이터(행안부)
- 학력 대학교, 월소득 100만원 미만                       ← socioeconomic(KISDI)
- 성격(OCEAN): 개방성 매우 낮음, 성실성 보통, 외향성 보통,  ← B-6 연령 조건화
  친화성 낮음, 신경증 매우 낮음                            + raw z-score를 정성 수준으로 변환
- 주 이용 미디어: PC (하루 약 307분, 보통 이용자)          ← media(KISDI) + 이용강도
- 중시 소비가치: ['성능', '품질', '편의', '저렴한 가격', …]  ← consumption(+작업2 OCEAN 조건화)
- 서사: (4-a에서 생성된 인물 소개)
- 지금 노출 맥락: 저녁·집·스마트폰/휴대폰·SNS              ← media 노출맥락
  [내 성향(한국 특화)] 체면 65%, 동조 …                   ← 작업4 (값 비면 줄 생략 — 지금 안 보임)
[내 세대]
- 브랜드·문화 형성기 2014~2024년, 모르는 브랜드면 '낯섦' 반영,
  내 나이대 어투로 말하기                                 ← Tier1 세대 게이팅

[광고]
- 업종: 음료(제로 탄산수) / 목적: 신제품 인지·구매전환     ← VLM 감지(목적 추가)
- 메시지: 제로 칼로리 신제품, 편의점 단독 출시
- 가격: 정가 30,000원 → 할인가 19,900원 (내 월소득 기준 판단) ← ad_features
- 브랜드 언급: 있음 / 사회적 증거(후기·인기): high
- 브랜드 시대성(전원 공유 사실): … (친숙/낯섦은 내 형성기로 판단)   ← Tier2 brand_era
[광고 비주얼]                                            ← VLM visual_elements
- 핵심 피사체: 제품 캔 클로즈업                            (피사체 추가)
- 첫눈에 띄는 것: 파란 캔과 물방울
- 주요 시각요소: 제품 캔, 모델, 할인 배지, 로고
- 색감·톤: 시원한 블루·화이트
  [브랜드 인지도] OOO는 내 또래 인지도 75% …             ← 작업1 (값 비면 줄 생략 — 지금 안 보임)

[출력 — 아래 JSON만, 설명·코드펜스 없이]
{
  "aisas": {attention, interest, search, action, share},
  "drop_stage", "drop_reason_tag",                       ← 정해진 enum만
  "purchase_intent": 1~5, "trust": 1~5, "rejected": bool,
  "rejection_reason_tag", "emotion_tag",                 ← 정해진 enum만
  "perceived_message", "perceived_target",
  "noticed_first": "내 성격·가치상 가장 먼저 눈에 든 요소",
  "utterance": "한 문장 솔직한 반응"
}
주의: AISAS 깔때기(action=true면 attention·interest도 true), 태그는 enum에서만, noticed_first는 사람마다 다르게.`}
          </pre>
        </div>
      </div>
    ),
  },
  'sim-cost-strategy': {
    title: '시뮬레이션 비용을 줄이는 4겹 구조',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '전수 시뮬 금지 — 표본 + 가중', state: 'success', detail: '여론조사 원리로 콜 수 자체를 상한' },
          { label: '고정 패널 — 프로필 생성비 1회', state: 'success', detail: '런타임엔 반응 콜만 지출' },
          { label: '반응은 경량 Flash 모델', state: 'success', detail: '대량 병렬 콜 구간에 저단가 모델 배정' },
          { label: '대규모 실행은 배치 API · Phase 2 소형/로컬 모델', state: 'neutral', detail: '비용 전략 문서에 단계별로 설계됨' },
        ]}
      />
    ),
  },
  'sim-data-sources': {
    title: '페르소나 grounding 데이터 출처',
    note: '전부 공표 통계·학술 데이터 — 개인 단위 원천 데이터 없이 통계 분포에서 뽑은 합성 인물이다. 페르소나 생성의 핵심 축(인구·OCEAN·미디어·소득·소비가치)은 실값 적재를 마쳤고, 심층 소비심리(체면·동조·눈치)·브랜드 보조인지율은 코드 프레임워크만 두고 값이 비어 있어 graceful fallback(회귀 0)한다. ⚠️ 서울대-카카오 OCEAN은 CC BY-NC-ND(비상업·변경금지) 라이선스라 발표·연구 인용은 자유지만 상업 서비스화 시점에는 법무 검토가 필요하다. 각 소스의 URL·접근 방법·라이선스 전체는 docs/simulation/Persona/데이터 확보처 가이드.md에 정리돼 있다.',
    render: () => (
      <Matrix
        columns={['출처', '규모·라이선스', '확보']}
        rows={[
          { label: '인구(연령×성별×지역)', cells: [{ text: '행안부 주민등록 / KOSIS' }, { text: '전국 5,109만 일치 · 공공데이터' }, { text: '✅ 실값', tone: 'success' }] },
          { label: '성격(OCEAN)', cells: [{ text: '서울대-카카오 Nature(2026)' }, { text: '표본 81만 · CC BY-NC-ND ⚠️', tone: 'warning' }, { text: '✅ 실값', tone: 'success' }] },
          { label: '미디어 행동·소득·학력', cells: [{ text: 'KISDI 한국미디어패널 2024' }, { text: 'raw 연령×성별 교차(4,006가구)' }, { text: '✅ 실값', tone: 'success' }] },
          { label: '소비가치', cells: [{ text: '대학내일20대연구소' }, { text: '공개 조사 응답률' }, { text: '✅ 실값', tone: 'success' }] },
          { label: 'Meta 도달 분포', cells: [{ text: 'Meta 광고 관리자' }, { text: '추산 잠재고객 실측(연령 marginal)' }, { text: '✅ 실값', tone: 'success' }] },
          { label: '심층 심리·브랜드 인지', cells: [{ text: 'MDIS 사회조사 · 갤럽/오픈서베이' }, { text: '체면·동조·보조인지 — 계약·수집 필요' }, { text: '☐ 프레임워크만', tone: 'muted' }] },
        ]}
      />
    ),
  },
  'sim-llm-models': {
    title: '시뮬레이션 LLM 배정 — 고성능이 아니라 적재적소',
    note: '수백 콜이 도는 반응 구간엔 경량 모델을 쓰고, 품질은 페르소나 조건화 + QA 재시도로 확보.',
    render: () => (
      <Matrix
        columns={['모델', '이유']}
        rows={[
          { label: '페르소나 반응', cells: [{ text: 'Gemini Flash 계열' }, { text: '표본 수만큼 병렬 호출 — 비용 효율 최우선' }] },
          { label: '광고 해석(VLM)·루브릭·QA', cells: [{ text: 'Gemini 2.5 Flash' }, { text: '이미지 이해 + 광고당 1회라 부담 적음' }] },
          { label: '장애 폴백', cells: [{ text: 'GPT(4.1-mini)' }, { text: '503 시 자동 전환 — 기본 ON' }] },
        ]}
      />
    ),
  },
  'sim-evidence-papers': {
    title: 'LLM이 소비자 행태를 모사한다는 학술 근거',
    note: '이 근거들은 "방향성·집단 분포는 신뢰할 만하다"까지만 뒷받침한다 — 반대 연구(Santurkar 2023 — LLM 응답이 특정 인구집단으로 치우치는 편향)도 함께 검토했고, 그래서 우리는 "방향성은 신뢰, 절대 수치는 단정 금지(예측 CTR ○% 환산 금지)"를 원칙으로 삼는다. 마지막 Chu 외(2025)는 우리 시뮬의 AISAS 클릭 깔때기 설계와 같은 프레임을 학술적으로 뒷받침한다.',
    render: () => (
      <Matrix
        columns={['무엇을 어떻게 보였나']}
        rows={[
          { label: 'Argyle 외 (2023) — Out of One, Many', cells: [{ text: '인구통계 프로파일을 조건으로 주면 미국 ANES 설문의 집단별 응답 분포를 재현("algorithmic fidelity"·실리콘 표본) — "데이터가 만든 페르소나"라는 우리 방식의 직접 토대', tone: 'success' }] },
          { label: 'LLMs Reproduce Human Purchase Intent (2025)', cells: [{ text: '실제 설문 약 9,300건과 대조 — LLM 페르소나의 구매의도(1~5점) 분포가 집단 수준에서 사람 응답과 유사하게 재현됨. 우리 구매의도 KPI(1~5점 분포)와 같은 척도', tone: 'success' }] },
          { label: 'Brand·Israeli·Ngwe (2023, 하버드 HBS WP)', cells: [{ text: 'GPT에 인구속성을 부여해 지불의사(WTP)를 물으면 가격이 오를수록 수요가 줄어드는 하방 수요곡선·가격민감도가 실제 소비자 조사와 유사하게 나타남' }] },
          { label: 'Park 외 (2024, 스탠퍼드·딥마인드)', cells: [{ text: '실제 1,052명을 2시간 인터뷰로 에이전트화 — 본인의 재응답 대비 GSS 정규화 정확도 약 85% 재현. 단 "2시간 인터뷰"라는 무거운 전제가 붙는다' }] },
          { label: 'Chu 외 (2025, arXiv:2510.18155)', cells: [{ text: 'LLM 멀티에이전트(소비자·판매자·환경)가 가상 town에서 가격할인 시나리오의 구매결정을 규칙 없이 시뮬 — AIDA·AISAS 소비심리 프레임과 정합하는 가격민감도·사회적 영향·구매 타이밍이 창발. 사전검증 도구로서의 LLM 시뮬을 뒷받침', tone: 'success' }] },
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
  'sim-prediction-vs-actual': {
    title: '집행 전 예측 vs 집행 후 실측 — 실제 트래픽 캠페인 1건',
    note: '사비로 집행한 실제 Meta 트래픽 캠페인(2026-07 · 노출 1,385 · 도달 1,202 · 지출 ₩7,640 · CPC ₩283 · CPM ₩5,516)과 집행 전 시뮬 예측을 나란히 본 실제 화면. ⚠️ 클릭 의향률(예측)과 CTR(실측)은 스케일이 다르므로 같은 수치로 비교하지 않고 축별로 방향만 대조한다 — "예측 CTR ○%" 환산 금지 원칙과 동일. 이 캠페인은 시뮬이 보수적으로 예측(클릭 축에서 예측<실측)한 사례이며, 단일 사례라 일반화하지 않는다 — 실측 5건 누적 시 예측↔실측 calibration이 자동 해금된다.',
    render: () => (
      <Matrix
        columns={['시뮬 예측(집행 전)', '실측(집행 후 · Meta)']}
        rows={[
          { label: '클릭 축', cells: [{ text: '클릭 의향률 0% · 약함(<20%)', tone: 'danger' }, { text: 'CTR 1.95% · 양호(≥1%)', tone: 'success' }] },
          { label: '구매 축', cells: [{ text: '구매의도 1.1/5 · 약함(<3.5)', tone: 'danger' }, { text: 'CVR 0.0% · 전환 0건', tone: 'muted' }] },
          { label: '보조 지표', cells: [{ text: '신뢰도 2.8/5 · 거부율 90%', tone: 'muted' }, { text: '종합 판정 — 예측보다 실측이 좋음', tone: 'success' }] },
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
  'mgmt-apscheduler-choice': {
    title: '왜 Celery·SQS가 아니라 APScheduler인가',
    note: '핵심 방어 논리 — 스케줄러에는 읽기·무상태·멱등한 잡만 올렸고, 상태를 바꾸는 집행은 전부 사람 승인 뒤에 있다.',
    render: () => (
      <StatusRow
        items={[
          { label: '단일 EC2 모놀리식 — 브로커·워커 프로세스 추가는 운영 인프라만 늘림', state: 'success', detail: '잡이 주기적 읽기 스캔+제안 기록이라 큐잉·재시도 보장이 필요한 성격이 아님' },
          { label: 'cron 대비 — 앱 컨텍스트(설정·DB·wiring)를 그대로 공유', state: 'success', detail: 'MANAGEMENT_SCHEDULER_ENABLED 플래그 하나로 dev·CI에서는 기본 off' },
          { label: '다중 인스턴스 확장 시 중복 실행 한계', state: 'muted', detail: '알고 미룬 트레이드오프 — 스케일아웃 시점이 곧 잡 큐 도입 재검토 시점(Open Issue로 관리)' },
        ]}
      />
    ),
  },
  'mgmt-scheduler-restart': {
    title: '서버 재시작과 스케줄러',
    note: '잡 영속화가 필요 없는 잡만 스케줄러에 올렸다 — 그래서 인메모리로 충분하다.',
    render: () => (
      <StatusRow
        items={[
          { label: '잡스토어는 인메모리 — 재시작하면 스케줄 상태 유실', state: 'muted', detail: '의도적으로 영속화하지 않음' },
          { label: '잡이 전부 무상태 읽기 스캔 — 다음 틱에 처음부터 재계산하면 끝', state: 'success' },
          { label: '재기동 시 같은 제안 중복 적재는 dedup_key로 차단', state: 'success', detail: 'rebalance:{from}:{to} · weekly:{until} 등 automation_runs 단위 dedup' },
        ]}
      />
    ),
  },
  'mgmt-scheduler-intervals': {
    title: '워커 주기는 잡마다 다르다',
    note: 'CPC는 시간 단위로 출렁이는 지표 — 예산 이동 제안만 일 단위이고, 이상 감지는 시간 단위로 돈다.',
    render: () => (
      <InfoCards
        items={[
          { label: '이상 스캔(게재0·소재피로·지갑 가드레일)', value: '60분', detail: '빠른 대응이 필요한 감지', tone: 'point' },
          { label: '리밸런싱 제안', value: '24시간', detail: '잦은 리밸런싱은 오히려 예산을 흔듦', tone: 'primary' },
          { label: '주간 성과 리포트', value: '7일', detail: '읽기 전용 집계 다이제스트', tone: 'neutral' },
        ]}
      />
    ),
  },
  'mgmt-scheduler-eventloop': {
    title: '인프로세스 스케줄러가 API를 블로킹하지 않는 이유',
    note: '',
    render: () => (
      <StatusRow
        items={[
          { label: '잡 내용이 전부 async I/O(Meta API 조회·DB 적재)', state: 'success', detail: '대기 중에는 이벤트 루프를 양보 — FastAPI 요청 처리와 공존' },
          { label: 'APScheduler 기본 max_instances=1', state: 'success', detail: '이전 잡이 안 끝났으면 다음 틱이 겹쳐 돌지 않음' },
          { label: 'CPU 헤비 작업이었다면 별도 프로세스가 정답', state: 'muted', detail: '현재 잡 성격(I/O 위주)이라 인프로세스를 선택한 것' },
        ]}
      />
    ),
  },
  'mgmt-rebalance-thresholds': {
    title: '1.2배·20%라는 숫자의 근거',
    note: '통계적 최적값이 아니라 안전 마진 설계 — 수치는 campaign_policy 한 곳에만 정의(단일 원천)해 프론트·백이 어긋나지 않는다.',
    render: () => (
      <InfoCards
        items={[
          { label: 'CPC 격차 게이트', value: '1.2배 초과', detail: '이내 격차는 노이즈로 보고 예산을 흔들지 않음', tone: 'point' },
          { label: '이동 폭', value: '일예산의 20%', detail: '한 번에 몰지 않고 점진 이동, 백원 단위 절사', tone: 'primary' },
          { label: '최소 이동액', value: '₩1,000', detail: '이보다 작으면 제안 자체를 안 함', tone: 'neutral' },
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
  'mgmt-live-execution': {
    title: '실제 집행 — Facebook·Instagram 채널 직접 운영',
    note: '채널명을 클릭하면 실제 운영 중인 라이브 페이지가 새 탭으로 열립니다. 수치는 전부 실제 운영 화면 스크린샷 기준(2026-07 조회) — 팔로워 0명 신규 계정에서 게시물·광고 집행으로 발생한 반응.',
    render: () => (
      <div className="space-y-6">
        <Pipeline
          steps={[
            { label: '채널 개설', detail: 'Facebook 페이지 · Instagram 계정', tone: 'neutral' },
            { label: '시안 게시', detail: '제너레이터 산출 시안 업로드', tone: 'neutral' },
            { label: 'Meta Ads 집행', detail: '실제 광고 계정으로 집행', tone: 'primary' },
            { label: '매니지먼트 수집', detail: 'Marketing API로 성과 읽기', tone: 'success' },
          ]}
        />
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
          {/* Facebook 묶음 */}
          <div className="space-y-4">
            <a
              href="https://www.facebook.com/profile.php?id=61590800941467"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-full bg-primary-subtle px-4 py-1.5 text-sm font-semibold text-primary hover:underline"
            >
              Facebook — 광고비피해자
              <ExternalLink size={14} strokeWidth={2} />
            </a>
            <InfoCards
              items={[
                { label: 'Facebook 조회', value: '1,064', detail: '최근 28일(6/14~7/11)', tone: 'success' },
                { label: '시작 팔로워', value: '0명', detail: '신규 개설 계정', tone: 'neutral' },
              ]}
            />
            <ShotGrid
              cols={1}
              shots={[
                { src: '/appendix/fb-page.png', caption: 'Facebook 페이지 — 광고비피해자' },
                { src: '/appendix/fb-insights.png', caption: 'Facebook 프로페셔널 대시보드 인사이트' },
                { src: '/appendix/fb-likes.png', caption: 'Facebook — 실제 좋아요 알림' },
              ]}
            />
          </div>
          {/* Instagram 묶음 */}
          <div className="space-y-4">
            <a
              href="https://www.instagram.com/cclick_me"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-full bg-point-subtle px-4 py-1.5 text-sm font-semibold text-point hover:underline"
            >
              Instagram — @cclick_me
              <ExternalLink size={14} strokeWidth={2} />
            </a>
            <InfoCards
              items={[
                { label: 'Instagram 도달 계정', value: '2,006', detail: '팔로워가 아닌 사람 100%', tone: 'success' },
                { label: 'Instagram 반응', value: '9', detail: '좋아요 등 상호작용', tone: 'success' },
              ]}
            />
            <ShotGrid
              cols={1}
              shots={[
                { src: '/appendix/ig-profile.png', caption: 'Instagram — @cclick_me 프로필' },
                { src: '/appendix/ig-insights.png', caption: 'Instagram 계정 인사이트' },
                { src: '/appendix/ig-likes.png', caption: 'Instagram — 실제 좋아요 알림' },
              ]}
            />
          </div>
        </div>
      </div>
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
  'chat-memory-tiers': {
    title: '대화 기억 3계층 — 정확성·용량·지속성',
    note: '정확성·용량·지속성 세 요구가 서로 충돌해 한 방식으로는 다 만족할 수 없다 — 각 계층이 앞 계층이 못 푸는 문제를 하나씩 맡는다. CPU 캐시–메모리–디스크, 사람의 작업기억–장기기억과 같은 검증된 계층 패턴을 LLM 컨텍스트에 적용한 것.',
    render: () => (
      <div className="space-y-2">
        {/* ① 매 턴 LLM에 주입되는 컨텍스트 윈도우 — 압축 요약 + 최근 4턴 원문 */}
        <div className="rounded-xl border-2 border-line bg-card p-5">
          <p className="mb-3 text-base font-semibold text-ink-secondary">매 턴 LLM에 주입되는 컨텍스트 윈도우</p>
          <div className="flex items-stretch gap-2">
            <div className="flex flex-[3] flex-col justify-center rounded-lg border-2 border-warning-border bg-warning-subtle px-4 py-3 text-center">
              <p className="text-base font-semibold text-warning">압축 — 오래된 턴은 요약으로</p>
              <p className="mt-1 text-sm text-ink-tertiary">용량 담당 · 컨텍스트 초과·토큰 비용 억제</p>
            </div>
            {['턴 N-3', '턴 N-2', '턴 N-1', '턴 N'].map((t) => (
              <div
                key={t}
                className="flex flex-1 flex-col justify-center rounded-lg border-2 border-primary/30 bg-primary-subtle px-2 py-3 text-center"
              >
                <p className="text-base font-semibold text-primary">{t}</p>
                <p className="mt-1 text-sm text-ink-tertiary">원문</p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-sm text-ink-tertiary">
            숏텀(정확성 담당) — 최근 4턴은 원문 그대로 유지, &lsquo;아까 그 카피로 해줘&rsquo;가 깨지지 않음
          </p>
        </div>

        {/* ↓ 저장 방향 */}
        <div className="flex items-center gap-2 pl-10">
          <ArrowDown size={20} strokeWidth={2} className="shrink-0 text-ink-tertiary" />
          <p className="text-sm text-ink-tertiary">오래된 기록·세션 종료 → 요약과 실행 이력으로 저장</p>
        </div>

        {/* ② 롱텀 저장소 */}
        <div className="rounded-xl border-2 border-success-border bg-success-subtle p-5">
          <p className="mb-3 text-base font-semibold text-success">롱텀 — 세션을 넘는 저장소 · 지속성 담당</p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <div className="rounded-lg border border-line bg-card px-4 py-3">
              <p className="text-base font-semibold text-ink">자연어 요약</p>
              <p className="mt-1 text-sm text-ink-tertiary">의미 검색 — pgvector</p>
            </div>
            <div className="rounded-lg border border-line bg-card px-4 py-3">
              <p className="text-base font-semibold text-ink">실행 이력</p>
              <p className="mt-1 text-sm text-ink-tertiary">키워드·날짜 검색 — tsvector</p>
            </div>
          </div>
        </div>

        {/* ↑ 회수 방향 */}
        <div className="flex items-center gap-2 pl-10">
          <ArrowUp size={20} strokeWidth={2} className="shrink-0 text-ink-tertiary" />
          <p className="text-sm text-ink-tertiary">
            &lsquo;지난주에 돌린 시뮬 결과 기억나?&rsquo; → 검색으로 회수해 컨텍스트에 재주입
          </p>
        </div>
      </div>
    ),
  },
  'chat-memory-counterfactual': {
    title: '한 계층만 쓰면 무엇이 깨지나',
    note: '각 계층은 앞 계층이 못 푸는 문제를 하나씩 맡는다 — 숏텀=정확성, 압축=용량, 롱텀=지속성.',
    render: () => (
      <StatusRow
        items={[
          { label: '숏텀만 쓰면?', state: 'danger', detail: '긴 세션에서 컨텍스트 초과로 실패 + 세션 간 기억이 0이 됨' },
          { label: '전부 요약하면?', state: 'danger', detail: "'아까 그 문구 그대로'가 깨짐 — 직전 맥락의 정확성을 포기하게 됨" },
          { label: '롱텀 검색만 쓰면?', state: 'danger', detail: '매 턴 검색 왕복 비용 + 검색이 놓치면 직전 대화조차 모름. 숏텀은 검색 실패가 없는 확실한 기억' },
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
  GENERATOR_DOMAIN,
  {
    id: 'simulation',
    label: '시뮬레이션',
    accent: 'point',
    icon: <Users size={16} strokeWidth={1.8} />,
    questions: [
      { id: 's1', q: '최신 논문 기법(SSR)을 도입했다가 하루 만에 롤백했다던데, 정확히 뭐가 문제였나요?', exhibitKey: 'sim-ssr-flat' },
      { id: 's2', q: '그 SSR 판정이 구체적으로 어떻게 틀렸는데요?', exhibitKey: 'sim-ssr-inversion' },
      { id: 's3', q: '그럼 지금은 어떤 방식으로 점수를 매기나요?', exhibitKey: 'sim-ssr-rollback' },
      { id: 's5', q: '페르소나 토론에서 나온 피드백이 실제로 마케팅에 쓸모가 있나요?', exhibitKey: 'sim-debate-before-after' },
      { id: 's6', q: '예측이 실제 결과랑 얼마나 맞나요?', exhibitKey: 'sim-prediction-vs-actual' },
      { id: 's7', q: '한국인 특유의 눈치·체면 문화도 반영되나요?', exhibitKey: 'sim-limits' },
      { id: 's11', q: '페르소나 샘플링에 나이 제한 같은 임계값이 있나요?', exhibitKey: 'sim-age-thresholds' },
      { id: 's12', q: '행안부 데이터에 지역 정보가 없으면 어떻게 하나요?', exhibitKey: 'sim-region-fallback' },
      { id: 's15', q: '토론에서 의견이 갈리면 어떻게 결론을 내나요?', exhibitKey: 'sim-debate-tiebreak' },
      { id: 's16', q: '실측 벤치마크(KOBACO)가 모든 광고 카테고리에 다 있나요?', exhibitKey: 'sim-kobaco-gap' },
      { id: 's17', q: "'관심 있는 사람만' 따로 보는 지표도 있나요?", exhibitKey: 'sim-interest-conditional' },
      { id: 's20', q: '실제 사람과 비슷한지 어떻게 검증했나요? 외부 설문과 비교했나요?', exhibitKey: 'sim-validation-method' },
      { id: 's21', q: '리포트가 느려서 타임아웃 났던 적 있나요?', exhibitKey: 'sim-report-timeout' },
      { id: 's22', q: '토론 결론이 중간에 잘리는 버그가 있었나요?', exhibitKey: 'sim-json-truncation' },
      { id: 's23', q: '토론 참여 인원은 고정인가요?', exhibitKey: 'sim-debate-size' },
      { id: 's26', q: '같은 광고를 두 번 돌리면 같은 결과가 나오나요? A/B 비교는 공정한가요?', exhibitKey: 'sim-fixed-panel' },
      { id: 's30', q: 'AI가 만든 소비자면 결국 AI 편향 아닌가요?', exhibitKey: 'sim-ai-bias' },
      { id: 's31', q: '그래서 예측 CTR이 몇 %라는 건가요?', exhibitKey: 'sim-no-ctr' },
      { id: 's33', q: '우리 고객층(예: 40대 여성)만 골라서 테스트할 수 있나요?', exhibitKey: 'sim-target-filter' },
      { id: 's34', q: '페르소나가 실존 인물처럼 보이는데 개인정보 문제는 없나요?', exhibitKey: 'sim-privacy' },
      { id: 's35', q: '실제 사람 응답과 비교한 정확도 수치가 있나요?', exhibitKey: 'sim-validation-method' },
      { id: 's36', q: '결과가 틀렸을 때 책임은 누가 지나요?', exhibitKey: 'sim-responsibility' },
      { id: 's37', q: '1,000명이면 LLM을 1,000번 호출하나요?', exhibitKey: 'sim-call-count' },
      { id: 's38', q: '100명 시뮬레이션 1회 비용은 얼마인가요?', exhibitKey: 'sim-cost-100' },
      { id: 's39', q: '동시에 고객 100개사가 돌리면 버티나요?', exhibitKey: 'sim-concurrency' },
      { id: 's40', q: 'LLM 가격이 오르거나 API가 막히면요?', exhibitKey: 'sim-llm-resilience' },
      { id: 's41', q: '실제 배포 광고와 비교한 사례가 있나요?', exhibitKey: 'sim-real-campaign' },
      { id: 's42', q: '시뮬 결과대로 개선했더니 성과가 올랐다는 사례가 있나요?', exhibitKey: 'sim-improvement-case' },
      { id: 's43', q: '우리 광고 시안을 업로드하면 그게 LLM 학습에 쓰이나요? 기밀 유지가 되나요?', exhibitKey: 'sim-confidentiality' },
      { id: 's44', q: '페르소나를 어떤 방식으로 생성하나요?', exhibitKey: 'sim-persona-pipeline' },
      { id: 's45', q: '시뮬레이션 비용이 많이 나오는데요? 다른 대안은 없나요?', exhibitKey: 'sim-cost-strategy' },
      { id: 's46', q: '어떤 데이터들을 활용했죠?', exhibitKey: 'sim-data-sources' },
      { id: 's47', q: 'LLM은 무슨 모델을 사용하죠? 왜 Gemini를 쓰고, 반응에 고성능 모델을 안 쓰나요?', exhibitKey: 'sim-llm-models' },
      { id: 's48', q: '이렇게 만든 페르소나가 신뢰할 수 있나요? LLM이 소비자 행태를 모사할 수 있다는 근거 자료가 있나요?', exhibitKey: 'sim-evidence-papers' },
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
      { id: 'm19', q: '시뮬레이션만 한 건가요, 실제 광고 집행도 해봤나요?', exhibitKey: 'mgmt-live-execution' },
      { id: 'm20', q: 'Celery나 SQS 같은 잡 큐 대신 APScheduler를 쓴 이유가 뭔가요?', exhibitKey: 'mgmt-apscheduler-choice' },
      { id: 'm21', q: '그냥 cron을 쓰면 안 됐나요?', exhibitKey: 'mgmt-apscheduler-choice' },
      { id: 'm22', q: '서버가 재시작되면 스케줄된 잡은 어떻게 되나요?', exhibitKey: 'mgmt-scheduler-restart' },
      { id: 'm23', q: 'EC2를 여러 대로 늘리면 같은 잡이 중복 실행되지 않나요?', exhibitKey: 'mgmt-apscheduler-choice' },
      { id: 'm24', q: '24시간 주기면 이상 상황에 너무 늦게 반응하는 것 아닌가요?', exhibitKey: 'mgmt-scheduler-intervals' },
      { id: 'm25', q: '같은 프로세스에서 도는 스케줄러가 API 응답을 느리게 하지 않나요?', exhibitKey: 'mgmt-scheduler-eventloop' },
      { id: 'm26', q: 'CPC 격차 1.2배, 이동 20%라는 숫자는 어떻게 정했나요?', exhibitKey: 'mgmt-rebalance-thresholds' },
      { id: 'm27', q: '대화 기억을 왜 숏텀·압축·롱텀 3계층으로 나눠 관리했나요?', exhibitKey: 'chat-memory-tiers' },
      { id: 'm28', q: '그냥 숏텀만 쓰거나, 전부 요약하면 안 되나요?', exhibitKey: 'chat-memory-counterfactual' },
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
