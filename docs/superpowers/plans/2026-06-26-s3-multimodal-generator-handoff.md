# S3 — 멀티모달 첨부 + generator 잡 핸드오프 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 챗에 제품 사진(s3_key)을 첨부하면 게이트 A로 Planner에 진입해 `generate` 스텝이 실 generator 생성 잡을 **트리거(job start)** 하고, 챗이 진행 구독용 핸드오프 카드(stream_url)를 흘린다.

**Architecture:** S2가 만든 블랙보드(`TurnContext`)·`ask(ctx, step)` 계약·멀티스텝 `execute_plan`·generator 등록 위에, ① 멀티모달 계약(`Attachment`) ② 게이트 A(첨부→generate 보장) ③ generator 실 어댑터(s3→bytes→`start_generation`) ④ executor 단락(`status:"started"`→이후 스텝 미집행) ⑤ 핸드오프 카드 출력 분기를 얹는다. generator 어댑터는 generator 도메인 소유(오케스트레이션 core는 generator를 import하지 않음).

**Tech Stack:** Python 3.12, FastAPI, LangGraph(S2 그래프), pytest(`@pytest.mark.asyncio`), uv. 기존 generator 서비스(`start_generation`/`store_temp_image`)·`tools.storage.s3.download_bytes` 재사용.

---

## ✅ S2 의존 — 실제 시그니처 (코드 확인 완료)

S2는 **구현 완료**(`feat/chat-boeun`에 머지됨). 본 계획은 아래 **실제 S2 시그니처**에 맞춰 작성됐다(추정 아님).

| S2 산출물 | 실제 시그니처/위치 |
|---|---|
| `TurnContext` | `api/orchestration/context.py` — `user_input: str`, `session_id: str=""`, `ad_id: str\|None=None`, `attachments: tuple[Any,...]=()`, `results: dict`, `output_of(action)`. **`remember()` 없음** — 적재는 executor가 `ctx.results[step.id]=out`로 직접. |
| `PlanStep` (+id) | `api/orchestration/plan.py` — `PlanStep(domain, action, inputs, id="")`. `make_plan`이 `id={action}-{n}`(action별 1-based) 부여. `plan_hash`엔 id 비포함. |
| `DomainAgent` | `api/orchestration/contracts.py` — `async def ask(self, ctx, step) -> Any`(Protocol, `Any`). |
| `execute_plan` | `api/orchestration/executor.py` — `async def execute_plan(plan, ctx, *, registry)`. 루프: `with _step_trace(step): out = await agent.ask(ctx, step)` 후 `ctx.results[step.id] = out`. |
| `build_plan` | `api/orchestration/planner.py` — **`build_plan(route, *, query: str) -> Plan`** (ctx 아님, **query만**). 미해석 도메인이면 `ValueError`. 게이트 B: `len(nonzero)>=2 or sequential`. |
| `policy.py` | `api/orchestration/policy.py` — `PIPELINE_ORDER=("generate","simulate")`, `DOMAIN_TO_ACTION`/`ACTION_TO_DOMAIN`(generator→generate, simulation→simulate, management→answer), `SEQUENTIAL_MARKERS`. |
| bootstrap | `GeneratorStubAgent`/`SimulationStubAgent`/`ManagementDomainAgent` 등록(`build_orchestration`). |
| turn | `run_turn(graph, route, *, ctx)`. `plan_node`가 `build_plan(route, query=ctx.user_input)` 호출. |
| chat 통합 | `chat_complete().generate()`가 plan 경로를 **`_should_plan(route, registry) and route.domain == "management"`** 로 제한(gen/sim 렌더는 S3+). `_assistant` 클로저에서 `TurnContext` 생성 후 `run_turn`, `_management_card_stream`으로 렌더. |

**두 가지 핵심 delta(설계 추정과 다름) — 본 계획은 이미 반영:**
1. `build_plan`이 `ctx`가 아니라 `query`만 받는다 → 게이트 A(첨부)는 build_plan에 `attachments` 인자를 추가하고 `turn.py` plan_node도 함께 수정한다(Task 4).
2. chat 경로가 management로 잠겨 있다 → S3가 generator 핸드오프 분기를 **추가**한다(Task 6).

**confirmed generator/storage 사실:** `start_generation(req) -> str`(generation_id, `generator_service.py:57`) · `store_temp_image(data) -> str`(**async**, `generator_service.py:50`) · `download_bytes(key) -> bytes`(**async**, `tools/storage/s3.py:50`).

