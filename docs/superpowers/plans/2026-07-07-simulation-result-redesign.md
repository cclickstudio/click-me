# 시뮬 결과 화면 재설계(탭 분리형 + 블루 모노크롬) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `SimulationResultView`를 히어로(목표달성+KPI 한 줄) 고정 + 3탭(개요/페르소나 반응/토론·리포트) 구조로 재구성하고 색상을 블루 모노크롬으로 통일한다.

**Architecture:** 스펙 `docs/superpowers/specs/2026-07-07-simulation-result-redesign-design.md` 기준. 데이터 계산 로직(purchaseDist·rejectionDist 등)은 수정 없이 위치만 이동. 페르소나 카드는 새 파일 `PersonaReactionCard.tsx`로 분리. DebatePanel·SimulationReportView 내부는 손대지 않는다.

**Tech Stack:** Next.js(TS)·Tailwind. 프론트 단위 테스트 셋업이 없으므로 태스크별 검증은 `pnpm exec tsc --noEmit`(+ 마지막에 ESLint·Claude Preview).

**검증 공통 명령** (frontend/ 에서): `pnpm exec tsc --noEmit -p tsconfig.json` → 출력 없음(성공) 기대.

---

### Task 1: PersonaReactionCard 컴포넌트 신규 작성

**Files:**
- Create: `frontend/src/components/simulator/PersonaReactionCard.tsx`
- 참조: `frontend/src/components/simulator/SimulationResultView.tsx:19-67` (라벨 맵·aisasFunnel — 이 태스크에서 새 파일로 옮겨 export하고, Task 5에서 원본 삭제)

- [ ] **Step 1: 파일 작성**

라벨 맵과 `aisasFunnel`은 SimulationResultView.tsx 19-67줄의 것을 그대로 가져오되 이 파일에서 export한다(부모의 거부 사유 카드가 `REJECTION_LABEL`을 계속 쓰기 때문). 거부 뱃지는 스펙대로 빨강 배경 제거 → 회색 배경. 상세 펼침의 소비가치·미디어행동·사회경제는 `JSON.stringify` 대신 key: value 나열.

