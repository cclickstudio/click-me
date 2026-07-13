// 발표 Q&A 부록 — 제너레이터 도메인 보강 초안. 기존 exhibits.tsx의 generator 블록을 대체할 목적으로
// 따로 뽑아 작성한다. 모든 수치·동작은 코드 재검증(2026-07-13) 결과를 근거로 하며, 기존 부록이
// 코드와 어긋나던 4건(g2 해결 여부 · g12 누끼 재사용 · g17 인페인팅 호출 수 · g18 정지 상태)은 정정했다.
// 지어낸 수치는 없다. 미해결·미구현 항목은 "미해결"로 그대로 노출한다.

import { Sparkles } from 'lucide-react';
import { Pipeline, LayerStack, Matrix, Timeline, InfoCards, StatusRow, ShotGrid, type Tone } from './primitives';

export type GenQuestion = { id: string; q: string; exhibitKey: string };
export type GenExhibit = { title: string; note: string; render: () => React.ReactNode };

// ── 질문 목록 (기존 g1~g18 유지 + g19~g22 신규) ──────────────────────
export const GENERATOR_DOMAIN = {
  id: 'generator',
  label: '제너레이터',
  accent: 'warning' as Tone,
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
    { id: 'g12', q: '채팅에서 개선모드로 들어가면 아까 만든 누끼를 재사용하나요?', exhibitKey: 'gen-chat-cutout' },
    { id: 'g13', q: '자동 개선 루프는 몇 번까지 반복되나요?', exhibitKey: 'gen-loop-limit' },
    { id: 'g14', q: '어떤 지표가 부족하면 뭘 고칠지는 어떻게 정하나요?', exhibitKey: 'gen-loop-axis' },
    { id: 'g15', q: '한글 폰트는 어떻게 처리하나요? 라이선스 문제는 없나요?', exhibitKey: 'gen-font' },
    { id: 'g16', q: '브랜드 컬러가 밝으면 버튼 글씨가 안 보이는 문제 없었나요?', exhibitKey: 'gen-contrast-bug' },
    { id: 'g18', q: '서버가 재시작되면 생성 중이던 작업은 어떻게 되나요?', exhibitKey: 'gen-restart' },
    { id: 'g19', q: '시안 3개 중 1등이 왜 1등이에요? 실제로 반응이 제일 좋을 거란 뜻인가요?', exhibitKey: 'gen-rank-meaning' },
    { id: 'g20', q: '오탈자·가독성 검수는 언제 진짜로 붙나요?', exhibitKey: 'gen-qa-roadmap' },
    { id: 'g21', q: '신규 생성은 Gemini인데, 개선 모드는 왜 항상 OpenAI로 도나요?', exhibitKey: 'gen-improve-openai' },
    { id: 'g22', q: '모델 상위 버전으로 올리면 OpenAI 라벨 깨짐 문제도 해결되나요?', exhibitKey: 'gen-model-tier' },
    { id: 'g23', q: '발표에서 못 보여준 생성 기능이 더 있나요? (카드뉴스·플랫폼 리사이징·브랜드 키트)', exhibitKey: 'gen-extra-features' },
  ] satisfies GenQuestion[],
};