---

## File Structure

| 파일 | 책임 | 신규/수정 |
|---|---|---|
| `backend/core/schemas.py` | `Attachment` + `ChatRequest.attachments` | 수정 |
| `backend/domain/generator/chat/domain_agent.py` | `GeneratorDomainAgent.ask(ctx, step)` 실 어댑터 | 신규(generator 소유) |
| `backend/api/orchestration/executor.py` | `status:"started"` 단락 규칙 | 수정(S2) |
| `backend/api/orchestration/planner.py` | 게이트 A — 첨부 시 generate 보장 | 수정(S2) |
| `backend/api/routers/chat.py` | `_should_plan(...,has_image)` · ctx.attachments 주입 · 핸드오프 카드 분기 | 수정(S2) |
| `backend/api/orchestration/bootstrap.py` | `GeneratorStubAgent`→`GeneratorDomainAgent` 교체 | 수정(S2) |
| `backend/tests/test_attachments_contract.py` | Attachment 스키마 | 신규 |
| `backend/tests/generator/test_chat_domain_agent.py` | generator 어댑터 | 신규 |
| `backend/tests/orchestration/test_s3_gate_and_handoff.py` | 게이트 A·단락·핸드오프·회귀 | 신규 |

---

## Task 1: 멀티모달 계약 (Attachment + ChatRequest.attachments) — S2 비의존

**Files:**
- Modify: `backend/core/schemas.py`
- Test: `backend/tests/test_attachments_contract.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_attachments_contract.py`:

```python
# ChatRequest.attachments(s3_key) 멀티모달 계약 — append-only, 기본 빈 리스트
from core.schemas import Attachment, ChatRequest


def test_attachment_defaults_to_image_kind():
    a = Attachment(s3_key="uploads/p.png")
    assert a.s3_key == "uploads/p.png"
    assert a.kind == "image"


def test_chat_request_attachments_default_empty():
    req = ChatRequest(session_id="s1", messages=[])
    assert req.attachments == []


def test_chat_request_accepts_attachments():
    req = ChatRequest(
        session_id="s1",
        messages=[],
        attachments=[{"s3_key": "uploads/p.png", "kind": "image"}],
    )
    assert req.attachments[0].s3_key == "uploads/p.png"
    assert req.attachments[0].kind == "image"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_attachments_contract.py -v`
Expected: FAIL (`ImportError: cannot import name 'Attachment'`)

- [ ] **Step 3: Write minimal implementation**

`backend/core/schemas.py` — `ChatMessage` 정의 아래에 `Attachment`를 추가하고, `ChatRequest`에 `attachments` 필드를 더한다(`Literal`은 이미 미사용이면 import 추가). `from typing import Any` 위에 `Literal` 추가:

```python
from typing import Any, Literal
```

`ChatMessage` 클래스 바로 다음에:

```python
class Attachment(BaseModel):
    s3_key: str
    kind: Literal["image"] = "image"
```

`ChatRequest`에 필드 추가(기존 필드 아래, append-only):

```python
class ChatRequest(BaseModel):
    session_id: str
    messages: list[ChatMessage]
    context_ad_id: str | None = None
    context_simulation_id: str | None = None
    improve_context: dict | None = None
    attachments: list[Attachment] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_attachments_contract.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Ruff + Commit**

```bash
cd backend && uv run ruff format core/schemas.py tests/test_attachments_contract.py && uv run ruff check core/schemas.py tests/test_attachments_contract.py --fix
git add backend/core/schemas.py backend/tests/test_attachments_contract.py
git commit -m "add: ChatRequest.attachments(s3_key) 멀티모달 계약 — S3"
```

---

## Task 2: generator 실 어댑터 (s3→bytes→start_generation 핸드오프) — S2 `ask(ctx, step)` 계약 전제

어댑터는 ctx/step을 **덕타이핑**(속성 접근)으로만 쓰므로 S2 타입을 import하지 않고 단독 테스트가 가능하다. 단 **`ask(ctx, step)` 계약 자체는 S2 산출물**이므로, S2가 계약을 바꾸면 어댑터 시그니처도 맞춘다.

**Files:**
- Create: `backend/domain/generator/chat/domain_agent.py`
- Test: `backend/tests/generator/test_chat_domain_agent.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/generator/test_chat_domain_agent.py`:

```python
# generator 챗 어댑터 — s3_key→bytes→start_generation 트리거, started 핸드오프 반환
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

