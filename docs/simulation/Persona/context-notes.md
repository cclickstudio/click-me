# 시뮬레이터 구현 — 컨텍스트 노트 (결정·근거 기록)

> 착수 전 합의된 아키텍처 결정과 그 근거를 한곳에 고정한다. 코드가 흔들릴 때 이 문서로 되돌아온다.
> 선행 문서: `SIMULATOR_SCOPE.md`(소유권 9테이블) · `PERSONA_GENERATION_STRATEGY (1).md`(파이프라인 원칙) · `Data_Collection.md`(확보처).

## 0. 한 줄 요약

다양성은 **한국 통계 분포 샘플링(LLM✗)** 으로 미리 강제하고, LLM은 **서사(4-a)·반응(4-b)·루브릭** 에서만 등장한다. 오케스트레이션은 **하이브리드 LangGraph**(바깥 선형 DAG + 반응 유닛만 사이클 서브그래프).

## 1. 소유 범위 (재확인)

- 담당 = **페르소나 생성 + 반응·집계(숫자 생산)**. 분석·리포트(문장)는 별도 팀.
- 인터페이스 계약 = `페르소나반응`(§3.5) + `시뮬레이션집계`. 분석팀은 **읽기만**.
- 분석 테이블(`토론*`·`진단`·`개선권고`·`보고서`) **import·쓰기 금지**.

## 2. 교정된 워크플로우 (네가 그린 흐름에서 2곳 수정)

```
[패널 빌드 — 오프라인/최초 1회, 광고 무관]
  단계1~3 통계 샘플링(코드, LLM✗) → 4-a 프로필 서사(LLM 1콜/명) → 패널 캐시(panel-v1)

[시뮬레이션 런 — 광고마다]
  광고입력 ─┬─ 광고해석(VLM)            ─┐
           ├─ 패널 로드(캐시)            ─┤
           └─ 루브릭 평가(LLM, 광고만 의존)─병렬─┐
                                               ├─ 페르소나별 반응 4-b (fan-out N) → QA 게이트(통과분만)
                                               └────────────────────────────────→ 집계 엔진(코드) → 핸드오프
```

**교정 ① 페르소나 생성 ≠ 반응도출 시점.** 페르소나는 패널 빌드 때 1회 만들고 캐시(`panel-v1`), 시뮬레이션마다 재생성 금지(§3.6). 반응(4-b)만 광고마다 새로, 캐시 금지. → 런 시작 시 페르소나는 이미 존재(로드), 반응만 얹는다.

**교정 ② 페르소나 "생성 에이전트" 아님.** 단계1~3은 LLM 없는 통계 샘플링(§2 원칙1). LLM(에이전트)은 4-a 서사 1콜에서만. 이름을 "샘플러(코드)" vs "서사(LLM)"로 분리.

**병렬화.** 루브릭은 광고에만 의존 → 반응 fan-out과 병렬, 집계 직전 합류.

## 3. LangGraph — 하이브리드 (채택)

파이프라인의 ~80%가 선형 DAG + 순수 샘플링이라 전부 그래프化는 과설계. **집세 내는 두 곳에만** 쓴다.

- **반응 유닛(4-b + QA 재시도)** — 진짜 사이클: `반응생성 → qa_gate → (실패&재시도여유) → 반응생성 → (통과/포기) → 반환`. 조건부 엣지. 추후 Debate(§4-2)도 여기 사이클로.
- **N명 fan-out(map-reduce)** — Send API로 페르소나당 worker, `reactions: Annotated[list, operator.add]` 리듀서로 fan-in. 체크포인터로 긴 런 중단 시 **재개**.

**그래프 안 쓰는 곳** — 단계1~3 샘플러, 집계 엔진. 순수 함수 → 일반 Python service, 노드에서 호출만.

**토폴로지** — "선형 supervisor DAG + 1개 map-reduce 노드(worker = QA 사이클 서브그래프)".
```
State(TypedDict): request, ad_interpretation, panel,
                  reactions: Annotated[list, operator.add],
                  rubric_scores, aggregate
outer: interpret_ad ─┐
       load_panel ───┤
       rubric_eval ──┴─> [Send×N → react_subgraph] ─(add)─> aggregate
react_subgraph(persona): gen_reaction → qa_gate ─실패→ gen_reaction
                                                └─통과/포기→ return
```
**현 DI 구조 유지.** `wiring.py`가 그래프를 빌드해 `SimulationService`에 주입, service `_run`은 `graph.ainvoke(state)` 호출만.

## 4. 라이브러리 역할 경계

- **LangChain** — LLM 래퍼·`with_structured_output()`(§3.5 Pydantic 강제)·임베딩만. 체인 남발 금지.
- **LangSmith** — LangGraph 없이도 `@traceable`+env로 추적됨. 그래프化하면 런당 트레이스 트리 1개로 깔끔(부수 이점).
- **FastMCP** — **코어 파이프라인엔 불필요**(내부 배치라 도구노출 레이어 불요). 자리가 있다면 (a) 챗 4-4가 시뮬을 도구 호출, (b) 데이터소스 개발 도구화. 코어엔 넣지 않는다.

## 5. 데이터 확보 현실 (웹 vs 수동)

| 데이터 | 웹 확보 | 비고 |
|---|---|---|
| OCEAN 연령대별 분포 | △ | Nature 본문 수치 가능, supplementary 원표 불확실. **CC BY-NC-ND** |
| 대학내일 소비가치 응답률 | ○ | 공개 % 인용 |
| 인구 marginal(연령×성별×지역) | △ | KOSIS/행안부 파일·API. 근사는 웹, 정밀본은 다운로드 |
| KISDI raw / MDIS raw | ✗ | 로그인·다운로드 필요 → 수동, stub+TODO |

→ 1단계는 **웹 확보 가능 분포만 작은 큐레이션 JSON**(OCEAN 연령밴드·소비가치·인구 marginal), raw 의존부는 stub. 샘플러는 이 JSON을 읽는 **코드**.

## 6. 디렉터리 매핑 (`backend/domain/simulation/`)

| 경로 | 채울 내용 |
|---|---|
| `contracts/` | §3.5 반응·집계 스키마, enum taxonomy (있음) |
| `data/` | 큐레이션 분포 JSON + 로더 |
| `tools/sampling/` | 단계1~3 샘플러(순수 엔진, LLM✗) |
| `tools/aggregation/` | 집계 엔진(순수 엔진, LLM✗) |
| `panel/` | 패널 빌드(4-a 서사 LLM) + 캐시 로드 |
| `graph/` | LangGraph 정의(outer + react_subgraph) |
| `adapters/` | VLM·LLM 어댑터(실연동) + 현 mock |
| `service/` | 오케스트레이션 구동 + SSE (그래프 astream 구동) |
| `repositories/` | 9테이블 CRUD 영속화 (미구현) |
| `agent/debate/` | 분석팀 경계 — 비워둠 |

## 7. 절대 금지 (PERSONA §7 발췌)

- 인구통계·성격·행동 속성을 LLM에게 생성시키기(동질화).
- 성격↔행동 검증 안 된 공식 억지 결합.
- 40대+ OCEAN을 20~30대와 동일 신뢰도 취급(표본 3%).
- 반응(4-b)을 캐시·재사용(캐시는 프로필 4-a만).
- A/B를 서로 다른 랜덤 패널로(고정 패널 §3.6 사용).
- 분석 테이블 import·쓰기.
