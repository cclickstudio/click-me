# feat/simulation 병합 변경점 — 토론(debate) 도메인 통합 (2026-06-17)

> `feat/simulation-yeotaeho` 기준 **이전 커밋 `e945190` → 현재 `c84011d`** 의 차이 정리.
> 팀원이 `feat/simulation`에 올린 작업을 fast-forward로 병합. **충돌 0건**, 36파일 +12,673 / −420.
> 내가 한 작업(메타 reach Tier2-A·analysis_view)과 **겹치지 않음** — 대부분 토론 도메인 신규/수정.

---

## 1. 한눈에 — 무엇이 달라졌나

전부 **페르소나 토론(4-1 후속, 시뮬 반응 → 토론 → 개선안)** 파이프라인 작업이다. 크게 4덩어리.

1. **토론 패널 구조 개편** — 전문가4 + 일반인2(→옵션 4)로 재편, Judge 모델 조정.
2. **일반인(lay) 선발 로직 대폭 보강** — 타깃 적합·전 연령형 보정 + LLM 재랭킹 게이트.
3. **실 LLM 경로 정리** — 토론자 Gemini 제거(Haiku·GPT 2엔진), Judge Sonnet, 무조건 실 LLM.
4. **프론트 토론 패널 연동** — `DebatePanel.tsx`(SSE 스트림·결과 렌더)를 시뮬 실행 화면에 추가.

---

## 2. 커밋 요약 (17개, 머지 제외)

| 분류 | 커밋 | 내용 |
| --- | --- | --- |
| 구조 | `a69e35e` | 토론 패널 전문가4+일반인2 재편, Judge Sonnet 다운그레이드 |
| 구조 | `9019682`·`c6484c9` | 일반인 2→4명 확대, `lay_count` 2 vs 4 API 분리(비교 운영) |
| 선발 | `c713606` | 타깃 적합 일반인 선발 — 타깃 밖 후보 배제(personas 인구통계) |
| 선발 | `ba7119c`·`4fb52c8` | 전 연령형(타깃 불명확) 보정 + LLM 재랭킹 게이트 |
| 선발 | `439afda`·`a071d62` | 선발 게이트 운영 통합(실 LLM 재랭킹 주입), 함정 테스트 6/6 |
| LLM | `9aa8c0e` | 토론자 Gemini 제거 → Haiku·GPT 2엔진 |
| LLM | `9acc880` | 토론 라우터 `use_llm` 제거 — 무조건 실 LLM |
| LLM | `31bcbf1` | Judge `propose_actions` max_tokens 300→800(한국어 JSON 잘림 방지) |
| 주제 | `350a15a` | 실 LLM이면 Judge가 논쟁적 토론 주제 유동 생성 |
| 결론 | `d9071a5` | 비전문가용 쉬운 결론(`plain_summary`) 추가 |
| 분석 | `c1b3e67`·`dde6f1c` | 메시지 수신 갭 분석(조각8/9) + 새 포맷(personas) 통합·handoff 기록 |
| 프론트 | `788f8d5` | DebatePanel SSE 스트림·결과 렌더 |
| API | `62d8f4c` | 토론 API 정리 — JSON body 4개로 축소(dummy·upload 제거) |

---

## 3. 변경 규모 큰 파일

| 파일 | 변경 | 비고 |
| --- | --- | --- |
| `tools/debate/selector.py` | +463/− | 일반인 선발 핵심 로직(타깃 보정·재랭킹) |
| `dummy/new/dummy1~6.json` | 각 +1,663 | 토론 데모/테스트용 더미 결과 6벌(신규) |
| `dummy/selection-traps.json` | +451 | 선발 함정 테스트 케이스(신규) |
| `frontend/.../DebatePanel.tsx` | +563 | 토론 패널 컴포넌트(신규) |
| `docs/simulation/debate/persona-debate-pipeline.md` | ±271 | 파이프라인 문서 갱신 |
| `adapters/llm_selector.py`·`tools/debate/trap_check.py` | 신규 | LLM 재랭킹·함정 검증 |
| `docs/simulation/sim-result-schema.md` | +153 | 정리된 시뮬 결과 스키마(전달용, 신규) |

---

## 4. 공유부·내 파일에 닿은 변경 (주의해서 볼 곳)

대부분 토론 내부지만 **두 파일은 공유/내 영역**과 닿는다.

### `domain/simulation/wiring.py` (+8/−)
- `build_debate_service`의 **실 LLM 분기만** 변경. 토론자 `Gemini` 제거 → `_ensure_env`가 `ANTHROPIC_API_KEY`·`OPENAI_API_KEY`만 요구(`GEMINI_API_KEY` 불요). `LLMSelector().choose`를 동점 재랭킹으로 주입.
- **내 변경(`build_panel_provider`의 reachability·Tier2-A)는 그대로** — 같은 파일이지만 다른 함수라 충돌 없음.

### `frontend/src/app/simulation/run/page.tsx` (+9)
- 내가 만든 시뮬 실행 화면에 **`<DebatePanel>` 한 블록 추가**. 반응 결과 아래에서 `reactions`·`adAnalysis`·`result.personas`·`simulation_id`를 받아 토론을 이어 돌린다.
- 즉 토론 패널이 **내가 추가한 `result.personas`(반응별 페르소나 속성)를 입력으로 사용** — 내 작업과 자연스럽게 연결됨.

> `api.ts`(+26)·`types.ts`(+110)·`globals.css`(+15)는 토론 패널용 타입·호출·스타일 추가.

---

## 5. 내 작업(reach·analysis_view)과의 관계

- **충돌 없음** — 내 변경은 `tools/sampling/persona_sampler.py`·`data/.../meta_reach.json`·`service/analysis_view.py`·`api/routers/simulation/`, 팀원은 `tools/debate/*`·`adapters/llm_*`·`api/routers/debate.py`로 분리.
- **시너지** — 토론 패널이 내가 정규화한 `personas` 포맷을 입력으로 쓴다. 분석용 정리 스키마(`/run?shape=analysis`)와 토론 입력은 같은 `personas`·`reactions` 계약을 공유.
- **검증** — 병합 후 `pytest tests/simulation/` 72 passed(3 실패는 기존 `aiosqlite` 미설치, 무관). 회귀 없음.

---

## 6. 한 문장

**이번 병합은 전부 페르소나 토론 파이프라인(선발·실 LLM·프론트 패널) 작업이고, 내 메타 reach·analysis_view 작업과 충돌 없이 합쳐졌으며, 토론 패널이 내가 만든 `personas` 출력을 그대로 입력으로 받아 이어진다.**