import domain.generator.chat.domain_agent as mod
from domain.generator.chat.domain_agent import GeneratorDomainAgent


@dataclass
class _Ctx:
    user_input: str
    attachments: tuple = ()
    results: dict = field(default_factory=dict)


def _step(action="generate", domain="generator", idx=1, inputs=None):
    return SimpleNamespace(
        id=f"{action}-{idx}", action=action, domain=domain, inputs=inputs or {}
    )


@pytest.mark.asyncio
async def test_triggers_generation_and_returns_handoff(monkeypatch):
    seen = {}

    async def _fake_download(key):
        seen["downloaded"] = key
        return b"IMGBYTES"

    async def _fake_store(data):
        seen["stored"] = data
        return "temp-key-1"

    async def _fake_start(req):
        seen["req"] = req
        return "gen-123"

    monkeypatch.setattr(mod, "download_bytes", _fake_download)
    monkeypatch.setattr(mod, "store_temp_image", _fake_store)
    monkeypatch.setattr(mod, "start_generation", _fake_start)

    agent = GeneratorDomainAgent()
    ctx = _Ctx(user_input="이 텀블러로 광고 만들어줘", attachments=(
        SimpleNamespace(kind="image", s3_key="uploads/p.png"),
    ))
    out = await agent.ask(ctx, _step())

    assert seen["downloaded"] == "uploads/p.png"
    assert seen["stored"] == b"IMGBYTES"
    assert seen["req"].product_image_temp_key == "temp-key-1"
    assert seen["req"].product_description == "이 텀블러로 광고 만들어줘"
    assert seen["req"].target_audience == "전체"
    assert out == {
        "status": "started",
        "step_id": "generate-1",
        "domain": "generator",
        "action": "generate",
        "task_id": "gen-123",
        "stream_url": "/api/generator/generations/gen-123/stream",
        "ad_id": None,
    }


@pytest.mark.asyncio
async def test_no_attachment_skips_download(monkeypatch):
    async def _fail_download(key):  # 호출되면 실패
        raise AssertionError("download_bytes는 첨부 없으면 호출되면 안 됨")

    async def _fake_start(req):
        return "gen-9"

    monkeypatch.setattr(mod, "download_bytes", _fail_download)
    monkeypatch.setattr(mod, "start_generation", _fake_start)

    agent = GeneratorDomainAgent()
    out = await agent.ask(_Ctx(user_input="광고 만들어줘"), _step())
    assert out["task_id"] == "gen-9"
    assert out["status"] == "started"


@pytest.mark.asyncio
async def test_step_inputs_query_takes_priority_over_user_input(monkeypatch):
    seen = {}

    async def _fake_start(req):
        seen["req"] = req
        return "gen-2"

    monkeypatch.setattr(mod, "start_generation", _fake_start)

    agent = GeneratorDomainAgent()
    ctx = _Ctx(user_input="대화 전체 맥락")
    await agent.ask(ctx, _step(inputs={"query": "스텝 지정 설명"}))
    assert seen["req"].product_description == "스텝 지정 설명"  # step.inputs 우선
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/generator/test_chat_domain_agent.py -v`
Expected: FAIL (`ModuleNotFoundError: domain.generator.chat.domain_agent`)

- [ ] **Step 3: Write minimal implementation**

`backend/domain/generator/chat/domain_agent.py`:

```python
# 챗 오케스트레이터용 generator 도메인 에이전트 — 이미지로 생성 잡을 트리거하고 핸드오프 반환
from __future__ import annotations

from domain.generator.contracts.enums import GenerationMode
from domain.generator.contracts.schemas import GenerationCreateRequest
from domain.generator.service.generator_service import start_generation, store_temp_image
from tools.storage.s3 import download_bytes

_DEFAULT_TARGET = "전체"


def _first_image_key(attachments) -> str | None:
    for a in attachments:
        if getattr(a, "kind", None) == "image" and getattr(a, "s3_key", None):
            return a.s3_key
    return None


def _derive_product_name(user_input: str) -> str:
    text = (user_input or "").strip()
    return text[:40] if text else "상품"