```tsx
'use client';
// 페르소나 반응 카드 — 탭 ② 그리드용. 요약(인적·AISAS·발화) + 클릭 시 상세(OCEAN·소비가치 등) 펼침.

import type { SimRunResult } from '@/lib/types';

type Reaction = SimRunResult['reactions'][number];
type Persona = NonNullable<SimRunResult['personas']>[number];

/* ─── enum 한글 라벨(백엔드 contracts/enums.py 동기화) ─── */
export const EMOTION_LABEL: Record<string, string> = {
  curiosity: '호기심',
  delight: '즐거움',
  empathy: '공감',
  trust: '신뢰',
  indifference: '무관심',
  annoyance: '거부감',
  distrust: '불신',
  other: '기타',
};
export const REJECTION_LABEL: Record<string, string> = {
  irrelevant: '무관함',
  offensive: '불쾌함',
  overpriced: '비쌈',
  overpromise: '과장',
  distrust: '불신',
  ad_fatigue: '광고 피로',
  other: '기타',
};
export const DROP_LABEL: Record<string, string> = {
  no_reason_to_explore: '탐색 동기 없음',
  price_concern: '가격 부담',
  low_relevance: '낮은 관련성',
  unclear_message: '메시지 불명확',
  distrust: '불신',
  other: '기타',
};
export const GENDER_LABEL: Record<string, string> = { M: '남성', F: '여성' };
export const OCEAN_LABEL: Record<string, string> = {
  openness: '개방성',
  conscientiousness: '성실성',
  extraversion: '외향성',
  agreeableness: '친화성',
  neuroticism: '신경성',
};

export function aisasFunnel(a: Reaction['aisas']): string {
  const stages: [keyof typeof a, string][] = [
    ['attention', 'A'],
    ['interest', 'I'],
    ['search', 'S'],
    ['action', 'A'],
    ['share', 'S'],
  ];
  return stages.map(([k, label]) => (a[k] ? label : '·')).join('');
}

// object → "key: value" 줄 나열(JSON.stringify 노출 개선)
function kvList(obj: Record<string, unknown>) {
  return Object.entries(obj).map(([k, v]) => (
    <span key={k} className='mr-3'>
      {k}: {typeof v === 'object' ? JSON.stringify(v) : String(v)}
    </span>
  ));
}

interface Props {
  reaction: Reaction;
  persona?: Persona;
  isOpen: boolean;
  onToggle: () => void;
}

export function PersonaReactionCard({ reaction: r, persona: p, isOpen, onToggle }: Props) {
  return (
    <div
      className={`bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl p-4 transition-colors ${
        r.qa_passed ? '' : 'opacity-60'
      }`}>
      {/* 인적사항 + AISAS */}
      <div className='flex items-center justify-between gap-2 mb-1.5'>
        <button
          type='button'
          onClick={() => p && onToggle()}
          className='text-sm font-medium text-[#191F28] dark:text-[#F2F4F6] hover:text-[#3182F6] text-left'>
          {p ? (
            <>
              {p.age}세 {GENDER_LABEL[p.gender] ?? p.gender} · {p.region}
              <span className='ml-1 text-[10px] text-[#B0B8C1] dark:text-[#4B5563]'>
                {isOpen ? '▲' : '▼'}
              </span>
            </>
          ) : (
            r.persona_id
          )}
        </button>
        <span className='font-mono text-xs text-[#3182F6] dark:text-[#5B9DF9]'>
          {aisasFunnel(r.aisas)}
        </span>
      </div>

      {/* 반응 요약 뱃지 */}
      <div className='flex flex-wrap items-center gap-1.5 text-[11px] mb-1.5'>
        <span className='text-[#4E5968] dark:text-[#9CA3AF]'>
          구매 {r.purchase_intent} · 신뢰 {r.trust}
        </span>
        <span className='px-1.5 py-0.5 rounded bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]'>
          {EMOTION_LABEL[r.emotion_tag] ?? r.emotion_tag}
        </span>
        {r.rejected && (
          <span className='px-1.5 py-0.5 rounded bg-[#F2F4F6] dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6]'>
            거부
            {r.rejection_reason_tag
              ? `·${REJECTION_LABEL[r.rejection_reason_tag] ?? r.rejection_reason_tag}`
              : ''}
          </span>
        )}
        {r.drop_stage && (
          <span className='text-[#B0B8C1] dark:text-[#4B5563]'>
            이탈 {r.drop_stage}
            {r.drop_reason_tag ? `·${DROP_LABEL[r.drop_reason_tag] ?? r.drop_reason_tag}` : ''}
          </span>
        )}
        {r.exposure_context && (
          <span className='text-[#B0B8C1] dark:text-[#4B5563]'>노출 {r.exposure_context}</span>
        )}
        {!r.qa_passed && (
          <span className='text-[#D97706]'>
            QA 탈락{r.qa_fail_reason ? `·${r.qa_fail_reason}` : ''}
          </span>
        )}
      </div>

      {r.utterance && (
        <p className='text-sm text-[#4E5968] dark:text-[#9CA3AF]'>{r.utterance}</p>
      )}

      {/* 상세 펼침 */}
      {isOpen && p && (
        <div className='mt-2 p-3 rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D] text-[11px] space-y-2'>
          <div>
            <span className='text-[#8B95A1] dark:text-[#6B7280]'>OCEAN</span>
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
              <span className='text-[#8B95A1] dark:text-[#6B7280]'>소비가치</span>
              <p className='mt-0.5 text-[#4E5968] dark:text-[#9CA3AF] break-all'>
                {kvList(p.consumption_values)}
              </p>
            </div>
          )}
          {Object.keys(p.media_behavior).length > 0 && (
            <div>
              <span className='text-[#8B95A1] dark:text-[#6B7280]'>미디어 행동</span>
              <p className='mt-0.5 text-[#4E5968] dark:text-[#9CA3AF] break-all'>
                {kvList(p.media_behavior)}
              </p>
            </div>
          )}
          {Object.keys(p.socioeconomic).length > 0 && (
            <div>
              <span className='text-[#8B95A1] dark:text-[#6B7280]'>사회경제</span>
              <p className='mt-0.5 text-[#4E5968] dark:text-[#9CA3AF] break-all'>
                {kvList(p.socioeconomic)}
              </p>
            </div>
          )}
          {p.profile_narrative && (
            <div>
              <span className='text-[#8B95A1] dark:text-[#6B7280]'>프로필 서사</span>
              <p className='mt-0.5 text-[#4E5968] dark:text-[#9CA3AF]'>{p.profile_narrative}</p>
            </div>
          )}
          <span className='inline-block text-[10px] text-[#B0B8C1] dark:text-[#4B5563]'>
            가중치 {p.weight}
          </span>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 타입 검사**

Run (frontend/): `pnpm exec tsc --noEmit -p tsconfig.json`
Expected: 출력 없음. (`SimRunResult['personas']`가 optional 배열이 아니어서 `NonNullable<...>[number]`가 에러나면 `SimRunResult` 실제 타입(`frontend/src/lib/types.ts`)에 맞춰 `Persona` 별칭만 조정 — 다른 코드는 유지.)

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/components/simulator/PersonaReactionCard.tsx
git commit -m "add: 페르소나 반응 카드 컴포넌트 분리(그리드용)"
```

