# LangSmith 운영 가이드 — ClickMe 팀 공통

> **목적**: LangSmith를 단순 로그 뷰어가 아니라, 도메인별 비용·품질·지연시간을 추적하는 Observability 도구로 활용한다.  
> **대상**: generator·simulation·management 도메인 개발자 전원.

---

## 목차

1. [프로젝트 구조](#1-프로젝트-구조)
2. [Trace 이름 규칙](#2-trace-이름-규칙)
3. [Node / Step 이름 규칙](#3-node--step-이름-규칙)
4. [필수 Metadata](#4-필수-metadata)
5. [필수 Tags](#5-필수-tags)
6. [언제 새 Trace를 시작할지](#6-언제-새-trace를-시작할지)
7. [토큰·비용 누락 방지](#7-토큰비용-누락-방지)
8. [비용 분석 시 확인할 항목](#8-비용-분석-시-확인할-항목)
9. [현재 코드베이스 현황 & 개선 체크리스트](#9-현재-코드베이스-현황--개선-체크리스트)
10. [도메인별 구현 예시](#10-도메인별-구현-예시)

---

## 1. 프로젝트 구조

| 항목 | 값 | 비고 |
|------|-----|------|
| LangSmith 프로젝트명 | `clickme` | `.env` `LANGCHAIN_PROJECT` |
| 환경 | `development` / `staging` / `production` | `APP_ENV` 값 그대로 사용 |
| Dataset 네이밍 | `{domain}-evals-{YYYY-MM}` | 예: `simulation-evals-2026-06` |

LangSmith 대시보드에서 프로젝트 → `clickme`를 기준으로 전체 필터링한다.  
환경별 분리는 **별도 프로젝트가 아니라 Tags**로 구분한다 (→ [필수 Tags](#5-필수-tags) 참고).

---

## 2. Trace 이름 규칙

> **Trace** = 사용자의 HTTP 요청 하나에 대응하는 최상위 실행 단위.

### 형식

```
{도메인}.{기능}.{모드}
```

| 세그먼트 | 허용값 | 예 |
|---------|-------|---|
| 도메인 | `generator` `simulation` `management` | |
| 기능 | `generate` `simulate` `react` `debate` `regenerate` `analyze` | |
| 모드 | `create` `improve` `batch` — 없으면 생략 | |

### 도메인별 표준 이름

| 도메인 | Trace 이름 | 트리거 |
|--------|-----------|--------|
| generator | `generator.generate.create` | 최초 광고 생성 |
| generator | `generator.generate.improve` | 개선 모드 생성 |
| simulation | `simulation.simulate` | 전체 시뮬레이션 실행 |
| simulation | `simulation.react` | 단일 페르소나 반응 |
| simulation | `simulation.debate` | 토론 실행 |
| management | `management.regenerate` | 이미지 재생성 |
| management | `management.analyze` | 광고 분석 |

### 현재 코드에서 적용 위치

```python
# domain/generator/service/generator_service.py
# graph.ainvoke() 호출 시 config에 run_name 주입
from langchain_core.runnables import RunnableConfig

config = RunnableConfig(
    run_name="generator.generate.create",   # ← 여기
    tags=["generator", "create", env],
    metadata={...},
)
result = await graph.ainvoke(state, config=config)
```

---

## 3. Node / Step 이름 규칙

> **Node** = Trace 안의 개별 LangGraph 노드 또는 `@traceable` 함수.

### 형식

```
{도메인}:{역할}
```

| 도메인 | 역할 예시 | Node 이름 |
|--------|---------|-----------|
| generator | 상품 분석 | `generator:analyze_product` |
| generator | 전략 수립 | `generator:plan_strategies` |
| generator | 카피 생성 | `generator:generate_copy` |
| generator | 이미지 생성 | `generator:generate_image` |
| generator | 품질 검증 | `generator:check_quality` |
| simulation | 광고 이해 | `simulation:interpret_ad` |
| simulation | 페르소나 반응 | `simulation:persona_react` |
| simulation | Q&A 검증 | `simulation:qa_gate` |
| simulation | 노출 판단 | `simulation:exposure` |
| simulation | 숙고 판단 | `simulation:deliberation` |
| management | 이미지 재생성 | `management:regenerate_image` |
| tools | 페르소나 팩토리 | `tools:persona_factory` |
| tools | 광고 비전 분석 | `tools:ad_vision` |

### `@traceable` 적용 예

```python
from langsmith import traceable

@traceable(
    run_type="chain",
    name="generator:generate_copy",         # ← 표준 이름
    metadata={"prompt_version": "v1.2"},    # ← 버전 필수
)
async def generate_copy(state: dict) -> dict:
    ...
```

---

## 4. 필수 Metadata

> 모든 Trace에 아래 필드를 포함해야 LangSmith 필터·그룹핑이 동작한다.

### Trace 레벨 (최상위)

| 키 | 타입 | 설명 | 예 |
|----|------|------|----|
| `domain` | str | 바운디드 컨텍스트 | `"generator"` |
| `feature` | str | 기능 분류 | `"generate"` |
| `mode` | str | 실행 모드 | `"create"` / `"improve"` |
| `env` | str | 실행 환경 | `"development"` |
| `user_id` | str | 요청 사용자 ID | `"user_42"` — 없으면 `"anonymous"` |
| `ad_id` | str \| None | 광고 ID | `"ad_123"` — 최초 생성 시 `None` |
| `project_id` | str \| None | 프로젝트 ID | `"proj_7"` |

### Node 레벨 (함수별 추가)

| 키 | 적용 도메인 | 설명 | 예 |
|----|-----------|------|----|
| `prompt_version` | 전체 | 프롬프트 버전 | `"v1.2"` |
| `model` | 전체 | 사용 모델 | `"gemini-2.0-flash"` |
| `persona_id` | simulation | 페르소나 식별자 | `"persona_3"` |
| `candidate_idx` | generator | 시안 인덱스 | `0` ~ `4` |
| `retry_count` | simulation | 재시도 횟수 | `0`, `1`, `2` |
| `topic_headline` | simulation | 토론 주제 | `"이 광고는 신뢰를 주는가"` |
| `ls_model_name` | 전체 (LLM) | LangSmith 비용 계산용 모델명 | `"gemini-2.0-flash"` |
| `ls_provider` | 전체 (LLM) | LangSmith 비용 계산용 공급자 | `"google_genai"` |

> **`ls_model_name` / `ls_provider`** 는 LangSmith가 자동 비용 계산에 사용하는 예약 키.  
> LangChain 공식 연동이 없는 SDK(Gemini SDK 직접 호출 등)는 반드시 수동으로 주입해야 한다.

### 빠른 조립 헬퍼 (공통 유틸 권장)

`backend/core/tracing.py` 에 아래 헬퍼를 두고 전 도메인이 import해 쓴다.

```python
# backend/core/tracing.py
# LangSmith RunnableConfig 조립 헬퍼

from langchain_core.runnables import RunnableConfig
from core.config import settings


def make_trace_config(
    *,
    domain: str,
    feature: str,
    mode: str | None = None,
    user_id: str = "anonymous",
    ad_id: str | None = None,
    project_id: str | None = None,
    extra_metadata: dict | None = None,
    extra_tags: list[str] | None = None,
) -> RunnableConfig:
    run_name = f"{domain}.{feature}" + (f".{mode}" if mode else "")
    tags = [domain, feature, settings.APP_ENV] + (extra_tags or [])
    if mode:
        tags.append(mode)

    metadata: dict = {
        "domain": domain,
        "feature": feature,
        "env": settings.APP_ENV,
        "user_id": user_id,
        "ad_id": ad_id,
        "project_id": project_id,
    }
    if mode:
        metadata["mode"] = mode
    if extra_metadata:
        metadata.update(extra_metadata)

    return RunnableConfig(run_name=run_name, tags=tags, metadata=metadata)
```

---

## 5. 필수 Tags

> Tags는 LangSmith 대시보드에서 **필터 Bar**로 직접 선택 가능. 일관성 없으면 필터가 깨진다.

### 표준 Tag 목록

| Tag | 예시값 | 설명 |
|-----|-------|------|
| 도메인 | `generator` `simulation` `management` `tools` | 항상 포함 |
| 기능 | `generate` `simulate` `debate` `regenerate` | 항상 포함 |
| 환경 | `development` `staging` `production` | `APP_ENV` 값 |
| 모드 | `create` `improve` `batch` | 해당할 때만 |
| 특수 | `error` `retry` `fallback` `slow` | 이상 감지 시 추가 |

### 이상 감지 태그 부착 예

```python
from langsmith import get_current_run_tree

async def _qa_with_retry(question: str, max_retry: int = 2):
    for attempt in range(max_retry + 1):
        result = await _call_llm(question)
        if result.is_valid:
            return result
        if attempt > 0:
            run = get_current_run_tree()
            if run:
                run.add_tags(["retry"])
    run = get_current_run_tree()
    if run:
        run.add_tags(["fallback"])
    return fallback_result()
```

---

## 6. 언제 새 Trace를 시작할지

| 상황 | 새 Trace? | 이유 |
|------|----------|------|
| HTTP 요청 1건 | **항상 새 Trace** | 요청 단위가 기본 집계 단위 |
| SSE 스트리밍 중 내부 LLM 호출 | 기존 Trace의 하위 Node | 같은 요청 컨텍스트 |
| SQS 메시지 소비 1건 | **항상 새 Trace** | 비동기 워커도 요청 단위 |
| 백그라운드 배치 (페르소나 N명 병렬) | 상위 1개 Trace + 페르소나별 하위 Node | 부채꼴 구조로 집계 |
| Cron / 스케줄 작업 | **항상 새 Trace** | `tags=["batch"]` 부착 |
| LangGraph `graph.ainvoke()` | **항상 새 Trace** | 그래프 실행 = 요청 1건 |
| LangGraph 내부 노드 실행 | 기존 Trace의 하위 Node | 자동으로 부모 Trace에 묶임 |

### LangGraph 그래프 호출 패턴

```python
# 항상 make_trace_config()로 config를 만들어 ainvoke에 넘긴다.
from core.tracing import make_trace_config

config = make_trace_config(
    domain="generator",
    feature="generate",
    mode="create",
    user_id=str(current_user.id),
    project_id=str(req.project_id),
)
result = await generation_graph.ainvoke(initial_state, config=config)
```

### SQS 워커 패턴

```python
# SQS 메시지마다 새 Trace
from langsmith import traceable

@traceable(
    run_type="chain",
    name="simulation.simulate",
    tags=["simulation", "batch", settings.APP_ENV],
)
async def process_sqs_message(message: dict) -> dict:
    metadata = {
        "domain": "simulation",
        "feature": "simulate",
        "env": settings.APP_ENV,
        "ad_id": message["ad_id"],
        "user_id": message.get("user_id", "system"),
    }
    ...
```

---

## 7. 토큰·비용 누락 방지

LangSmith가 자동으로 토큰을 기록하는 경우와 수동 주입이 필요한 경우를 구분한다.

### 자동 기록되는 경우

| SDK / 방식 | 자동 여부 |
|-----------|----------|
| LangChain `init_chat_model()` | ✅ 자동 |
| `wrap_openai(OpenAI())` | ✅ 자동 |
| `wrap_anthropic(Anthropic())` | ✅ 자동 |
| LangGraph 노드 내 LangChain LLM 호출 | ✅ 자동 |

### 수동 주입이 필요한 경우

| SDK / 방식 | 처리 방법 |
|-----------|----------|
| `google.generativeai` SDK 직접 호출 | `get_current_run_tree()` + `run.set()` |
| `anthropic` SDK (wrap 미적용) | `wrap_anthropic()` 적용 |
| `openai` SDK (wrap 미적용) | `wrap_openai()` 적용 |
| HTTP 직접 호출 | 응답에서 토큰 파싱 후 `run.set()` |

### Gemini SDK 수동 기록 표준 패턴

> 현재 `domain/simulation/adapters/gemini/_common.py` 에 구현된 패턴을 전 도메인이 따른다.

```python
from langsmith import get_current_run_tree

def _record_gemini_usage(resp: Any, model: str) -> None:
    run = get_current_run_tree()
    um = getattr(resp, "usage_metadata", None)
    if run is None or um is None:
        return
    run.set(
        usage_metadata={
            "input_tokens": um.prompt_token_count,
            "output_tokens": um.candidates_token_count,
            "total_tokens": um.total_token_count,
        },
        metadata={
            "ls_model_name": model,        # LangSmith 예약 키 — 비용 계산용
            "ls_provider": "google_genai", # LangSmith 예약 키 — 비용 계산용
        },
    )
```

### 비용 누락 체크 (배포 전 자가 점검)

```bash
# LangSmith 대시보드 → Runs 탭 → 내 최근 실행 선택
# 우측 패널에서 다음 항목 확인:
# - "Total Tokens" 값이 0이거나 없으면 → 수동 기록 누락
# - "Cost" 열이 $0.000이면 → ls_model_name 또는 ls_provider 누락
# - "Latency" 값이 없으면 → Trace가 닫히지 않은 것 (에러 처리 확인)
```

---

## 8. 비용 분석 시 확인할 항목

LangSmith 대시보드 기준으로 팀 전체가 동일한 절차를 따른다.

### 주간 비용 리뷰 (매주 월요일)

**필터 설정**
1. 프로젝트: `clickme`
2. 날짜: 지난 7일
3. Tag 필터로 도메인 분리 (`generator` / `simulation` / `management`)

**확인 항목**

| 항목 | 확인 방법 | 이상 기준 |
|------|---------|---------|
| 도메인별 총 비용 | Tags 그룹핑 → Cost 합계 | 전주 대비 30% 초과 |
| 모델별 토큰 소비 | Model 필터 → Token 합계 | 특정 모델 이상 급증 |
| 평균 지연시간 | Latency 컬럼 평균 | p95 > 30초 |
| 오류율 | Error 필터 | 5% 초과 |
| 재시도 비율 | Tag `retry` 비율 | 10% 초과 |

**LangSmith Charts 활용**

- `Monitor` 탭 → `Cost over time` 차트: 도메인 비교
- `Monitor` 탭 → `Token Usage` 차트: 입력/출력 토큰 비율 (입력이 과도하면 프롬프트 최적화 신호)
- `Runs` 탭 → `Error` 상태 필터: 어떤 노드에서 실패가 집중되는지 확인

### 성능 이상 감지 체크리스트

```
[ ] 전체 Token 합계 확인 (입력:출력 비율 3:1 초과 → 프롬프트 비대화 의심)
[ ] 도메인별 Cost 비교 (특정 도메인 급증 → 해당 도메인 팀에 알림)
[ ] retry Tag 비율 (10% 초과 → LLM 품질 또는 프롬프트 문제)
[ ] Latency p95 (30초 초과 → 병렬화 또는 모델 교체 검토)
[ ] Trace가 Error 상태인 경우 → 스택트레이스 열어 원인 분류
[ ] ls_model_name 없는 Trace 건수 (비용 계산 누락 여부)
[ ] user_id가 "anonymous"인 Trace 비율 (인증 연동 누락 신호)
```

### 비용 최적화 판단 기준

| 신호 | 조치 |
|------|------|
| 입력 토큰이 출력 토큰의 5배 이상 | 시스템 프롬프트 압축, RAG 청크 크기 조정 |
| 특정 Node의 p50 지연 > 10초 | 병렬 실행 또는 경량 모델 대체 검토 |
| retry 비율 > 15% | 프롬프트 구조화 또는 파싱 로직 보강 |
| 동일 광고 반복 Trace | 결과 캐싱 검토 (동일 ad_id 기준) |

---

## 9. 현재 코드베이스 현황 & 개선 체크리스트

### 현황 요약

| 도메인 | `@traceable` 함수 | Trace 이름 표준화 | 필수 Metadata | 비용 기록 |
|--------|-----------------|----------------|--------------|---------|
| generator | 8개 ✅ | ❌ 미적용 | ❌ pipeline만 | ❌ LangChain 자동 |
| simulation | 4개 ✅ | 부분 ✅ | 부분 ✅ | ✅ Gemini 수동 |
| management | 0개 ❌ | ❌ | ❌ | ❌ |
| tools | 4개 ✅ | ❌ 미적용 | ⚠️ version만 | ❌ LangChain 자동 |

### 개선 체크리스트

**즉시 적용 (공통)**

```
[ ] backend/core/tracing.py — make_trace_config() 헬퍼 추가
[ ] generator/service/generator_service.py — graph.ainvoke() 에 make_trace_config() 적용
[ ] simulation/service/*.py — graph.ainvoke() 에 make_trace_config() 적용
[ ] management/agents/regeneration.py — graph.ainvoke() 에 make_trace_config() 적용
```

**generator 도메인**

```
[ ] 각 pipeline/*.py @traceable name을 "generator:{역할}" 형식으로 변경
[ ] metadata에 user_id, ad_id, project_id, candidate_idx 추가
[ ] 개선 모드(improve) 실행 시 mode 태그 분기 처리
```

**simulation 도메인**

```
[ ] reaction_graph.py 노드에 @traceable 또는 RunnableConfig 적용
[ ] 각 페르소나 반응에 persona_id metadata 추가
[ ] retry 발생 시 run.add_tags(["retry"]) 적용
```

**management 도메인**

```
[ ] regeneration.py 전체에 @traceable 또는 graph config 적용
[ ] 최소: graph.ainvoke() 호출에 run_name + tags + metadata 추가
```

**tools**

```
[ ] run_persona_factory, run_exposure, run_deliberation — name을 "tools:{역할}" 형식으로 변경
[ ] metadata에 ad_id, user_id 추가 (상위 호출에서 context propagation)
```

---

## 10. 도메인별 구현 예시

### Generator — 그래프 호출

```python
# domain/generator/service/generator_service.py
from core.tracing import make_trace_config

async def run_generation(req: GenerationRequest, user_id: str) -> GenerationResult:
    config = make_trace_config(
        domain="generator",
        feature="generate",
        mode="improve" if req.base_ad_id else "create",
        user_id=user_id,
        ad_id=str(req.base_ad_id) if req.base_ad_id else None,
        project_id=str(req.project_id),
    )
    return await generation_graph.ainvoke(initial_state, config=config)
```

### Simulation — 배치 실행

```python
# domain/simulation/service/simulation_service.py
from core.tracing import make_trace_config

async def run_simulation(ad_id: str, user_id: str, panel_size: int) -> SimResult:
    config = make_trace_config(
        domain="simulation",
        feature="simulate",
        user_id=user_id,
        ad_id=ad_id,
        extra_metadata={"panel_size": panel_size},
        extra_tags=["batch"] if panel_size > 10 else None,
    )
    return await run_graph.ainvoke(initial_state, config=config)
```

### Simulation — 페르소나 반응 Node

```python
# domain/simulation/graph/nodes/react.py
from langsmith import traceable, get_current_run_tree

@traceable(run_type="chain", name="simulation:persona_react")
async def persona_react_node(state: ReactionState) -> ReactionState:
    run = get_current_run_tree()
    if run:
        run.update(
            metadata={
                "persona_id": state.persona.id,
                "persona_age": state.persona.age,
                "prompt_version": "v1.1",
            }
        )
    ...
```

### Management — 재생성 에이전트

```python
# domain/management/agents/regeneration.py
from core.tracing import make_trace_config

async def regenerate(ad_id: str, user_id: str) -> RegenerationResult:
    config = make_trace_config(
        domain="management",
        feature="regenerate",
        user_id=user_id,
        ad_id=ad_id,
    )
    return await regeneration_graph.ainvoke(initial_state, config=config)
```

### Gemini 직접 호출 — 수동 토큰 기록

```python
# 모든 Gemini SDK 직접 호출 부분에 적용
from langsmith import get_current_run_tree

async def call_gemini(prompt: str, model: str = "gemini-2.0-flash") -> str:
    client = genai.GenerativeModel(model)
    resp = await client.generate_content_async(prompt)
    _record_gemini_usage(resp, model)   # ← 반드시 호출
    return resp.text

def _record_gemini_usage(resp: Any, model: str) -> None:
    run = get_current_run_tree()
    um = getattr(resp, "usage_metadata", None)
    if run is None or um is None:
        return
    run.set(
        usage_metadata={
            "input_tokens": um.prompt_token_count,
            "output_tokens": um.candidates_token_count,
            "total_tokens": um.total_token_count,
        },
        metadata={"ls_model_name": model, "ls_provider": "google_genai"},
    )
```

---

## 참고

- LangSmith 공식 문서: https://docs.smith.langchain.com
- `@traceable` API: https://docs.smith.langchain.com/how_to_guides/tracing/annotate_code
- LangSmith 프로젝트: `clickme` (팀 공용)
- 문의: `#infra` 채널 또는 PR 코멘트