class GeneratorDomainAgent:
    """챗 계약 ask(ctx, step) — ctx.attachments의 이미지로 실 생성 잡을 시작(job start까지만)."""

    domain = "generator"

    async def ask(self, ctx, step):
        s3_key = _first_image_key(ctx.attachments)
        temp_key = None
        if s3_key:
            data = await download_bytes(s3_key)
            temp_key = await store_temp_image(data)
        # step.inputs.query 우선(Planner가 스텝별로 지정한 값) → 없으면 ctx.user_input → 기본
        desc = (step.inputs.get("query") or ctx.user_input or "").strip() or "상품 광고"
        req = GenerationCreateRequest(
            mode=GenerationMode.CREATE,
            product_description=desc,
            product_name=_derive_product_name(ctx.user_input),
            target_audience=_DEFAULT_TARGET,
            product_image_temp_key=temp_key,
        )
        generation_id = await start_generation(req)
        return {
            "status": "started",
            "step_id": step.id,
            "domain": step.domain,
            "action": step.action,
            "task_id": generation_id,
            "stream_url": f"/api/generator/generations/{generation_id}/stream",
            "ad_id": None,
        }
```

`backend/domain/generator/chat/__init__.py`가 없으면 빈 파일 생성(패키지). 이미 있으면 건너뛴다.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/generator/test_chat_domain_agent.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Ruff + Commit**

```bash
cd backend && uv run ruff format domain/generator/chat/domain_agent.py tests/generator/test_chat_domain_agent.py && uv run ruff check domain/generator/chat/domain_agent.py tests/generator/test_chat_domain_agent.py --fix
git add backend/domain/generator/chat/domain_agent.py backend/tests/generator/test_chat_domain_agent.py
git commit -m "add: generator 챗 어댑터(s3→start_generation 핸드오프) — S3"
```

---

## Task 3: executor 단락 — status:"started" 핸드오프

S2 멀티스텝 `execute_plan`(executor.py)에 단락 규칙을 더한다 — 스텝이 `status:"started"`를 반환하면 이후 스텝을 집행하지 않고 그 핸드오프를 반환.

**Files:**
- Modify: `backend/api/orchestration/executor.py`
- Test: `backend/tests/orchestration/test_s3_gate_and_handoff.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/orchestration/test_s3_gate_and_handoff.py` (신규 — 이 파일은 Task 3·4·5(통합)에서 함께 쓴다):

```python
# S3 — executor 단락 / 게이트 A / 핸드오프. S2 멀티스텝 execute_plan·build_plan·TurnContext 전제.
from dataclasses import dataclass, field

import pytest

from api.orchestration.context import TurnContext
from api.orchestration.executor import execute_plan
from api.orchestration.plan import PlanStep, make_plan
from api.orchestration.registry import AgentRegistry


class _StartedAgent:
    domain = "generator"

    async def ask(self, ctx, step):
        return {"status": "started", "step_id": step.id, "task_id": "gen-1"}


class _SpyAgent:
    domain = "simulation"

    def __init__(self):
        self.calls = 0

    async def ask(self, ctx, step):
        self.calls += 1
        return {"simulation_id": "sim-1"}


@pytest.mark.asyncio
async def test_executor_short_circuits_on_started():
    spy = _SpyAgent()
    registry = AgentRegistry()
    registry.register(_StartedAgent())
    registry.register(spy)
    plan = make_plan(
        [
            PlanStep(domain="generator", action="generate", inputs={}),
            PlanStep(domain="simulation", action="simulate", inputs={}),
        ]
    )
    ctx = TurnContext(user_input="시안 만들고 시뮬 돌려줘")

    out = await execute_plan(plan, ctx, registry=registry)

    assert out["status"] == "started"
    assert spy.calls == 0  # generate started → simulate 미집행 (S3 한계 가드)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/orchestration/test_s3_gate_and_handoff.py::test_executor_short_circuits_on_started -v`
Expected: FAIL — S2 `execute_plan`은 단락 없이 simulate까지 호출해 `spy.calls == 1`.

- [ ] **Step 3: Write minimal implementation**

`backend/api/orchestration/executor.py` 루프의 `ctx.results[step.id] = out`(executor.py:42) **직후**에 단락 분기를 추가한다(실제 S2 executor는 `with _step_trace(step):` 블록 안에서 `ask`, 적재는 블록 밖):

```python
        with _step_trace(step):  # 기존 S2
            out = await agent.ask(ctx, step)
        ctx.results[step.id] = out  # 기존 S2 — 블랙보드 누적
        if isinstance(out, dict) and out.get("status") == "started":
            return out  # 비동기 핸드오프 — 이후 스텝 미집행, 턴 종결(S3)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/orchestration/test_s3_gate_and_handoff.py::test_executor_short_circuits_on_started -v`
