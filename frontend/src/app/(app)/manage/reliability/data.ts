// 신뢰도 리포트 정적 데이터 — 백엔드 골든셋 평가 실측 스냅샷(파일 반영, 실시간 아님).
// 프론트는 어려운 용어를 걷어낸 쉬운 말로 표시. 원 지표명·측정 세부는 백엔드 문서 참고.

// ── 측정 메타 ──────────────────────────────────────────────────────────────
export const EVAL_META = {
  asOf: '2026-07-07',
  n: 35,
  target: 'AI 채팅 어시스턴트 (실제 서비스 그대로)',
  note: '점수는 실제 서비스 답변을 자동 채점기가 3번 평가한 값. 채점기와 답변이 같은 계열이라 상대 개선폭 위주로 봅니다.',
} as const;

// ── 셋별 5지표 — 단일셋 vs 복합셋 (개선 전 → 개선 후) ──────────────────────────
// initial: 개선 전(검색=재정렬 전, 답변=자료 없이 답한 값). improved: 개선 후.
// targetOne: 100%가 목표인가(아니면 최대한 높게가 목표).
export type SetMetric = {
  key: string;
  eng: string; // 원 지표명(영어) — 표준 용어
  short: string; // 차트 축 라벨(짧게)
  plain: string; // 카드·설명용 쉬운 이름
  group: '검색 품질' | '답변 품질';
  initial: number | null;
  improved: number;
  targetOne: boolean;
  work: string; // 이 점수를 올린 작업(쉬운 말)
  note?: string;
};

export type GoldenSet = {
  key: 'single' | 'complex';
  name: string;
  sub: string;
  examples: string[]; // 이 셋의 대표 질문 3개
  metrics: SetMetric[];
};

export const GOLDEN_SETS: GoldenSet[] = [
  {
    key: 'single',
    name: '단일셋',
    sub: '35문항 · 자료 하나로 답할 수 있는 질문 (정책·운영 가이드·기준 해석)',
    examples: [
      '광고 심사 중인데 노출이 0이야, 정상이야?',
      'CTR이 낮을 때 뭘 점검해야 해?',
      '예산 증액은 바로 되나, 승인이 필요해?',
    ],
    metrics: [
      {
        key: 'hit5',
        eng: 'Hit Rate',
        short: 'Hit Rate',
        plain: '관련 문서 찾기',
        group: '검색 품질',
        initial: 0.886,
        improved: 1.0,
        targetOne: true,
        work: '검색 결과를 골고루 섞고 중요도순으로 재정렬',
        note: '35개 모두 찾음. 정답 자료가 항상 상위에.',
      },
      {
        key: 'mrr',
        eng: 'MRR',
        short: 'MRR',
        plain: '상위에 정확히',
        group: '검색 품질',
        initial: 0.705,
        improved: 0.938,
        targetOne: false,
        work: '중요한 자료를 더 위쪽으로 정렬',
        note: '항상 1등은 비현실 — 높을수록 좋음.',
      },
      {
        key: 'ctxp',
        eng: 'Context Precision',
        short: 'CP',
        plain: '검색 결과 관련도',
        group: '검색 품질',
        initial: null,
        improved: 0.886,
        targetOne: false,
        work: '가져온 자료가 실제로 관련 있는지 측정',
        note: '상위 자료 대부분이 관련 있음.',
      },
      {
        key: 'faith',
        eng: 'Faithfulness',
        short: 'Faith',
        plain: '근거대로 답하기',
        group: '답변 품질',
        initial: null,
        improved: 1.0,
        targetOne: true,
        work: '근거가 없으면 지어내지 않게',
        note: '지어낸 것 없이 100% 근거 기반.',
      },
      {
        key: 'fc',
        eng: 'Factual Correctness',
        short: 'FC',
        plain: '답이 실제로 맞나',
        group: '답변 품질',
        initial: 0.714,
        improved: 0.986,
        targetOne: true,
        work: '회사 규칙은 자료를 근거로만 답하게 강화',
        note: '개선 전은 자료 없이 답한 값. 실제 서비스는 거의 다 맞음.',
      },
    ],
  },
  {
    key: 'complex',
    name: '복합셋',
    sub: '35문항 · 자료 2~3개를 엮어야 답할 수 있는 어려운 질문',
    examples: [
      '학습 단계인데 CTR이 낮으면 소재를 바로 바꿔야 해?',
      '전환 추적이 안 돼 있는데 ROAS가 목표보다 낮다고 볼 수 있어?',
      '대출 상품 광고인데 비슷한 타깃을 만들 수 있어?',
    ],
    metrics: [
      {
        key: 'hit5',
        eng: 'Hit Rate',
        short: 'Hit Rate',
        plain: '관련 문서 찾기',
        group: '검색 품질',
        initial: 0.8,
        improved: 1.0,
        targetOne: true,
        work: '검색 결과를 골고루 섞고 중요도순으로 재정렬',
        note: '35개 모두 찾음. 밀려나던 정답 자료를 끌어올림.',
      },
      {
        key: 'mrr',
        eng: 'MRR',
        short: 'MRR',
        plain: '상위에 정확히',
        group: '검색 품질',
        initial: 0.634,
        improved: 0.833,
        targetOne: false,
        work: '중요한 자료를 더 위쪽으로 정렬',
        note: '여러 자료를 엮어야 해 단순 셋보다 낮음 — 높을수록 좋음.',
      },
      {
        key: 'ctxp',
        eng: 'Context Precision',
        short: 'CP',
        plain: '검색 결과 관련도',
        group: '검색 품질',
        initial: null,
        improved: 0.926,
        targetOne: false,
        work: '가져온 자료가 실제로 관련 있는지 측정',
        note: '상위가 관련 자료로 채워짐.',
      },
      {
        key: 'faith',
        eng: 'Faithfulness',
        short: 'Faith',
        plain: '근거대로 답하기',
        group: '답변 품질',
        initial: null,
        improved: 1.0,
        targetOne: true,
        work: '근거가 없으면 지어내지 않게',
        note: '어려운 질문에서도 지어냄 없음.',
      },
      {
        key: 'fc',
        eng: 'Factual Correctness',
        short: 'FC',
        plain: '답이 실제로 맞나',
        group: '답변 품질',
        initial: 0.857,
        improved: 0.971,
        targetOne: true,
        work: '회사 규칙은 자료를 근거로만 답하게 강화',
        note: '규칙을 근거로 답하게 하며 0.914 → 0.971.',
      },
    ],
  },
];