---

### Task 2: 히어로 재구성 — 목표달성 카드 + KPI 한 줄, 전면 배경 제거

**Files:**
- Modify: `frontend/src/components/simulator/SimulationResultView.tsx:222-335` (기존 목표달성 배너 + KPI 그리드 구간)

- [ ] **Step 1: 기존 222-294줄(목표달성 배너)과 296-335줄(4대 KPI)을 아래 단일 블록으로 교체**

`tone` 3분기(초록/노랑/빨강)를 삭제하고, 등급은 잉크색 텍스트 + 블루 막대로만. `f.rationale`·`f.contributions`·low_confidence 문구는 여기서 제거(Task 3의 "더보기"로 이동). KPI 뱃지 행(effective_n 등)은 유지하되 `intent_mismatch` 뱃지의 노랑 배경을 회색으로.

```tsx
      {/* 히어로 — 목표달성 카드 + 4대 KPI 한 줄 (블루 모노크롬, 전면 배경 없음) */}
      {agg && (
        <>
          <div className='grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4'>
            {fit && (
              <div className='lg:col-span-2 col-span-2 bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-5'>
                <p className='text-xs text-[#8B95A1] dark:text-[#6B7280]'>
                  목표 달성 가능성 · {fit.objective}
                </p>
                <div className='flex items-baseline gap-2 mt-1'>
                  <span className='text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]'>
                    {fit.grade}
                  </span>
                  <span className='text-xs text-[#8B95A1] dark:text-[#6B7280]'>
                    지수 {fit.score}/100
                  </span>
                </div>
                <div className='mt-2.5 h-1.5 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] overflow-hidden'>
                  <div
                    className='h-full rounded-full bg-[#3182F6] dark:bg-[#5B9DF9]'
                    style={{ width: `${fit.score}%` }}
                  />
                </div>
              </div>
            )}
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
            <KpiCard label='신뢰도 (1~5 평균)' value={agg.trust_avg.toFixed(2)} />
            <KpiCard
              label='거부율'
              value={formatPercent(agg.rejection_rate)}
              sub={agg.rejection_rate > 0.3 ? '▲ 30% 초과 주의' : undefined}
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
              <span className='px-3 py-1 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[#D97706]'>
                ⚠ 의도-반응 불일치 감지
              </span>
            )}
          </div>
        </>
      )}
```

주의: 이 교체로 `ObjectiveFit` import와 `fit &&((f: ObjectiveFit)=>{...})(fit)` IIFE가 사라진다. `import type { ObjectiveFit ... }`에서 `ObjectiveFit`은 아직 지우지 말 것(Task 3의 더보기에서 fit.rationale 사용 — 타입 import는 유지해도 무해하나 미사용 경고 시 제거).

- [ ] **Step 2: 타입 검사** — `pnpm exec tsc --noEmit -p tsconfig.json` → 출력 없음.

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/components/simulator/SimulationResultView.tsx
git commit -m "edit: 시뮬 결과 히어로 재구성(목표달성+KPI 한 줄, 전면 배경 제거)"
```

---

### Task 3: 탭 상태·탭 바 도입 + 탭 ① 개요 구성

**Files:**
- Modify: `frontend/src/components/simulator/SimulationResultView.tsx`

- [ ] **Step 1: 탭 state 추가**

컴포넌트 상단 state 선언부(기존 `showFailed` 근처)에 추가. `showFailed`는 Task 4에서 필터로 대체되므로 이 시점엔 그대로 둔다.

```tsx
  type ResultTab = 'overview' | 'personas' | 'debate';
  const [tab, setTab] = useState<ResultTab>('overview');
  const [showDetails, setShowDetails] = useState(false); // 개요 탭 '더보기' 접이식