Expected: PASS

- [ ] **Step 5: Ruff + Commit**

```bash
cd backend && uv run ruff format api/orchestration/executor.py tests/orchestration/test_s3_gate_and_handoff.py && uv run ruff check api/orchestration/executor.py tests/orchestration/test_s3_gate_and_handoff.py --fix
git add backend/api/orchestration/executor.py backend/tests/orchestration/test_s3_gate_and_handoff.py
git commit -m "edit: executor 단락(started 핸드오프 시 이후 스텝 미집행) — S3"
```

---

## Task 4: 게이트 A — 첨부 시 generate 보장 (build_plan + turn.py)

실제 `build_plan(route, *, query)`는 attachments를 받지 않는다. 게이트 A를 위해 **build_plan에 `attachments` 인자를 추가**하고, **`turn.py` plan_node가 `ctx.attachments`를 넘기도록** 함께 수정한다. 첨부 이미지가 있으면 generator를 도메인 집합에 넣고, 단일 fallback도 generator 우선으로 한다(미해석 도메인이라도 첨부가 있으면 `[generate]`).

**Files:**
- Modify: `backend/api/orchestration/planner.py`, `backend/api/orchestration/turn.py`
- Test: `backend/tests/orchestration/test_s3_gate_and_handoff.py` (Task 3 파일에 추가)

- [ ] **Step 1: Write the failing test**

Task 3 테스트 파일 상단(import 아래)에 헬퍼 추가:

```python
@dataclass
class _Img:
    s3_key: str
    kind: str = "image"
```

테스트 파일 끝에 추가:

```python
from api.orchestration.planner import build_plan
from api.orchestration.routing import KeywordMatcher, Router


def _has_action(plan, action):
    return any(s.action == action for s in plan.steps)


def test_gate_a_attachment_forces_generate_step():
    # "봐줄래"는 어떤 도메인 키워드도 아님 → route.domain=clio, score 0.
    # 그래도 첨부 이미지가 있으면 generate 스텝이 들어간다(게이트 A).
    route = Router([KeywordMatcher("management", frozenset({"캠페인"}))]).route("이거 좀 봐줄래")
    plan = build_plan(route, query="이거 좀 봐줄래", attachments=(_Img("uploads/p.png"),))
    assert _has_action(plan, "generate")


def test_no_attachment_keeps_single_resolved_domain():
    # 첨부 없고 management만 해석 → 기존 단일 answer 스텝(회귀 0)
    route = Router([KeywordMatcher("management", frozenset({"캠페인"}))]).route("이번 캠페인 예산?")
    plan = build_plan(route, query="이번 캠페인 예산?")
    assert [s.action for s in plan.steps] == ["answer"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/orchestration/test_s3_gate_and_handoff.py::test_gate_a_attachment_forces_generate_step -v`
Expected: FAIL — 현재 `build_plan`엔 `attachments` 인자가 없어 `TypeError`(또는 clio 라우트에 `ValueError`).

- [ ] **Step 3: Write minimal implementation**

(a) `backend/api/orchestration/planner.py` — `build_plan` 전체를 아래로 교체(게이트 A + attachments 인자):

```python
def _has_image_attachment(attachments) -> bool:
    return any(getattr(a, "kind", None) == "image" for a in attachments)


def build_plan(route: RouteDecision, *, query: str, attachments: tuple = ()) -> Plan:
    has_image = _has_image_attachment(attachments)
    nonzero = {c.domain for c in route.candidates if c.score > 0.0}
    if has_image:
        nonzero.add("generator")  # 게이트 A — 첨부 이미지 → generate 보장
    if not nonzero:
        # 미해석 도메인 & 첨부 없음 — 호출 전 _should_plan 가드 필요(fail-loud)
        raise ValueError(
            f"build_plan: 미해석 도메인({route.domain})·첨부 없음 — _should_plan 가드 필요"
        )

    sequential = any(marker in query for marker in policy.SEQUENTIAL_MARKERS)
    if len(nonzero) >= 2 or sequential:  # 게이트 B 진입
        steps = [
            PlanStep(domain=policy.ACTION_TO_DOMAIN[action], action=action, inputs={"query": query})
            for action in policy.PIPELINE_ORDER
            if policy.ACTION_TO_DOMAIN[action] in nonzero
        ]
        if len(steps) >= 2:  # 파이프라인 도메인 2개+ 매칭 시에만 멀티스텝
            return make_plan(steps)
        # 게이트 B지만 매칭 <2 → 아래 단일 fallback

    # 단일 스텝 — 첨부 있으면 generator 우선(generate), 아니면 해석된 route.domain
    single = "generator" if has_image else route.domain
    step = PlanStep(domain=single, action=policy.DOMAIN_TO_ACTION[single], inputs={"query": query})
    return make_plan([step])
```