// ── 취한 개선 작업 (개선 전 → 개선 후를 만든 것) ──────────────────────────────
export type EvalAction = { title: string; effect: string; tag: '방법론' | '검색' | '답변' | '수정' };

export const EVAL_ACTIONS: EvalAction[] = [
  {
    title: '정답을 파일로 고정한 평가셋 구축',
    effect:
      '질문·정답·근거 자료를 파일로 고정해 채점 기준이 흔들리지 않게 했습니다. 예전엔 정답을 그때그때 만들어 점수를 믿기 어려웠습니다.',
    tag: '방법론',
  },
  {
    title: '여러 자료를 엮어야 답하는 어려운 셋 추가',
    effect:
      '자료 2~3개를 함께 봐야 답이 되는 질문 35개를 추가해, 단순 검색을 넘는 종합 능력을 따로 측정합니다.',
    tag: '방법론',
  },
  {
    title: '검색 결과 다양화 + 재정렬',
    effect:
      '특정 용어 설명이 검색 상위를 독차지해 정작 필요한 자료를 밀어내던 문제를, 결과를 골고루 섞고 중요도순으로 재정렬해 해결했습니다. → 정답 문서를 항상 상위에서 찾습니다.',
    tag: '검색',
  },
  {
    title: '거절 관련 자료 보강',
    effect:
      '설명이 한 줄뿐이라 잘 안 잡히던 항목을 문단으로 보강해 검색이 되게 했습니다.',
    tag: '검색',
  },
  {
    title: '답변 규칙 강화',
    effect:
      '회사 고유 규칙(승인 단계·기준치 등)은 반드시 자료를 근거로만 답하도록 강화해, 지어내던 답을 바로잡았습니다.',
    tag: '답변',
  },
  {
    title: '실제 서비스 그대로 재측정',
    effect:
      '간단한 테스트가 아니라 실제 서비스가 내는 답변으로 3번 채점해, 사용자가 겪는 그대로의 품질을 쟀습니다.',
    tag: '방법론',
  },
  {
    title: '검색 정확도 점수 오류 수정',
    effect:
      '검색 정확도 점수가 다른 지표와 똑같이 계산되던 오류를 바로잡아 진짜 값을 재게 했습니다.',
    tag: '수정',
  },
];

// ── 어떻게 개선했나 — 표준(RAGAS·LlamaIndex) 기반 ───────────────────────────
// 이 프로젝트가 따른 표준 평가·개선 방식과 출처.
export type StandardBasis = { area: string; basis: string; url: string };

export const STANDARD_BASIS: StandardBasis[] = [
  {
    area: '답변 품질 평가',
    basis: 'RAGAS 표준 — 지어내지 않고 근거대로 답하는지(근거 충실도)·답이 실제로 맞는지(사실 정확도).',
    url: 'https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/',
  },
  {
    area: '검색 품질 평가',
    basis: 'LlamaIndex 표준 — 관련 문서 찾기(Hit Rate)·상위 노출(MRR)을 검색 평가 지표로 사용.',
    url: 'https://docs.llamaindex.ai/en/stable/module_guides/evaluating/usage_pattern_retrieval/',
  },
  {
    area: '검색이 약할 때 처방',
    basis: '업계 표준 — 결과 골고루 섞기(하이브리드)·중요도순 재정렬(리랭킹)·자료 보강. 우리가 적용한 것과 동일.',
    url: 'https://www.meilisearch.com/blog/rag-techniques',
  },
];