```

- [ ] **Step 2: 히어로 뱃지 행 바로 아래에 탭 바 삽입**

```tsx
      {/* 탭 바 */}
      <div className='flex gap-6 border-b border-[#E5E8EB] dark:border-[#2D3748]'>
        {(
          [
            ['overview', '개요'],
            ['personas', `페르소나 반응 (${reactions.length})`],
            ['debate', '토론·리포트'],
          ] as [ResultTab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`pb-2.5 text-sm font-medium -mb-px border-b-2 transition-colors ${
              tab === key
                ? 'border-[#3182F6] text-[#3182F6]'
                : 'border-transparent text-[#8B95A1] dark:text-[#6B7280] hover:text-[#4E5968]'
            }`}>
            {label}
          </button>
        ))}
      </div>
```

- [ ] **Step 3: 개요 탭 콘텐츠 구성**

탭 바 아래를 `{tab === 'overview' && ( ... )}` 블록으로 감싸고, 기존 섹션들을 다음 순서·색상으로 재배치한다.

```tsx
      {tab === 'overview' && (
        <div className='space-y-6'>
          <div className='grid grid-cols-1 md:grid-cols-2 gap-6'>
            {/* (1) 구매의도 분포 — 기존 372-418줄 카드 그대로 이동 */}
            {/* (2) 거부 사유 분해 — 기존 421-456줄 이동 + 막대색 교체:
                   bg-[#F74D4D] dark:bg-[#F87171] → bg-[#1B64DA] dark:bg-[#5B9DF9] */}
          </div>
          <div className='grid grid-cols-1 md:grid-cols-2 gap-6'>
            {/* (3) 성향별 반응 OCEAN — 기존 459-518줄 이동 + 격차 음수색 교체:
                   text-[#E03131] → text-[#191F28] dark:text-[#F2F4F6] (양수는 #1B64DA 유지) */}
            {/* (4) 광고 해석 — 기존 526-558줄(좌열에 있던 카드)을 여기로 이동 */}
          </div>

          {/* 더보기 — 루브릭·KOBACO·목표달성 근거 (기본 접힘) */}
          <div>
            <button
              onClick={() => setShowDetails(v => !v)}
              className='text-xs text-[#8B95A1] dark:text-[#6B7280] hover:text-[#3182F6]'>
              {showDetails ? '▴ 상세 접기' : '▸ 더보기 (루브릭 · KOBACO 참고치 · 목표달성 근거)'}
            </button>
            {showDetails && (
              <div className='mt-4 space-y-6'>
                {/* (5) 루브릭 평가 — 기존 561-585줄 카드 그대로 이동 */}
                {/* (6) KOBACO 참고치 — 기존 338-369줄 카드 그대로 이동 */}
                {/* (7) 목표달성 근거 — 신규 카드, Task 2에서 히어로에서 뺀 내용 */}
                {fit && (
                  <div className={cardCls}>
                    <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-2'>
                      목표달성 판단 근거
                    </h2>
                    <p className='text-sm text-[#4E5968] dark:text-[#9CA3AF]'>{fit.rationale}</p>
                    <div className='flex flex-wrap gap-2 mt-3'>
                      {fit.contributions.map(c => (
                        <span
                          key={c.label}
                          className='text-[11px] px-2 py-1 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF]'>
                          {c.label} {Math.round(c.value * 100)}%
                          <span className='opacity-60'> ·가중 {Math.round(c.weight * 100)}%</span>
                        </span>
                      ))}
                    </div>
                    <p className='text-[11px] text-[#B0B8C1] dark:text-[#4B5563] mt-2'>
                      {fit.low_confidence && '⚠ 표본이 적어 신뢰가 낮습니다. '}
                      실측이 아닌 시뮬 신호 기반 상대 지표입니다(exploratory).
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
```

(1)(2)(5)(6)은 기존 JSX 블록을 잘라 넣기만 하고 내용 수정 금지(색상 교체 지시가 있는 (2)(3)만 해당 클래스 문자열 치환). 하단 고지문(`본 결과는 AI 시뮬레이션 기반 예측…`, 기존 784-787줄)은 탭 밖(컴포넌트 맨 아래)에 그대로 둔다.

- [ ] **Step 4: 타입 검사** — `pnpm exec tsc --noEmit -p tsconfig.json` → 출력 없음.

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/components/simulator/SimulationResultView.tsx
git commit -m "edit: 시뮬 결과 탭 도입 + 개요 탭 구성(블루 모노크롬)"
```

---

### Task 4: 탭 ② 페르소나 반응 — 필터·정렬 + 3열 카드 그리드

**Files:**
- Modify: `frontend/src/components/simulator/SimulationResultView.tsx` (기존 좌열 페르소나 반응 587-748줄 대체, 19-67줄 라벨 맵·aisasFunnel 삭제)

- [ ] **Step 1: 라벨 맵·유틸 정리**

19-67줄의 `EMOTION_LABEL`~`OCEAN_LABEL`·`aisasFunnel` 선언을 삭제하고 import로 교체. 부모에 남는 사용처는 거부 사유 카드의 `REJECTION_LABEL` 뿐이다.

```tsx
import { PersonaReactionCard, REJECTION_LABEL } from '@/components/simulator/PersonaReactionCard';
```

- [ ] **Step 2: 필터·정렬 state 및 파생 목록 추가**

`showFailed` state를 삭제하고 아래로 교체. 기존 `shown`/`failed` 계산(178·182줄)도 삭제.

```tsx
  type PersonaFilter = 'all' | 'clicked' | 'rejected' | 'qa_failed';
  type PersonaSort = 'default' | 'purchase' | 'trust';
  const [personaFilter, setPersonaFilter] = useState<PersonaFilter>('all');
  const [personaSort, setPersonaSort] = useState<PersonaSort>('default');

  const clicked = reactions.filter(r => r.aisas.action);
  const rejectedList = reactions.filter(r => r.rejected);
  const failed = reactions.filter(r => !r.qa_passed);
  const filtered =
    personaFilter === 'clicked'
      ? clicked
      : personaFilter === 'rejected'
        ? rejectedList
        : personaFilter === 'qa_failed'
          ? failed
          : reactions;
  const shownReactions =
    personaSort === 'default'
      ? filtered
      : [...filtered].sort((a, b) =>
          personaSort === 'purchase'
            ? b.purchase_intent - a.purchase_intent
            : b.trust - a.trust,
        );
```

- [ ] **Step 3: 기존 2열 그리드(520-766줄) 해체**

- 좌열 래퍼·광고해석·루브릭·페르소나 목록 JSX 삭제(광고해석·루브릭은 Task 3에서 이미 개요 탭으로 이동 완료 상태).
- DebatePanel은 Task 5에서 탭 ③로 감싼다(이 시점엔 임시로 그대로 두어도 tsc는 통과).

페르소나 탭 콘텐츠를 추가한다.

```tsx
      {tab === 'personas' && (
        <div className='space-y-4'>
          <div className='flex flex-wrap items-center justify-between gap-3'>
            <div className='flex flex-wrap gap-2'>
              {(
                [
                  ['all', `전체 ${reactions.length}`],
                  ['clicked', `클릭 의향 ${clicked.length}`],
                  ['rejected', `거부 ${rejectedList.length}`],
                  ['qa_failed', `QA 탈락 ${failed.length}`],
                ] as [PersonaFilter, string][]
              ).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setPersonaFilter(key)}
                  className={`px-3 py-1 rounded-full text-xs transition-colors ${
                    personaFilter === key
                      ? 'bg-[#3182F6] text-white'
                      : 'bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF] hover:bg-[#E5E8EB]'
                  }`}>
                  {label}
                </button>
              ))}
            </div>
            <select
              value={personaSort}
              onChange={e => setPersonaSort(e.target.value as PersonaSort)}
              className='text-xs border border-[#E5E8EB] dark:border-[#2D3748] rounded-lg px-2 py-1 bg-white dark:bg-[#1C2333] text-[#4E5968] dark:text-[#9CA3AF]'>
              <option value='default'>기본 순서</option>
              <option value='purchase'>구매의도 높은 순</option>
              <option value='trust'>신뢰도 높은 순</option>
            </select>
          </div>
          {shownReactions.length === 0 ? (
            <p className='py-16 text-center text-sm text-[#8B95A1]'>해당 조건의 반응이 없습니다</p>
          ) : (
            <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4'>
              {shownReactions.map(r => (
                <PersonaReactionCard
                  key={r.persona_id}
                  reaction={r}
                  persona={personaMap.get(r.persona_id)}
                  isOpen={expanded.has(r.persona_id)}
                  onToggle={() => toggleExpand(r.persona_id)}
                />
              ))}
            </div>
          )}
        </div>
      )}
```

- [ ] **Step 4: 타입 검사** — `pnpm exec tsc --noEmit -p tsconfig.json` → 출력 없음. (미사용 변수 에러가 나면 해당 잔재 삭제.)

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/components/simulator/SimulationResultView.tsx
git commit -m "edit: 페르소나 반응 탭 — 전체 폭 카드 그리드 + 필터·정렬"
```

---

### Task 5: 탭 ③ 토론·리포트

**Files:**
- Modify: `frontend/src/components/simulator/SimulationResultView.tsx` (DebatePanel 배치 + 기존 최종 결과 카드 769-782줄 이동)

- [ ] **Step 1: DebatePanel과 최종 결과 카드를 탭 ③ 블록으로 감싸기**

DebatePanel props는 기존(754-764줄) 그대로. 최종 결과 카드(769-782줄)도 그대로 아래에 배치.

```tsx
      {tab === 'debate' && (
        <div className='space-y-6'>
          <DebatePanel
            reactions={reactions}
            adAnalysis={ad ?? null}
            personas={result.personas ?? []}
            simulationId={result.simulation_id}
            objectiveFit={fit}
            rubricScores={result.rubric_scores}
            adTitle={adTitle || undefined}
            adDescription={adDescription || undefined}
            onReportView={setReportView}
          />
          <div className={cardCls}>
            {reportView ? (
              <SimulationReportView rv={reportView} />
            ) : (
              <>
                <h2 className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-2'>
                  최종 결과
                </h2>
                <p className='text-xs text-[#8B95A1] dark:text-[#6B7280]'>
                  토론이 끝나면 종합 리포트가 여기에 표시됩니다 (PDF 다운로드 포함).
                </p>
              </>
            )}
          </div>
        </div>
      )}
```

주의: `tab !== 'debate'`일 때 DebatePanel이 언마운트되므로 진행 중 토론 상태가 날아간다. DebatePanel 내부를 안 고치는 범위에서 이를 막으려면 조건부 렌더 대신 **숨김 유지 방식**을 쓴다.

```tsx
      <div className={tab === 'debate' ? 'space-y-6' : 'hidden'}>
        ...위와 동일 내용...
      </div>
```

(토론은 SSE 스트리밍 진행형이라 언마운트 시 세션 유실 — `hidden` 방식을 최종 채택한다.)

- [ ] **Step 2: 타입 검사** — `pnpm exec tsc --noEmit -p tsconfig.json` → 출력 없음.

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/components/simulator/SimulationResultView.tsx
git commit -m "edit: 토론·리포트 탭 배치(hidden 유지로 토론 세션 보존)"
```

---

### Task 6: 최종 검증 — lint·프리뷰·다크모드

- [ ] **Step 1: ESLint** — Run (frontend/): `pnpm lint` → 에러 0 기대(경고는 기존 수준 유지).

- [ ] **Step 2: Claude Preview 검증**

1. `preview_start`(frontend) 후 `/simulation/[임의 저장된 id]` 진입(시뮬 내역에서 실데이터 id 사용).
2. 확인 항목: 히어로 한 줄 렌더 / 탭 3개 전환 / 개요 2열 그리드·더보기 접힘 / 페르소나 3열 그리드·필터·정렬·카드 펼침 / 토론 탭 hidden 유지(탭 이동 후 복귀 시 토론 상태 보존) / 하단 고지문.
3. `preview_resize`로 모바일(1열)·다크모드 확인 — 빨강/초록/노랑 배경 잔재 없는지.
4. 스크린샷 공유.

- [ ] **Step 3: 잔재 검색**

Run: `grep -n "F04452\|F74D4D\|E03131\|FFF8E6\|F0FDF4\|FEF2F2" frontend/src/components/simulator/SimulationResultView.tsx`
Expected: 매치 없음.

- [ ] **Step 4: 마무리 커밋(필요 시)** — 검증 중 수정분이 있으면 `edit: 시뮬 결과 재설계 검증 후 보완` 커밋.