(b) `backend/api/orchestration/turn.py` — `plan_node`가 attachments를 넘기도록 수정:

```python
    async def plan_node(state: TurnState) -> dict:
        ctx = state["ctx"]
        return {"plan": build_plan(state["route"], query=ctx.user_input, attachments=ctx.attachments)}
```

- [ ] **Step 4: Run test to verify it passes (+ 기존 planner 회귀)**

Run: `cd backend && uv run pytest tests/orchestration/test_s3_gate_and_handoff.py -k "gate_a or no_attachment_keeps" tests/orchestration/test_planner.py -v`
Expected: PASS — `attachments` 기본값 `()`라 기존 `build_plan(route, query=...)` 호출(test_planner.py)은 무파손.

- [ ] **Step 5: Ruff + Commit**

```bash
cd backend && uv run ruff format api/orchestration/planner.py api/orchestration/turn.py tests/orchestration/test_s3_gate_and_handoff.py && uv run ruff check api/orchestration/planner.py api/orchestration/turn.py tests/orchestration/test_s3_gate_and_handoff.py --fix
git add backend/api/orchestration/planner.py backend/api/orchestration/turn.py tests/orchestration/test_s3_gate_and_handoff.py
git commit -m "edit: 게이트 A(첨부→generate 보장, build_plan attachments 인자 + turn.py) — S3"
```

---

## Task 5: bootstrap 등록 교체 (GeneratorStubAgent → GeneratorDomainAgent)

**Files:**
- Modify: `backend/api/orchestration/bootstrap.py`
- Test: `backend/tests/orchestration/test_s3_gate_and_handoff.py` (추가)

- [ ] **Step 1: Write the failing test**

테스트 파일에 추가:

```python
def test_bootstrap_registers_real_generator_agent():
    from api.orchestration.bootstrap import build_orchestration
    from domain.generator.chat.domain_agent import GeneratorDomainAgent

    _, registry = build_orchestration(settings=object())
    agent = registry.get("generator")
    assert isinstance(agent, GeneratorDomainAgent)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/orchestration/test_s3_gate_and_handoff.py::test_bootstrap_registers_real_generator_agent -v`
Expected: FAIL — S2는 `GeneratorStubAgent`를 등록.

- [ ] **Step 3: Write minimal implementation**

`backend/api/orchestration/bootstrap.py`에서 generator 등록을 스텁 → 실 어댑터로 교체:

```python
from domain.generator.chat.domain_agent import GeneratorDomainAgent  # 상단 import

# build_orchestration 내부 — GeneratorStubAgent() 등록 줄을 교체:
registry.register(GeneratorDomainAgent())
```

`GeneratorStubAgent` import·정의가 더 이상 안 쓰이면 제거(simulation 스텁은 유지).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/orchestration/test_s3_gate_and_handoff.py::test_bootstrap_registers_real_generator_agent -v`
Expected: PASS

- [ ] **Step 5: Ruff + Commit**

```bash
cd backend && uv run ruff format api/orchestration/bootstrap.py tests/orchestration/test_s3_gate_and_handoff.py && uv run ruff check api/orchestration/bootstrap.py tests/orchestration/test_s3_gate_and_handoff.py --fix
git add backend/api/orchestration/bootstrap.py tests/orchestration/test_s3_gate_and_handoff.py
git commit -m "edit: bootstrap에 generator 실 어댑터 등록(스텁 교체) — S3"
```

---

## Task 6: chat 게이트 A 진입 + ctx.attachments 주입 + 핸드오프 카드 분기

`chat.py` `generate()`에서 ① `_should_plan`에 첨부 신호 추가 ② management 분기에 `and not has_image` ③ generator 핸드오프 분기 추가(`TurnContext`에 `attachments` 주입, `status:"started"`면 핸드오프 카드 SSE). 실제 S2 `generate()` 블록(management 잠금)을 아래 Step 3(c)대로 교체한다.

**Files:**
- Modify: `backend/api/routers/chat.py`
- Test: `backend/tests/orchestration/test_s3_gate_and_handoff.py` (추가)

- [ ] **Step 1: Write the failing test**

테스트 파일에 추가(순수 함수 단위 — 전체 SSE 대신 게이트·카드 헬퍼를 검증):

```python
def test_should_plan_true_when_image_attachment(monkeypatch):
    import api.routers.chat as chat
    from api.orchestration.registry import AgentRegistry
    from api.orchestration.routing import KeywordMatcher, Router

    router = Router([KeywordMatcher("management", frozenset({"캠페인"}))])
    registry = AgentRegistry()
    registry.register(_StartedAgent())  # domain="generator"
    monkeypatch.setattr(chat, "_orchestration", (router, registry))

    route = router.route("이거 좀 봐줄래")  # 키워드 없음 → score 0
    assert chat._should_plan(route, registry, has_image=True) is True
    assert chat._should_plan(route, registry, has_image=False) is False