// ── 지어내기(환각) 억제 개선 (함정 질문 23개) ────────────────────────────────
// before=자료 미사용 → 자료 근거 답변 → after. 자동 채점 3회.
export const IMPROVEMENT = {
  action: '근거가 있으면 자료를 인용하고, 없으면 모른다고 답하게 함',
  selfCheck: '스스로 근거가 충분한지 점검해 부족하면 다시 찾고, 끝내 없으면 지어내지 않고 모른다고 답하는 자기교정(CRAG)',
  beforeLabel: '자료 미사용',
  afterLabel: '자료 근거 답변',
  judge: '자동 채점',
  asOf: '2026-07-06',
  overall: { before: 0.935, after: 0.978 },
  categories: [
    { key: 'C1', label: '자료 있음', before: 1.0, after: 1.0, n: 6 },
    { key: 'C2', label: '자료 밖', before: 0.9, after: 0.9, n: 5 },
    { key: 'C3', label: '틀린 전제', before: 1.0, after: 1.0, n: 5 },
    { key: 'C4', label: '숫자 함정', before: 0.875, after: 1.0, n: 4 },
    { key: 'C5', label: '분야 밖', before: 0.833, after: 1.0, n: 3 },
  ],
} as const;

// ── 한계와 극복 ────────────────────────────────────────────────────────────
export type LimitItem = { limit: string; fix: string; done: boolean };

export const LIMITATION: LimitItem[] = [
  {
    limit:
      '채점기가 답변과 같은 계열(같은 mini 모델)이라, 자기 답변에 후하게 줄 수 있습니다 (자기채점 편향).',
    fix: '다른 계열의 채점기(Gemini)로 분리해 채점하도록 배선 완료 — 무료 한도 때문에 전체 재측정은 결제 후. 그 전까지는 상대 개선폭 위주로 해석합니다.',
    done: false,
  },
  {
    limit: '검색 재정렬(리랭킹)의 일부는 아직 평가 단계 검증값입니다.',
    fix: '실제 서비스에는 결과 다양화까지 반영 완료, 재정렬은 속도·비용 검토 후 배포합니다.',
    done: false,
  },
  {
    limit: '지어내기(환각) 자체는 자기교정(CRAG)으로 실제 서비스에서 이미 막고 있습니다.',
    fix: '근거를 스스로 점검·재검색하고 없으면 모른다고 답해, 함정 질문 지어내기 억제 0.935 → 0.978. 이는 편향과 다른 축의 개선입니다.',
    done: true,
  },
];

// ── 목표 설정 방침 ──────────────────────────────────────────────────────────
export const TARGET_POLICY = {
  curated:
    '정답이 자료에 있는 평가셋(사람이 직접 큐레이션). 항상 맞혀야 하는 지표는 목표 100%, 나머지는 최대한 높게가 목표.',
  prod: '실제 사용자 트래픽(답이 없거나 모호한 질문 포함) — 이때만 업계 일반 기준을 적용.',
};

// ── 지표 설명 ──────────────────────────────────────────────────────────────
export type MetricRow = {
  eng: string; // 표준 용어(영어)
  metric: string; // 쉬운 설명 이름
  group: '검색 품질' | '답변 품질';
  note: string;
};

export const METRIC_TAXONOMY: MetricRow[] = [
  {
    eng: 'Hit Rate',
    metric: '관련 문서 찾기',
    group: '검색 품질',
    note: '질문에 맞는 자료를 상위 5개 안에 찾았는지 · 단일 100% / 복합 100%',
  },
  {
    eng: 'MRR',
    metric: '상위에 정확히',
    group: '검색 품질',
    note: '정답 자료를 얼마나 위에서 찾는지 · 단일 0.94 / 복합 0.83',
  },
  {
    eng: 'Context Precision',
    metric: '검색 결과 관련도',
    group: '검색 품질',
    note: '가져온 자료가 실제로 관련 있는지 · 단일 0.89 / 복합 0.93',
  },
  {
    eng: 'Faithfulness',
    metric: '근거대로 답하기',
    group: '답변 품질',
    note: '지어내지 않고 자료 근거로 답하는지 · 단일·복합 100%',
  },
  {
    eng: 'Factual Correctness',
    metric: '답이 실제로 맞나',
    group: '답변 품질',
    note: '답이 정답과 사실이 맞는지 · 단일 0.71→0.99 / 복합 0.86→0.97',
  },
];

// ── 측정 방법 ──────────────────────────────────────────────────────────────
export const METHOD = [
  {
    title: '정답 고정 평가셋',
    body: '질문·정답·근거 자료를 파일로 고정하고 시스템만 개선해, 점수 조작 없이 개선 효과만 봅니다.',
  },
  {
    title: '실제 서비스로 측정',
    body: '간단한 테스트가 아니라 실제 서비스가 내는 답변으로 품질을 잽니다.',
  },
  {
    title: '3번 채점 후 다수결',
    body: '채점의 흔들림을 줄이려 3번 채점해 다수결·평균을 씁니다.',
  },
  {
    title: '단순 vs 종합 분리 측정',
    body: '자료 하나로 답하는 셋과 여러 자료를 엮는 셋을 나눠, 단순 검색과 종합 능력을 따로 봅니다.',
  },
] as const;