// ── 시각 자료 ────────────────────────────────────────────────────────
export const GENERATOR_EXHIBITS: Record<string, GenExhibit> = {
  // g1 ─ 트러블슈팅: AI가 쓴 한글이 깨짐
  'gen-korean-typo': {
    title: '트러블슈팅 — AI가 쓴 한글이 깨짐',
    note: '해결 방안: LLM별 성능 비교 + Harness로 광고 카피 품질 검증. 카피(PIL)와 라벨(이미지 모델)을 분리해 각각 잡았다.',
    render: () => (
      <LayerStack
        layers={[
          {
            label: '① 광고 카피는 AI가 아닌 PIL이 작성 → 오타율 0%',
            detail: '이미지 모델은 배경·상품만 그리고, 헤드라인·본문·CTA는 코드가 폰트로 직접 렌더한다. 확률적 생성물이 아니라 결정론 합성이라 구조적으로 오타가 생길 수 없다.',
            tone: 'success',
          },
          {
            label: '② 상품 라벨은 이미지 모델 전환으로 대응 → 오타율 89% 감소',
            detail: 'gpt-image-1(누끼 후 상품 재생성)에서 gemini-2.5-flash-image(원본 멀티모달 직접 참조)로 교체. 비용은 유지.',
            tone: 'success',
          },
        ]}
      />
    ),
  },

  // g2 ─ 트러블슈팅: LangSmith 비용 관측 공백 (해결됨 — 기존 부록의 "미해결" 표기는 정정)
  'gen-langsmith-gap': {
    title: '트러블슈팅 — LangSmith가 비용의 85%를 관측하지 못함',
    note: '해결 완료. LangSmith는 LangChain/LangGraph를 거치는 텍스트 LLM만 자동 추적하므로, SDK를 직접 부르는 이미지 생성은 잡히지 않았다.',
    render: () => (
      <>
        <LayerStack
          layers={[
            {
              label: '원인 — SDK를 직접 부르는 호출은 LangSmith가 자동으로 못 잡음',
              detail: '이미지 생성 API는 LangChain 체인을 타지 않아 토큰·비용 자동 계산 대상이 아니다.',
              tone: 'danger',
            },
            {
              label: '해결 — 이미지 단가를 메타데이터로 직접 주입',
              detail: '(모델 × 품질 × 작업내용) 단가표로 cost_usd를 계산해 노드 메타에 분해 기록. 한 노드에서 여러 장 생성 시 누적한다.',
              tone: 'success',
            },
          ]}
        />
        <div className="mt-4">
          <InfoCards
            items={[
              { label: '실비 반영률', value: '~15% → ~100%', detail: '텍스트 토큰만 잡히던 상태에서 이미지 실비까지 관측', tone: 'success' },
              { label: '기록되는 실비', value: 'cost_usd 0.06735', detail: '장당 약 90원 (기존 표시값 $0.0036은 텍스트 토큰만)', tone: 'warning' },
            ]}
          />
        </div>
      </>
    ),
  },

  // g3 ─ 시안 3종 생성 흐름
  'gen-flow': {
    title: '시안 3종 생성 흐름 — LangGraph 5노드',
    note: '값싼 준비 단계는 직렬, 비싼 후보 생성만 병렬. 순위는 파이프라인이 아니라 조회 시점에 매긴다.',
    render: () => (
      <>
        <Pipeline
          steps={[
            { label: '상품 분석', detail: '카테고리·강점·톤', tone: 'neutral' },
            { label: '전략 3종 수립', detail: 'LLM이 5전략 중 3개 선택', tone: 'warning' },
            { label: '템플릿 매핑', detail: 'A·B·C 배치', tone: 'warning' },
            { label: '후보 3종 병렬 생성', detail: '카피·이미지·오버레이·QA', tone: 'point' },
            { label: '선정 이유 설명', detail: 'LLM 1회 배치', tone: 'success' },
          ]}
        />
        <div className="mt-4">
          <StatusRow
            items={[
              {
                label: '후보 3개는 asyncio.gather로 동시 실행',
                state: 'success',
                detail: '카피 생성 → 이미지 생성 → PIL 텍스트 오버레이 → 규칙 QA를 후보마다 병렬로. 순차가 아니라 3장이 동시에 나와 전체 지연이 1장 수준으로 유지된다.',
              },
              {
                label: '설명(explain)은 후보마다 부르지 않고 1회 배치 호출',
                state: 'success',
                detail: '후보 3개의 선정 이유를 한 번의 LLM 호출로 묶어 받는다 — 토큰 절감.',
              },
              {
                label: '개선(IMPROVE) 모드는 템플릿 단계를 건너뛴다',
                state: 'muted',
                detail: '조건부 엣지로 분기해 단일 후보 1장만 생성한다.',
              },
            ]}
          />
        </div>
      </>
    ),
  },

  // g4 ─ 다양성 (FOMO 필수 이유 = 구조적 이유 + 소구로서의 표준성)
  'gen-diversity': {
    title: '시안 3종의 다양성 — 전략 3계열 강제 + FOMO 필수 포함',
    note: 'FOMO를 반드시 넣는 데는 두 가지 이유가 있다 — 레이아웃 커버리지(구조)와 소구의 표준성(마케팅).',
    render: () => (
      <>
        <LayerStack
          layers={[
            {
              label: '전략 풀 5종 중 3개를 LLM이 선택',
              detail: 'BENEFIT(혜택) · PROBLEM_SOLVING(문제해결) · SOCIAL_PROOF(사회적 증거) · FOMO(긴급성) · EMOTIONAL(감성). 고정 목록이 아니라 LLM이 상품에 맞게 고른다.',
              tone: 'neutral',
            },
            {
              label: '규칙 ① FOMO는 반드시 1개 포함',
              detail: 'FOMO는 광고에서 가장 표준적인 소구 중 하나다 — Cialdini 설득 원칙의 희소성(scarcity)에 해당하고, 상위 1.1만 개 쇼핑 사이트 크롤링에서 긴급성·희소성 메시지가 각각 437곳·609곳에서 발견될 만큼 커머스에 널리 쓰인다(Mathur et al., CSCW 2019). 동시에 FOMO만 템플릿 B에 매핑돼 있어, 이걸 넣어야 레이아웃 A·B·C가 모두 나온다.',
              tone: 'warning',
            },
            {
              label: '규칙 ② 나머지 2개는 서로 다른 계열에서',
              detail: 'A계열(benefit·problem_solving)에서 1개, C계열(social_proof·emotional)에서 1개. 소구와 레이아웃이 동시에 갈린다.',
              tone: 'warning',
            },
            {
              label: 'LLM 호출이 통째로 실패해도 기본 3종으로 보강',
              detail: 'BENEFIT · FOMO · SOCIAL_PROOF로 채워 A·B·C 템플릿이 모두 나오게 한다.',
              tone: 'success',
            },
          ]}
        />
        <div className="mt-4">
          <StatusRow
            items={[
              {
                label: 'FOMO 효과는 "무조건"이 아니라 조건부 — 그래서 시뮬로 검증한다',
                state: 'neutral',
                detail: '메타분석에 따르면 시간 기반 희소성은 고관여 제품에서 효과적이지만(Barton et al., Journal of Retailing 2022), 한정 수량·기간형 긴급성의 구매 효과가 유의하지 않았다는 보고도 있다(Ladeira et al., Psychology & Marketing 2023). 널리 쓰이는 소구지만 상품마다 통하는 정도가 다르다는 뜻이라, 시안을 만들기만 하지 않고 시뮬레이터로 사전 검증하는 이유가 여기에 있다.',
              },
              {
                label: '한계 — 중복 검사 코드는 없다',
                state: 'danger',
                detail: '규칙은 프롬프트로만 강제한다. LLM이 같은 전략을 3번 주면 그대로 통과한다. 실무상 드물지만 구조적으로 열려 있는 경로.',
              },
            ]}
          />
        </div>
      </>
    ),
  },

  // g5 ─ Gemini 모드에서도 카피는 텍스트 LLM
  'gen-gemini-copy': {
    title: 'Gemini 모드에서도 카피는 텍스트 LLM 전담',
    note: '이미지 모델이 카피까지 쓰게 했더니 카피가 통째로 누락되는 버그가 실측으로 확인돼 분리했다.',
    render: () => (
      <Timeline
        events={[
          {
            date: '이전',
            label: '이미지 모델이 카피까지 생성',
            detail: 'gemini-3-pro가 카피 텍스트를 약 80% 확률로 통째 누락 — 이미지만 반환',
            tone: 'danger',
          },
          {
            date: '이후',
            label: '카피는 항상 gpt-4.1 텍스트 LLM',
            detail: '이미지 모델이 카피를 줘도 버리고, 텍스트 LLM이 쓴 카피를 PIL로 합성한다',
            tone: 'success',
          },
        ]}
      />
    ),
  },

  // g6 ─ 재시도 (정정: Gemini만 백오프, OpenAI는 SDK 기본)
  'gen-retry': {
    title: '이미지 생성 실패·지연 대응',
    note: '재시도 로직은 Gemini 경로에만 명시적으로 있다. OpenAI 이미지 경로는 SDK 기본 동작에 의존한다 — 정직하게 답할 것.',
    render: () => (
      <>
        <Pipeline
          steps={[
            { label: '동시 호출 1개로 직렬화', detail: 'Gemini는 동시 호출 시 503·이미지 누락 급증', tone: 'neutral' },
            { label: '503 · 429 · 이미지 누락 감지', tone: 'warning' },
            { label: '지수 백오프 재시도', detail: '3 → 6 → 10초 + 지터, 최대 4회 시도', tone: 'success' },
          ]}
        />
        <div className="mt-4">
          <StatusRow
            items={[
              {
                label: '타임아웃 — OpenAI 이미지 120초',
                state: 'neutral',
                detail: 'Gemini 경로에는 명시적 타임아웃 설정이 없다(SDK 기본).',
              },
              {
                label: '재시도 소진 시 후보 1개만 빠지는 게 아니라 생성 전체가 실패',
                state: 'danger',
                detail: '후보 병렬 실행이 예외를 전파해 status=failed로 기록되고 SSE로 에러를 내보낸다. 부분 후보 저장은 없다 — 사용자는 재생성해야 한다.',
              },
              {
                label: '예외 — 누끼 실패는 삼킨다',
                state: 'muted',
                detail: '배경 제거가 실패하면 상품 없이 0부터 생성하는 경로로 조용히 내려간다(생성 자체는 성공).',
              },
            ]}
          />
        </div>
      </>
    ),
  },

  // g7 ─ 순위 근거
  'gen-ranking-basis': {
    title: '시안 순위는 클릭률 예측이 아니다 — QA 규칙 점수 기반',
    note: '실측 누적 전까지 "예측 CTR" 같은 실측 스케일 환산은 프로젝트 원칙상 금지.',
    render: () => (
      <>
        <StatusRow
          items={[
            {
              label: '정렬 기준 — QA 통과 여부 → 평균 품질점수 → 원래 순서',
              state: 'neutral',
              detail: '결과를 조회하는 시점에 계산한다. 파이프라인 안의 별도 노드가 아니다.',
            },
            {
              label: '예측 CTR 환산 아님',
              state: 'muted',
              detail: '이미지 모델은 클릭률을 예측할 수 없다. 카피 품질 신호에 기반한 상대 순위일 뿐이다.',
            },
          ]}
        />
        <div className="mt-4">
          <Matrix
            columns={['임계값 / 계산', '점수']}
            rows={[
              { label: '글자 수', cells: [{ text: '헤드라인 20자 · 본문 50자 · CTA 10자 이내', tone: 'neutral' }, { text: '통과 수 ÷ 3', tone: 'warning' }] },
              { label: 'CTA 존재', cells: [{ text: 'CTA가 비어 있지 않은가', tone: 'neutral' }, { text: '1.0 또는 0.0', tone: 'warning' }] },
              { label: '중복 검사', cells: [{ text: '헤드라인·본문·CTA 간 부분 문자열 포함', tone: 'neutral' }, { text: '1.0 또는 0.0', tone: 'warning' }] },
            ]}
          />
        </div>
        <div className="mt-4">
          <StatusRow
            items={[
              {
                label: '주의 — 총점은 7항목 평균이라 바닥이 0.571로 깔린다',
                state: 'danger',
                detail: '실제로 채점하는 3항목 외에 항상 1.0인 4항목(오타·가독성·타깃적합·브랜드일관성)까지 분모에 포함해 평균을 낸다. 그래서 최저점이 4/7 ≈ 0.571이고 시안 간 점수 차가 좁게 나온다.',
              },
            ]}
          />
        </div>
      </>
    ),
  },

  // g8 ─ QA 정직
  'gen-qa-honest': {
    title: '품질검증 7항목 중 3개만 실제로 검사한다',
    note: '정직한 한계 — 코드 주석과 팀 문서에 이미 명시돼 있는 사항.',
    render: () => (
      <>
        <Matrix
          columns={['상태']}
          rows={[
            { label: '글자 수', cells: [{ text: '실제 규칙 검증', tone: 'success' }] },
            { label: 'CTA 존재', cells: [{ text: '실제 규칙 검증', tone: 'success' }] },
            { label: '중복 여부', cells: [{ text: '실제 규칙 검증', tone: 'success' }] },
            { label: '오탈자', cells: [{ text: '항상 통과(스텁)', tone: 'muted' }] },
            { label: '가독성', cells: [{ text: '항상 통과(스텁)', tone: 'muted' }] },
            { label: '타깃 적합성', cells: [{ text: '항상 통과(스텁)', tone: 'muted' }] },
            { label: '브랜드 일관성', cells: [{ text: '항상 통과(스텁)', tone: 'muted' }] },
          ]}
        />
        <div className="mt-4">
          <StatusRow
            items={[
              {
                label: '왜 3개만 규칙으로 했나 — 비용·지연·설명가능성',
                state: 'success',
                detail: 'QA를 LLM으로 돌리던 것을 규칙으로 바꿔 텍스트 토큰을 약 53% 절감했다. 길이·CTA·중복은 규칙으로 100% 정확히 판정되므로 LLM을 쓸 이유가 없다.',
              },
              {
                label: '오타는 애초에 검사할 필요가 없는 구조',
                state: 'success',
                detail: '카피를 PIL로 렌더하므로 오타가 발생할 수 없다. 검사 항목을 스텁으로 둔 것은 스키마 자리를 미리 잡아둔 것.',
              },
            ]}
          />
        </div>
      </>
    ),
  },

  // g9 ─ 금칙어 (경고만 — 점수 미반영)
  'gen-banned-words': {
    title: '과대광고 표현 필터 — 경고는 하되 차단은 하지 않는다',
    note: '중요: 금칙어는 policy_warnings로만 나가고 품질점수·통과 여부에는 영향을 주지 않는다.',
    render: () => (
      <>
        <InfoCards
          items={[
            {
              label: '금칙 표현',
              value: '15개',
              detail: '100% · 보장 · 기적 · 완치 · 즉시 효과 · 넘버원 · 최고 · 완벽 · 1위 · guaranteed · miracle · cure · instant · perfect · no.1',
              tone: 'warning',
            },
          ]}
        />
        <div className="mt-4">
          <StatusRow
            items={[
              {
                label: '상품명은 검사에서 제외',
                state: 'neutral',
                detail: '상품명에 "퍼펙트" 같은 단어가 들어가도 오탐하지 않도록 상품명을 먼저 지운 뒤 검사한다.',
              },
              {
                label: '한계 — 경고 목록으로만 노출되고 점수에는 반영 안 됨',
                state: 'danger',
                detail: 'Meta 광고 정책 위반 가능성을 알려주지만, 해당 시안이 QA를 통과하고 1위가 될 수도 있다. 최종 판단은 사람이 한다.',
              },
            ]}
          />
        </div>
      </>
    ),
  },

  // g10 ─ 개선 모드
  'gen-improve-redesign': {
    title: '개선 모드는 기존 이미지를 "직접" 고치지 않는다',
    note: '',
    render: () => (
      <Timeline
        events={[
          {
            date: '초기 설계',
            label: '기존 광고 이미지를 직접 수정',
            detail: '원본에 이미 텍스트가 박혀 있어, 그 위에 다시 카피를 얹으면 텍스트가 이중 노출되는 문제로 폐기',
            tone: 'danger',
          },
          {
            date: '현재',
            label: '시뮬 피드백 기반으로 다시 만든다',
            detail: '상품 누끼는 재사용하되 배경은 새로 생성하고, 기존 이미지는 텍스트 힌트로만 참조한다',
            tone: 'success',
          },
        ]}
      />
    ),
  },

  // g11 ─ 누끼 3단계 폴백
  'gen-cutout-fallback': {
    title: '상품 누끼를 못 찾을 때 — 3단계 폴백',
    note: '누끼는 신규 생성 시 1회 만들어 S3에 보존하고, 개선 모드에서 재사용한다.',
    render: () => (
      <>
        <Pipeline
          steps={[
            { label: '① 요청에 담긴 누끼 키로 직접 로드', tone: 'success' },
            { label: '② 기존 광고 키에서 역산해 재구성', detail: '광고 S3 키에서 생성 ID를 뽑아 누끼 키를 조립', tone: 'warning' },
            { label: '③ 기존 광고에서 즉석 배경 제거', detail: '검증 통과해야 채택', tone: 'point' },
          ]}
        />
        <div className="mt-4">
          <StatusRow
            items={[
              {
                label: '③단계 누끼는 검증을 통과해야 쓴다',
                state: 'neutral',
                detail: '불투명 픽셀 비율이 3~85% 범위이고, 가장 큰 덩어리가 전체 불투명 영역의 70% 이상이어야 "상품 하나가 제대로 떨어졌다"고 보고 채택한다.',
              },
              {
                label: '검증 실패 시 — 원본을 마스크 없이 Edit',
                state: 'warning',
                detail: '누끼가 못 미더우면 상품 픽셀을 잠그지 않고 기존 광고 이미지 전체를 편집한다.',
              },
              {
                label: '기존 광고조차 없으면 — 상품 없이 0부터 생성',
                state: 'muted',
                detail: '최종 폴백. 상품 이미지 없이 배경을 자유 생성한다.',
              },
            ]}
          />
        </div>
      </>
    ),
  },

  // g12 ─ 채팅 누끼 재사용 — 조건부로 된다 (백엔드가 키를 넘기고 프론트도 body에 싣는다)
  'gen-chat-cutout': {
    title: '채팅 개선모드의 누끼 재사용 — 조건부로 된다',
    note: '백엔드가 누끼 키를 찾아 넘기고, 프론트도 요청 body에 실어 보낸다. 다만 아래 두 조건을 모두 만족해야 한다.',
    render: () => (
      <>
        <Matrix
          columns={['조건', '만족하면']}
          rows={[
            {
              label: '조건 ①',
              cells: [
                { text: 'ClickMe의 신규 생성으로 만든 광고일 것', tone: 'neutral' },
                { text: '누끼 키를 역산할 수 있다', tone: 'success' },
              ],
            },
            {
              label: '조건 ②',
              cells: [
                { text: '그 생성 때 상품 이미지를 업로드했을 것', tone: 'neutral' },
                { text: '누끼가 실제로 S3에 저장돼 있다', tone: 'success' },
              ],
            },
          ]}
        />
        <div className="mt-4">
          <StatusRow
            items={[
              {
                label: '두 조건을 만족하면 — 누끼를 그대로 재사용한다',
                state: 'success',
                detail: '백엔드가 시뮬레이션의 원본 광고에서 생성 ID를 찾아 누끼 S3 키를 조립해 넘기고, 프론트 개선 폼도 이 키를 요청 body에 싣는다. 채팅 폼 경로와 폼 없이 바로 실행하는 경로 모두 전달한다. 누끼를 다시 뜨지 않으므로 상품 픽셀이 그대로 보존되고 이미지 API 호출도 1회 아낀다.',
              },
              {
                label: '조건을 못 채우면 — 3단계 폴백으로 내려간다',
                state: 'warning',
                detail: '외부에서 업로드한 광고이거나 상품 이미지 없이 만든 광고로 시뮬을 돌린 경우엔 누끼 키가 비어 있다. 이때는 기존 광고 이미지에서 즉석으로 배경을 제거하거나, 그마저 실패하면 마스크 없이 원본을 편집한다.',
              },
              {
                label: '자동 개선 루프는 아직 재사용하지 않는다 — 보완 예정',
                state: 'danger',
                detail: '루프는 상품 이미지 없이 시작해 누끼가 애초에 만들어지지 않고, 개선 요청에도 누끼 키를 싣지 않는다. 매 반복이 즉석 배경 제거로 폴백한다.',
              },
            ]}
          />
        </div>
      </>
    ),
  },

  // g13 ─ 루프 한계값
  'gen-loop-limit': {
    title: '자동 개선 루프의 한계값',
    note: '평가 신호는 QA 품질점수만 쓴다(반복마다 재시뮬하지 않음 — 비용 사유).',
    render: () => (
      <>
        <InfoCards
          items={[
            { label: '목표 품질 점수', value: '0.8', detail: '도달하면 즉시 종료', tone: 'warning' },
            { label: '최대 반복', value: '3회', detail: '시뮬 연동 시 2회로 더 조임(비용)', tone: 'warning' },
            { label: '타임아웃', value: '600초', tone: 'warning' },
          ]}
        />
        <div className="mt-4">
          <StatusRow
            items={[
              {
                label: '조기 중단 조건',
                state: 'neutral',
                detail: '고칠 거리를 못 찾으면(개선 지시문이 비면) 반복을 남겨두고도 중단한다. 개선 생성이 후보 0개를 내면 에러로 종료.',
              },
              {
                label: '최고점 시안은 계속 보존',
                state: 'success',
                detail: '반복하며 점수가 같거나 높은 후보가 나오면 교체하고, 나빠지면 이전 최고점을 유지한다.',
              },
            ]}
          />
        </div>
      </>
    ),
  },

  // g14 ─ 개선 축 선정
  'gen-loop-axis': {
    title: '무엇을 고칠지 — 목표 대비 가장 못 미치는 1축',
    note: '축 선정은 최초 1회 시뮬에서만 하고, 그 방향을 모든 반복에 고정 주입한다(하이브리드).',
    render: () => (
      <>
        <Matrix
          columns={['목표선', '미달 시 개선 방향']}
          rows={[
            { label: '클릭 의향률', cells: [{ text: '0.25', tone: 'neutral' }, { text: '클릭 유도 패턴 KB 조회', tone: 'warning' }] },
            { label: '구매 의도', cells: [{ text: '3.5 / 5', tone: 'neutral' }, { text: '구매 설득 패턴 KB 조회', tone: 'warning' }] },
            { label: '신뢰도', cells: [{ text: '3.5 / 5', tone: 'neutral' }, { text: '신뢰 강화 패턴 KB 조회', tone: 'warning' }] },
            { label: '거부율', cells: [{ text: '0.30 이하', tone: 'neutral' }, { text: '거부 요인 제거 패턴 KB 조회', tone: 'warning' }] },
          ]}
        />
        <div className="mt-4">
          <StatusRow
            items={[
              {
                label: '미달 폭을 정규화해 가장 심한 1축만 고른다',
                state: 'success',
                detail: '척도가 다른 지표(비율 vs 5점)를 정규화한 뒤 비교해, 가장 크게 미달한 축 하나만 개선 대상으로 삼는다. 여러 축을 동시에 건드려 방향이 흐려지는 것을 막는다.',
              },
              {
                label: '선정된 축의 개선 패턴을 KB에서 뽑아 매 반복에 동일하게 주입',
                state: 'neutral',
                detail: '반복마다 다시 시뮬을 돌리지 않고(비용), 최초 진단으로 얻은 방향을 고정한다.',
              },
              {
                label: '사용자 요청사항과 충돌하면 — 절충',
                state: 'warning',
                detail: '스키마 주석에는 사용자 요청이 "1순위"로 적혀 있지만, 실제 프롬프트는 시뮬 신호와 충돌 시 절충안을 만들라고 지시한다. 하드 오버라이드가 아니다.',
              },
            ]}
          />
        </div>
      </>
    ),
  },

  // g15 ─ 폰트·라이선스 (생성 화면 하단에 고지 추가함)
  'gen-font': {
    title: '한글 폰트 — Pretendard(OFL), 생성 화면에 라이선스 고지',
    note: 'OFL은 라이선스 고지를 요구한다. 생성 화면 하단에 고지 문구를 넣어 요건을 충족했다.',
    render: () => (
      <>
        <Pipeline
          steps={[
            { label: '폰트 캐시 폴더 확인', detail: '환경변수 → 설정 → 시스템 임시 폴더 순', tone: 'neutral' },
            { label: '없으면 CDN에서 다운로드', detail: 'jsDelivr, 웨이트 9종(Thin~Black)', tone: 'warning' },
            { label: '실패 시 가장 가까운 웨이트로 폴백', tone: 'success' },
          ]}
        />
        <div className="mt-4">
          <StatusRow
            items={[
              {
                label: 'Pretendard는 SIL Open Font License 1.1 — 상업적 이용·임베딩 허용',
                state: 'success',
                detail: '오픈 폰트 라이선스라 상용 서비스에서 자유롭게 쓸 수 있다. 폰트를 판매하지 않는 한 제약이 없다.',
              },
              {
                label: 'OFL 고지 의무 — 생성 화면 하단에 고지한다',
                state: 'success',
                detail: 'OFL은 저작권·라이선스 고지를 요구한다. 생성 화면 하단에 "생성된 광고 이미지의 문구는 Pretendard 글꼴로 렌더링됩니다 — SIL Open Font License 1.1, © 길형진(orioncactus)" 문구와 원저작자·라이선스 링크를 배치해 요건을 충족했다.',
              },
              {
                label: '폰트를 저장소에 내장하지 않는다',
                state: 'neutral',
                detail: 'CDN에서 런타임에 받아 캐시하므로 저장소에 폰트 바이너리를 재배포하지 않는다.',
              },
            ]}
          />
        </div>
      </>
    ),
  },

  // g16 ─ 대비 버그
  'gen-contrast-bug': {
    title: '밝은 브랜드 컬러에서 글씨가 안 보이던 문제',
    note: '실측으로 발견한 버그 — 파스텔·연회색 브랜드 컬러에서 흰 글씨가 배경에 묻혔다.',
    render: () => (
      <>
        <StatusRow
          items={[
            {
              label: '문제 — 밝은 브랜드 컬러 + 흰 글씨 = 대비 거의 0',
              state: 'danger',
              detail: 'CTA 버튼과 패널 없는 레이아웃(floating·emotional)에서 특히 심했다.',
            },
            {
              label: '해결 — 텍스트 자리의 실제 밝기를 픽셀 단위로 샘플링',
              state: 'success',
              detail: '텍스트가 들어갈 영역의 배경 밝기를 재서, 임계값(140) 이상이면 어두운 텍스트, 미만이면 흰 텍스트를 자동 선택한다. 여기에 블러 그림자를 더해 가독성을 보강한다.',
            },
            {
              label: 'CTA 버튼은 강조색을 어둡게 섞어 최소 대비 보장',
              state: 'success',
              detail: '밝은 파스텔 브랜드 컬러가 흰 글씨와 묻히지 않도록 버튼 배경색을 보정한다.',
            },
          ]}
        />
      </>
    ),
  },

  // g18 ─ 재시작 (정정! pending이 아니라 running 고정, 스캐너 기본 OFF)
  'gen-restart': {
    title: '서버 재시작 시 진행 중이던 생성 — 복구되지 않는다',
    note: '정정 사항: pending이 아니라 대부분 running 상태로 고정된다. 자동 정정은 하지 않는다.',
    render: () => (
      <>
        <StatusRow
          items={[
            {
              label: '인프로세스 asyncio 방식 — 프로세스가 죽으면 작업도 사라진다',
              state: 'danger',
              detail: '별도 큐(SQS·Celery) 없이 백그라운드 태스크로 돌린다. 단일 EC2 전제의 의도적 선택.',
            },
            {
              label: 'DB 상태는 running에 영구 고정',
              state: 'danger',
              detail: '파이프라인 시작 직후 pending → running으로 바뀌므로, 중단되면 대부분 running으로 남는다. 이후 completed/failed로 바꿔줄 주체가 없다.',
            },
            {
              label: '30분 주기 정체 감지 — 관측·알림만, 자동 정정은 안 함',
              state: 'muted',
              detail: '30분 넘게 갱신이 없는 건을 찾아 "다시 생성해 주세요" 알림을 남긴다. 상태를 강제로 failed로 고치지는 않는다.',
            },
            {
              label: '주의 — 이 스캐너는 기본 OFF',
              state: 'warning',
              detail: '플래그로 켜야 돈다. 꺼져 있으면 정체 감지조차 하지 않는다. 사용자 관점 복구 수단은 재생성뿐.',
            },
          ]}
        />
      </>
    ),
  },

  // g19 ─ 1등의 의미 (신규)
  'gen-rank-meaning': {
    title: '1등 시안이 "반응이 제일 좋다"는 뜻은 아니다',
    note: '순위와 시뮬레이션 반응 예측은 완전히 별개 축이다 — 혼동하지 말 것.',
    render: () => (
      <>
        <Matrix
          columns={['무엇을 재나', '무엇을 못 재나']}
          rows={[
            {
              label: '시안 순위 (QA)',
              cells: [
                { text: '카피가 규칙을 지켰는가', tone: 'success' },
                { text: '소비자가 반응할지', tone: 'danger' },
              ],
            },
            {
              label: '시뮬레이션',
              cells: [
                { text: '가상 소비자의 예측 반응', tone: 'success' },
                { text: '카피 규칙 준수 여부', tone: 'muted' },
              ],
            },
          ]}
        />
        <div className="mt-4">
          <StatusRow
            items={[
              {
                label: '1등 = QA 통과 + 평균 품질점수가 가장 높은 시안',
                state: 'neutral',
                detail: '글자 수·CTA 존재·중복 여부를 지켰다는 뜻이지, 실제 반응이 제일 좋을 거란 뜻이 아니다.',
              },
              {
                label: '반응 예측이 궁금하면 시뮬레이션을 돌려야 한다',
                state: 'warning',
                detail: '생성 결과에서 "이 시안으로 시뮬" 버튼으로 넘어가면 클릭 의향률·구매의도·신뢰도·거부율을 신뢰구간과 함께 볼 수 있다. 순위 1등이 시뮬 1등이 아닐 수 있다.',
              },
            ]}
          />
        </div>
      </>
    ),
  },

  // g20 ─ 오탈자·가독성 검수 로드맵 (신규 — 미해결)
  'gen-qa-roadmap': {
    title: '오탈자·가독성 검수 — 도입 일정이 잡혀 있지 않다',
    note: '미해결. 코드·로드맵 어디에도 일정이 없다. "우선순위 논의가 필요한 항목"이라고 답하는 것이 정확하다.',
    render: () => (
      <>
        <StatusRow
          items={[
            {
              label: '항목 자리(스키마)는 미리 마련해뒀다',
              state: 'neutral',
              detail: '오탈자·가독성·타깃적합·브랜드일관성 4항목이 QA 리포트에 필드로 존재하지만, 실제 검사 로직 없이 항상 통과 처리된다.',
            },
            {
              label: '오탈자는 사실상 불필요 — 카피가 PIL 렌더라 오타가 없다',
              state: 'success',
              detail: '검사할 대상 자체가 구조적으로 생기지 않는다. AI가 그린 상품 라벨은 카피가 아니라 이미지 영역이라 이 항목의 대상이 아니다.',
            },
            {
              label: '가독성은 이미 별도 경로로 측정 중',
              state: 'neutral',
              detail: '대비비를 base와 최종 이미지 diff로 산출하는 측정 스크립트가 있다. 다만 생성 파이프라인의 QA 항목으로 편입돼 있지는 않다.',
            },
            {
              label: '도입 일정 — 코드·로드맵에 없음',
              state: 'danger',
              detail: '필요성은 인지하고 있으나 우선순위가 정해지지 않았다. 발표 전 팀 내부에서 우선순위를 정해두는 것을 권장.',
            },
          ]}
        />
      </>
    ),
  },

  // g21 ─ 개선 모드가 항상 OpenAI인 이유 (신규)
  'gen-improve-openai': {
    title: '신규 생성은 Gemini, 개선 모드는 항상 OpenAI — 이유가 있다',
    note: '설정을 Gemini로 바꿔도 개선 모드에는 먹히지 않는다. 설정 무시가 아니라 기능 자체가 없기 때문.',
    render: () => (
      <>
        <Matrix
          columns={['이미지 모델', '설정을 따르는가']}
          rows={[
            {
              label: '신규 생성 (CREATE)',
              cells: [
                { text: '설정값 (기본 Gemini)', tone: 'success' },
                { text: '따른다', tone: 'success' },
              ],
            },
            {
              label: '개선 (IMPROVE)',
              cells: [
                { text: 'OpenAI 고정', tone: 'warning' },
                { text: '무시한다', tone: 'danger' },
              ],
            },
          ]}
        />
        <div className="mt-4">
          <StatusRow
            items={[
              {
                label: '이유 — Gemini는 "원본을 보존하며 일부만 수정"하는 편집 기능이 없다',
                state: 'neutral',
                detail: '개선 모드는 상품 픽셀을 잠근 채 배경만 다시 그려야 한다(마스크 인페인팅). 이 기능은 OpenAI 이미지 API에만 있어, 편집·마스크·누끼 3개 작업은 provider와 무관하게 OpenAI로 강제된다.',
              },
              {
                label: '설정을 Gemini로 두면 경고 로그 후 OpenAI로 폴백',
                state: 'warning',
                detail: 'OpenAI 키가 없으면 아예 실행되지 않는다(NotImplementedError). 조용히 잘못된 결과를 내지는 않는다.',
              },
              {
                label: '트레이드오프를 인지한 선택',
                state: 'muted',
                detail: '개선 모드는 라벨 보존력이 낮은 OpenAI를 쓰게 되지만, 원본을 지켜야 하는 요구가 더 우선이었다. Gemini가 편집을 지원하면 재검토 대상.',
              },
            ]}
          />
        </div>
      </>
    ),
  },

  // g22 ─ 상위 모델로 올리면 해결되나 (신규 — 테스트 결과 테이블)
  'gen-model-tier': {
    title: '상위 모델로 올려도 OpenAI 라벨 깨짐은 해결되지 않는다 — 실측',
    note: '사람이 원본 라벨과 대조해 판정한 결과(감사 모드). 표본: 상품 3종(프로틴바·수분크림·오메가3), 이미지 15~33장.',
    render: () => (
      <>
        <Matrix
          columns={['하위 모델', '상위 모델', '변화']}
          rows={[
            {
              label: 'Gemini · 라벨 정확율',
              cells: [
                { text: '68.8% (2.5-flash)', tone: 'warning' },
                { text: '86.0% (3-pro)', tone: 'success' },
                { text: '개선 ↑', tone: 'success' },
              ],
            },
            {
              label: 'OpenAI · 라벨 정확율',
              cells: [
                { text: '24.1% (gpt-image-1)', tone: 'danger' },
                { text: '19.8% (gpt-image-2)', tone: 'danger' },
                { text: '악화 ↓', tone: 'danger' },
              ],
            },
            {
              label: 'Gemini · 무결점 이미지',
              cells: [
                { text: '33.3%', tone: 'warning' },
                { text: '59.3%', tone: 'success' },
                { text: '개선 ↑', tone: 'success' },
              ],
            },
            {
              label: 'OpenAI · 무결점 이미지',
              cells: [
                { text: '0.0%', tone: 'danger' },
                { text: '0.0%', tone: 'danger' },
                { text: '변화 없음', tone: 'muted' },
              ],
            },
          ]}
        />
        <div className="mt-4">
          <StatusRow
            items={[
              {
                label: '원인 — OpenAI는 배경을 지우는 과정에서 상품 자체를 다시 그린다',
                state: 'danger',
                detail: '누끼를 뜨면서 상품을 재생성하므로 표면의 라벨 텍스트가 다시 그려진다. 모델 티어를 올려도 이 구조적 한계는 그대로다. 상위 모델에서 오탈자 74건·깨짐 56건.',
              },
              {
                label: 'Gemini는 원본 이미지를 직접 참조해 재구성한다',
                state: 'success',
                detail: '상위 모델에서 깨진 글자가 0건까지 줄었다. 남은 결함은 오탈자 8건·잘림 6건(상품이 포장 대신 내용물만 노출된 경우 등).',
              },
              {
                label: '판정기를 반드시 밝힐 것 — VLM은 관대하다',
                state: 'warning',
                detail: '같은 gpt-image-2를 자동 판정(VLM)은 86%, 사람은 19.8%로 봤다. "읽히기는 하지만 원본과 다른" 라벨이 많아서다. 발표에서는 사람 검수 수치를 쓴다.',
              },
            ]}
          />
        </div>
      </>
    ),
  },

  // g23 ─ 발표에서 못 보여준 3기능 (카드뉴스 · 리사이징 · 브랜드 키트)
  'gen-extra-features': {
    title: '발표에서 못 보여준 생성 기능 3종',
    note: '셋 다 AI를 추가로 부르지 않고 PIL 합성으로 해결한다 — 비용 0, 왜곡 0.',
    render: () => (
      <>
        <ShotGrid
          shots={[
            { src: '/appendix/gen-carousel.png', caption: '카드뉴스 — 관심끌기·가치전달·행동유도 3장' },
            { src: '/appendix/gen-relayout.png', caption: '플랫폼 리사이징 — IG 스토리(9:16)로 재배치' },
            { src: '/appendix/gen-brandkit.png', caption: '브랜드 키트 — 컬러·로고·톤앤매너 저장' },
          ]}
        />

        <div className="mt-5">
          <LayerStack
            layers={[
              {
                label: '① 카드뉴스 — 배경 1장으로 슬라이드 3장을 만든다',
                detail: '역할이 관심끌기 → 가치전달 → 행동유도로 고정돼 있고, CTA는 마지막 장에만 붙는다. 핵심은 이미지 API를 3번 부르지 않는다는 것 — 글자 없는 배경을 1장만 생성하고, 그 위에 슬라이드별 카피를 PIL로 얹어 3장을 만든다. 슬라이드마다 QA도 따로 돈다.',
                tone: 'success',
              },
              {
                label: '② 플랫폼 리사이징 — AI 재호출 없이 4개 규격으로',
                detail: 'IG 피드(1:1) · IG 스토리(9:16) · Facebook(1200×628) · LinkedIn(1200×627). 텍스트가 없는 원본을 비율 그대로 축소해 가운데 놓고, 남는 여백은 같은 이미지를 블러 처리해 채운다. 그 위에 카피를 새 크기에 맞춰 다시 렌더한다. 늘리거나 자르지 않으므로 상품이 찌그러지지 않는다.',
                tone: 'success',
              },
              {
                label: '③ 브랜드 키트 — 조직 단위로 저장해 재사용',
                detail: '브랜드 컬러·로고·톤앤매너를 키트로 저장해두고 생성할 때마다 불러 쓴다. 컬러는 이미지 프롬프트(배경 색감)와 PIL 오버레이(패널·CTA 버튼·숫자 강조) 양쪽에 반영되고, 로고는 모든 템플릿에서 좌상단에 합성된다.',
                tone: 'success',
              },
            ]}
          />
        </div>

        <div className="mt-5">
          <Matrix
            columns={['동작', '이미지 API 추가 호출']}
            rows={[
              {
                label: '카드뉴스 3장',
                cells: [
                  { text: '배경 1장 + 슬라이드별 카피 PIL 합성', tone: 'neutral' },
                  { text: '0회 (배경 1회로 3장)', tone: 'success' },
                ],
              },
              {
                label: '플랫폼 리사이징',
                cells: [
                  { text: '블러 배경 + 비율유지 전경 + 카피 재렌더', tone: 'neutral' },
                  { text: '0회 (PIL만)', tone: 'success' },
                ],
              },
              {
                label: '브랜드 컬러 미입력',
                cells: [
                  { text: '기본 강조색(#2563EB) + 배경 밝기 기반 텍스트색 자동 선택', tone: 'neutral' },
                  { text: '0회', tone: 'success' },
                ],
              },
            ]}
          />
        </div>

        <div className="mt-5">
          <StatusRow
            items={[
              {
                label: '"미적용 시 자동 배색"의 실체 — LLM이 색을 고르는 게 아니다',
                state: 'neutral',
                detail: '브랜드 컬러를 비우면 기본 강조색(파랑)을 쓰고, 이미지 프롬프트에는 "modern, clean, professional" 팔레트만 지시한다. 패널 없는 레이아웃은 배경 밝기를 픽셀로 재서 흰/어두운 글씨를 자동으로 고른다. 로고에서 색을 추출하는 로직은 없다.',
              },
              {
                label: '주의 — FOMO 전략은 브랜드 컬러를 덮어쓴다',
                state: 'warning',
                detail: '긴급성 소구는 코랄 레드(#E63946)를 강제 적용해 브랜드 컬러보다 우선한다. 플래시 세일 톤을 살리기 위한 의도적 선택이지만, "왜 우리 브랜드 색이 아니냐"는 질문이 나올 수 있는 지점.',
              },
              {
                label: '한계 — 톤앤매너는 카피에 반영되지 않는다',
                state: 'danger',
                detail: '톤앤매너는 이미지(배경) 프롬프트에만 들어가고, 헤드라인·본문·CTA를 쓰는 카피 LLM에는 전달되지 않는다. "신뢰감 있는, 전문적인"이라고 적어도 카피 문체는 바뀌지 않는다 — 보완 필요 항목.',
              },
              {
                label: '한계 — 요청한 사이즈가 최종 픽셀 크기는 아니다',
                state: 'warning',
                detail: '가로(1920×1080)를 골라도 이미지 모델이 지원하는 규격으로 생성되고, 요청값은 메타로만 남는다. 정확한 플랫폼 규격 출력은 리사이징 기능이 담당한다.',
              },
            ]}
          />
        </div>
      </>
    ),
  },
};