def test_handoff_card_events_contain_stream_url():
    import api.routers.chat as chat

    handoff = {
        "status": "started",
        "task_id": "gen-1",
        "stream_url": "/api/generator/generations/gen-1/stream",
    }
    chunks = list(chat._handoff_card_events(handoff))
    joined = "".join(chunks)
    assert "gen-1" in joined
    assert "/api/generator/generations/gen-1/stream" in joined
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/orchestration/test_s3_gate_and_handoff.py -k "should_plan_true_when_image or handoff_card" -v`
Expected: FAIL (`_should_plan`에 `has_image` 인자 없음 · `_handoff_card_events` 미정의).

- [ ] **Step 3: Write minimal implementation**

`backend/api/routers/chat.py`:

(a) `_should_plan` 시그니처 확장:

```python
def _should_plan(route: RouteDecision, registry: AgentRegistry, *, has_image: bool = False) -> bool:
    # 첨부 이미지가 있으면(에픽 §3 A 우선) generator 등록 시 Plan 경로. 아니면 도메인 해석 기준.
    if has_image and registry.get("generator") is not None:
        return True
    return route.score > 0.0 and registry.get(route.domain) is not None
```

(b) 핸드오프 카드 이벤트 헬퍼 추가 — **기존 카드 SSE와 동일 envelope를 써야 FE 호환이 깨지지 않는다.**
chat.py가 이미 import한 `format_sse`(`domain.management.assistant.composer`)로 이벤트를 감싼다(원시 `data: {...}`
직접 덤프 금지). 착수 시 **FE가 기대하는 카드 SSE 스키마(`kind`/envelope/종결 이벤트)를 실제 `compose_card`·
`stream_card` 출력과 대조**해 필드명을 맞춘다:

```python
def _handoff_card_events(handoff: dict):
    # generator 비동기 핸드오프 → "시안 생성 시작" 카드. 기존 카드 envelope(format_sse) 재사용.
    yield format_sse(
        {
            "kind": "handoff",
            "message": "시안 생성을 시작했어요. 진행 상황을 보여드릴게요.",
            "task_id": handoff.get("task_id"),
            "stream_url": handoff.get("stream_url"),
        }
    )
    yield format_sse({"kind": "final", "status": "started"})
```

> reconcile — FE 카드 렌더러가 `kind:"handoff"`를 모르면 ① FE에 핸드오프 섹션 추가 또는 ② 기존 카드
> 타입(예: 안내 텍스트 카드)으로 매핑. 종결 이벤트(`final`/`done`) 형태도 기존 스트림과 일치시킨다.

(c) `generate()` 내부 — 실제 S2 plan 경로는 `route.domain == "management"`로 잠겨 있다. **management 분기는 유지(회귀 0)** 하되 첨부 시 양보하도록 `and not has_image`를 더하고, 그 뒤·CLIO 앞에 generator 핸드오프 분기를 추가한다. 기존 블록(chat.py:204-226)을 아래로 교체:

```python
        router, registry = _get_orchestration()
        route = router.route(last_message)
        has_image = any(getattr(a, "kind", None) == "image" for a in body.attachments)

        # management 단일: 기존 카드 경로(회귀 0). 첨부가 있으면 generator로 양보.
        if _should_plan(route, registry) and route.domain == "management" and not has_image:
            graph = _get_orchestrator_graph()

            async def _assistant(req: AskRequest) -> AskResult:
                ctx = TurnContext(
                    user_input=req.question,
                    session_id=body.session_id,
                    ad_id=req.ad_id,
                )
                return await run_turn(graph, route, ctx=ctx)

            async for chunk in _management_card_stream(
                question=last_message,
                session_id=body.session_id,
                ad_id=body.context_ad_id,
                assistant=_assistant,
                record=_record_management_turn,
            ):
                yield chunk
            return

        # generator 핸드오프: 첨부 이미지 또는 generator 라우팅 → 비동기 잡 트리거(S3)
        if _should_plan(route, registry, has_image=has_image) and (
            has_image or route.domain == "generator"
        ):
            graph = _get_orchestrator_graph()
            ctx = TurnContext(
                user_input=last_message,
                session_id=body.session_id,
                ad_id=body.context_ad_id,
                attachments=tuple(body.attachments),
            )
            result = await run_turn(graph, route, ctx=ctx)
            if isinstance(result, dict) and result.get("status") == "started":
                for ev in _handoff_card_events(result):
                    yield ev
                return
            # 방어 — generator인데 핸드오프가 아니면(예상 밖) 아래 CLIO로 폴백
