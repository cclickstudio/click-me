# 시뮬레이터 LangGraph 노드 구성 & 워크플로우 다이어그램

> `backend/domain/simulation/`의 하이브리드 LangGraph 구조 — Outer DAG(5노드) + Inner 반응 서브그래프(2노드)의 토폴로지·파일 위치·흐름을 시각화한다.
> 코드 기준: `graph/run_graph.py` · `graph/reaction_graph.py` · `service/simulation_service.py` · `wiring.py`.

## 노드 총 7개 = Outer 5 + Inner 2

## 전체 워크플로우 (Outer + Inner)

```mermaid
flowchart TB
    subgraph WIRING["⚙️ wiring.py — Composition Root (mock↔Gemini 토글)"]
        direction LR
        W["build_simulation_service()"]
    end

    subgraph SERVICE["▶️ service/simulation_service.py — astream 구동 + SSE"]
        direction TB
        START((START))

        subgraph OUTER["🔀 graph/run_graph.py — Outer DAG (노드 5)"]
            direction TB
            N1["interpret_ad<br/>광고 → AdInterpretation"]
            N2["load_panel<br/>패널 N명 로드"]
            N3["rubric_eval<br/>루브릭 점수"]
            FANOUT{{"fan_out()<br/>Send × N"}}
            N4["react (worker)<br/>페르소나 1명 반응"]
            N5["aggregate<br/>가중 집계 + CI"]
        end

        ENDN((END))

        START --> N1
        N1 -->|"pct 5→15"| N2
        N2 -->|"pct 15→30"| N3
        N3 --> FANOUT
        FANOUT -.->|"persona 1"| N4
        FANOUT -.->|"persona 2"| N4
        FANOUT -.->|"persona N"| N4
        N4 -->|"reactions += (operator.add)"| N5
        N5 -->|"pct 95"| ENDN
    end

    subgraph INNER["🔁 graph/reaction_graph.py — Inner 서브그래프 (노드 2, 사이클)"]
        direction TB
        IS((START))
        I1["gen_reaction<br/>PersonaReaction 생성"]
        I2["qa_gate<br/>QA 검사"]
        IR{"route()"}
        IE((END))
        IS --> I1 --> I2 --> IR
        IR -->|"retry (실패 & attempts<2)"| I1
        IR -->|"done (통과 or 포기)"| IE
    end

    W -.조립.-> OUTER
    W -.주입.-> INNER
    N4 ==한 명마다 실행==> INNER
    ENDN -->|"result"| HANDOFF["📦 분석팀 핸드오프<br/>persistence.save_completed_run()"]
```

## 노드 ↔ 어댑터 매핑 (덕타이핑 주입)

```mermaid
flowchart LR
    subgraph G["LangGraph 노드"]
        n1["interpret_ad"]
        n2["load_panel"]
        n3["rubric_eval"]
        ng["gen_reaction"]
        nq["qa_gate"]
        n5["aggregate"]
    end

    subgraph A["adapters/ · tools/ (wiring이 선택)"]
        a1["MockAdInterpreter<br/>· GeminiAdInterpreter"]
        a2["CachedPanelProvider<br/>· PersonaSampler"]
        a3["MockRubricEvaluator<br/>· GeminiRubricEvaluator"]
        ag["MockReactionEngine<br/>· GeminiReactionEngine"]
        aq["RuleQaGate<br/>· GeminiQaGate"]
        a5["BasicAggregator"]
    end

    n1 --> a1
    n2 --> a2
    n3 --> a3
    ng --> ag
    nq --> aq
    n5 --> a5
```

## 노드 명세

### Outer 그래프 — `graph/run_graph.py` (노드 5)

| # | 노드 | 하는 일 | 호출 어댑터(주입) |
|---|---|---|---|
| 1 | `interpret_ad` | 광고 해석(VLM) → `AdInterpretation` | `interpreter.interpret` (Mock / `GeminiAdInterpreter`) |
| 2 | `load_panel` | 고정 패널 로드 or 샘플링 → `[Persona]` | `panel.get_or_build` (`CachedPanelProvider` / `PersonaSampler`) |
| 3 | `rubric_eval` | 루브릭 차원 평가 → `[RubricScore]` | `rubric.evaluate` (Mock / `GeminiRubricEvaluator`) |
| 4 | `react` | fan-out 워커 — 페르소나 1명당 1개 디스패치, 내부에서 inner 그래프 실행 | inner 그래프(`reaction_graph`) |
| 5 | `aggregate` | QA 통과분만 가중 집계 → `SimulationAggregate` | `aggregator.aggregate` (`BasicAggregator`) |

`react`는 단일 노드지만 `fan_out()`이 `Send("react", …)`를 페르소나 수(N)만큼 발사 → map-reduce. 결과는 `reactions: Annotated[list, operator.add]` 리듀서로 fan-in 수집.

### Inner 반응 서브그래프 — `graph/reaction_graph.py` (노드 2, 사이클)

| # | 노드 | 하는 일 | 호출 어댑터(주입) |
|---|---|---|---|
| 1 | `gen_reaction` | 반응 생성(4-b) → `PersonaReaction` | `reactor.react` (Mock / `GeminiReactionEngine`) |
| 2 | `qa_gate` | QA 검사 → `qa_passed` 갱신 | `qa.check` (`RuleQaGate` / `GeminiQaGate`) |

`route()` 조건부 엣지로 재시도 루프 — 실패 & 시도 여유 있으면 `gen_reaction`으로 되돌아감(`MAX_ATTEMPTS=2`).

## 파일 위치 요약

| 영역 | 파일 | 노드/역할 |
|---|---|---|
| Outer 그래프 | `graph/run_graph.py` | `interpret_ad`·`load_panel`·`rubric_eval`·`react`·`aggregate` (5) |
| Inner 서브그래프 | `graph/reaction_graph.py` | `gen_reaction`·`qa_gate` (2, 사이클) |
| 구동 | `service/simulation_service.py` | `astream` + SSE 진행률 |
| 조립 | `wiring.py` | mock↔Gemini 주입 유일 지점 |
| 어댑터 | `adapters/mock_engine.py`, `adapters/gemini/` | 실 LLM/QA 구현체 |
| 순수 엔진 | `tools/sampling/`, `tools/aggregation/`, `tools/panel/` | 샘플러·집계·패널(LLM✗) |

## 핵심 설계 포인트

- 값싼 preamble 3개(`interpret_ad`·`load_panel`·`rubric_eval`)는 직렬 — 불균등 깊이 join을 피하려는 의도(`run_graph.py` 주석).
- 비싼 N개 반응만 병렬 fan-out — LLM 콜은 여기서만 N배 발생.
- 노드는 어댑터를 모름 — 전부 덕타이핑 주입, mock↔실 Gemini 교체는 `wiring.py` 한 곳에서만.
- Inner 그래프의 사이클(retry 루프)이 LangGraph를 쓰는 진짜 이유 — 나머지 80%는 선형이라 과설계 회피(`context-notes.md §3`).