```

(이후 기존 CLIO 블록 `async for chunk in _clio_stream(...)`이 그대로 이어진다.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/orchestration/test_s3_gate_and_handoff.py -k "should_plan_true_when_image or handoff_card" -v`
Expected: PASS

- [ ] **Step 5: Ruff + Commit**

```bash
cd backend && uv run ruff format api/routers/chat.py tests/orchestration/test_s3_gate_and_handoff.py && uv run ruff check api/routers/chat.py tests/orchestration/test_s3_gate_and_handoff.py --fix
git add backend/api/routers/chat.py tests/orchestration/test_s3_gate_and_handoff.py
git commit -m "edit: 챗 게이트 A 진입·attachments 주입·핸드오프 카드 분기 — S3"
```

---

## Task 7: 회귀 + import 순수성 확인

- [ ] **Step 1: 전체 관련 스위트 실행**

Run: `cd backend && uv run pytest tests/orchestration/ tests/generator/ tests/management/ tests/test_attachments_contract.py -v`
Expected: PASS — management 단일·S2 멀티스텝 스텁 경로 회귀 0, S3 신규 테스트 통과.

- [ ] **Step 2: import 순수성**

`backend/tests/orchestration/test_import_purity.py`의 `_CORE`(plan/planner/executor/turn 등)가 `domain.generator`도 import하지 않음을 확인. 필요 시 `_FORBIDDEN`을 `("domain.management", "domain.generator", "domain.simulation")` 다중으로 확장하는 별도 테스트를 추가하고 통과 확인.

Run: `cd backend && uv run pytest tests/orchestration/test_import_purity.py -v`
Expected: PASS (core가 어떤 domain.*도 직접 import 안 함 — 어댑터는 generator 소유·bootstrap 등록만).

- [ ] **Step 3: 실패 시**

`systematic-debugging` 스킬로 전체 에러·스택 확인 후 원인 수정.

---

## Self-Review (작성자 체크)

- **스펙 커버리지** — 설계 §2(계약)=Task1, §4(generator 어댑터)=Task2, §5 단락=Task3, §3 게이트 A=Task4·6, bootstrap=Task5, 핸드오프 카드=Task6, §7 테스트(특히 §7-5 simulate 미집행)=Task3, 회귀·순수성=Task7. "job start만 보장"은 어댑터가 `start_generation` 트리거 후 즉시 핸드오프 반환(완료 await 없음)으로 충족.
- **Placeholder** — S2·generator·storage 시그니처 **전부 실제 코드 확인 완료**(추정/은폐 TBD 없음). 모든 Task가 구체 코드.
- **타입 정합** — 핸드오프 dict 키(`status/step_id/domain/action/task_id/stream_url/ad_id`)가 Task2(생성)·Task3(단락 판정 `status`)·Task6(카드 `task_id/stream_url`)에서 일관. `build_plan(route, *, query, attachments)`·`_should_plan(route, registry, *, has_image)`·`_handoff_card_events(handoff)`·`GeneratorDomainAgent.ask(ctx, step)` 시그니처가 실제 S2와 정합.
- **실 S2 정합(2 delta 반영)** — ① `build_plan`이 `query`만 받으므로 attachments 인자 추가 + `turn.py` plan_node 동반 수정(Task4). ② chat plan 경로가 `route.domain=="management"`로 잠겨 있으므로 management 분기 유지+`not has_image`, generator 핸드오프 분기 신설(Task6). `TurnContext`는 `remember()` 없이 `ctx.results` 직접 적재(Task3).
