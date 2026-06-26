# S3 — 멀티모달 첨부 + generator 잡 핸드오프 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 챗에 제품 사진(s3_key)을 첨부하면 게이트 A로 Planner에 진입해 `generate` 스텝이 실 generator 생성 잡을 **트리거(job start)** 하고, 챗이 진행 구독용 핸드오프 카드(stream_url)를 흘린다.

**Architecture:** S2가 만든 블랙보드(`TurnContext`)·`ask(ctx, step)` 계약·멀티스텝 `execute_plan`·generator 등록 위에, ① 멀티모달 계약(`Attachment`) ② 게이트 A(첨부→generate 보장) ③ generator 실 어댑터(s3→bytes→`start_generation`) ④ executor 단락(`status:"started"`→이후 스텝 미집행) ⑤ 핸드오프 카드 출력 분기를 얹는다. generator 어댑터는 generator 도메인 소유(오케스트레이션 core는 generator를 import하지 않음).

**Tech Stack:** Python 3.12, FastAPI, LangGraph(S2 그래프), pytest(`@pytest.mark.asyncio`), uv. 기존 generator 서비스(`start_generation`/`store_temp_image`)·`tools.storage.s3.download_bytes` 재사용.

---

## ⚠️ Precondition & Reconciliation (필독)

본 계획은 **S2 구현 완료를 전제**한다(`2026-06-26-s2-multistep-orchestration-design.md`). S2가 코드로 없으면 Task 2·3·4·6·7은 실행 불가다. S2가 제공한다고 가정하는 산출물·시그니처(이게 다르면 **착수 시점에 실제 코드로 맞춰 reconcile** 후 진행):

| S2 산출물 | 가정 시그니처/위치 |
|---|---|
| `TurnContext` | `api/orchestration/context.py` — `user_input: str`, `attachments: tuple[Any,...]`, `results: dict[str,Any]`, `output_of(action)` |
| `PlanStep` (+id) | `api/orchestration/plan.py` — `PlanStep(domain, action, inputs)` + `.id`(`{action}-{n}`) |
| `DomainAgent` | `api/orchestration/contracts.py` — `async def ask(self, ctx, step) -> Any` |
| `execute_plan` | `api/orchestration/executor.py` — `async def execute_plan(plan, ctx, *, registry)` 멀티스텝 순차 |
| `build_plan` | `api/orchestration/planner.py` — `build_plan(route, ctx) -> Plan` |
| `policy.py` | `api/orchestration/policy.py` — `PIPELINE_ORDER`, `DOMAIN_TO_ACTION`, `SEQUENTIAL_MARKERS` |
| bootstrap | `GeneratorStubAgent`/`SimulationStubAgent` 등록 |
| chat 통합 | `chat.py`가 `TurnContext`를 만들어 `run_turn(graph, route, ctx)` 호출, 결과를 카드로 스트림 |

> Task 1·5는 **S2 비의존**(전송 스키마 / generator 도메인)이라 먼저 단독 실행 가능. Task 2·3·4·6·7은 S2 위에서만.

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

## Task 2: generator 실 어댑터 (s3→bytes→start_generation 핸드오프) — S2 비의존(계약만 덕타이핑)

`ask(ctx, step)`는 S2 계약이지만 어댑터는 ctx/step을 **덕타이핑**(속성 접근)으로만 쓰므로 S2 타입 import 없이 단독 구현·테스트 가능하다.

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
        desc = (ctx.user_input or step.inputs.get("query") or "").strip() or "상품 광고"
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
Expected: PASS (2 passed)

- [ ] **Step 5: Ruff + Commit**

```bash
cd backend && uv run ruff format domain/generator/chat/domain_agent.py tests/generator/test_chat_domain_agent.py && uv run ruff check domain/generator/chat/domain_agent.py tests/generator/test_chat_domain_agent.py --fix
git add backend/domain/generator/chat/domain_agent.py backend/tests/generator/test_chat_domain_agent.py
git commit -m "add: generator 챗 어댑터(s3→start_generation 핸드오프) — S3"
```

---

## Task 3: executor 단락 — status:"started" 핸드오프 (S2 의존)

S2의 멀티스텝 `execute_plan`에 단락 규칙을 더한다. **착수 시 실제 S2 `execute_plan` 본문에 맞춰 삽입 위치 reconcile.**

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

`backend/api/orchestration/executor.py`의 S2 루프에서 `ctx.results[step.id] = out` **직후**에 단락 분기를 추가한다(루프 본문):

```python
        out = await agent.ask(ctx, step)
        ctx.results[step.id] = out
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

## Task 4: 게이트 A — 첨부 시 generate 보장 (S2 의존)

S2 `build_plan(route, ctx)`에서 **첨부 이미지가 있으면 generator를 도메인 집합에 포함**해 `generate` 스텝을 보장한다.

**Files:**
- Modify: `backend/api/orchestration/planner.py`
- Test: `backend/tests/orchestration/test_s3_gate_and_handoff.py` (Task 3 파일에 추가)

- [ ] **Step 1: Write the failing test**

Task 3의 테스트 파일 끝에 추가:

```python
from api.orchestration.planner import build_plan
from api.orchestration.routing import KeywordMatcher, Router


def _has_action(plan, action):
    return any(s.action == action for s in plan.steps)


def test_gate_a_attachment_forces_generate_step():
    # 키워드 score 0(도메인 미해석)이라도 첨부가 있으면 generate 스텝이 들어간다
    route = Router([KeywordMatcher("management", frozenset({"캠페인"}))]).route("이걸로 만들어줘")
    ctx = TurnContext(
        user_input="이걸로 만들어줘",
        attachments=(_Img("uploads/p.png"),),
    )
    plan = build_plan(route, ctx)
    assert _has_action(plan, "generate")
```

같은 파일 상단(import 아래)에 헬퍼 추가:

```python
@dataclass
class _Img:
    s3_key: str
    kind: str = "image"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/orchestration/test_s3_gate_and_handoff.py::test_gate_a_attachment_forces_generate_step -v`
Expected: FAIL — S2 build_plan은 첨부를 안 보므로 generate 스텝 없음(management 단일).

- [ ] **Step 3: Write minimal implementation**

`backend/api/orchestration/planner.py`에 헬퍼를 추가하고, `build_plan`에서 도메인 집합을 만든 직후 첨부면 generator를 더한다(S2 build_plan의 `nonzero` 도메인 집합 산출 지점에 reconcile):

```python
def _has_image_attachment(attachments) -> bool:
    return any(getattr(a, "kind", None) == "image" for a in attachments)
```

S2 `build_plan` 내부, nonzero 도메인 집합(`domains`)을 만든 직후:

```python
    domains = {c.domain for c in route.candidates if c.score > 0}
    if _has_image_attachment(ctx.attachments):
        domains.add("generator")  # 게이트 A — 첨부 이미지 → generate 보장
    # 이하 S2 로직: PIPELINE_ORDER ∩ domains 로 스텝 구성 …
```

> S2 `build_plan`이 멀티스텝을 `len(domains 매칭) >= 2`일 때만 만든다면, generator 단독(domains={generator})은 단일 `[generate]`로 나와야 한다 — S2 단일 fallback 경로가 `route.domain` 기준이면, **첨부 단독 시 generate 단일 스텝**을 반환하도록 fallback도 generator 우선으로 reconcile(첨부가 있으면 단일 스텝 도메인 = generator).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/orchestration/test_s3_gate_and_handoff.py::test_gate_a_attachment_forces_generate_step -v`
Expected: PASS

- [ ] **Step 5: Ruff + Commit**

```bash
cd backend && uv run ruff format api/orchestration/planner.py tests/orchestration/test_s3_gate_and_handoff.py && uv run ruff check api/orchestration/planner.py tests/orchestration/test_s3_gate_and_handoff.py --fix
git add backend/api/orchestration/planner.py tests/orchestration/test_s3_gate_and_handoff.py
git commit -m "edit: 게이트 A(첨부 이미지→generate 스텝 보장) — S3"
```

---

## Task 5: bootstrap 등록 교체 (S2 스텁 → 실 어댑터) (S2 의존)

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

## Task 6: chat 게이트 A 진입 + ctx.attachments 주입 + 핸드오프 카드 분기 (S2 의존)

`chat.py`에서 ① `_should_plan`에 첨부 신호 추가 ② `TurnContext`에 `attachments` 주입 ③ run_turn 결과가 `status:"started"` 핸드오프면 핸드오프 카드 SSE. **S2의 실제 chat 통합(ctx 생성·run_turn 호출·카드 스트림)에 맞춰 reconcile.**

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

    route = router.route("이걸로 만들어줘")  # score 0
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

(b) 핸드오프 카드 이벤트 헬퍼 추가:

```python
def _handoff_card_events(handoff: dict):
    # generator 비동기 핸드오프 → "시안 생성 시작" 카드 SSE(FE가 stream_url 구독)
    meta = {
        "kind": "handoff",
        "message": "시안 생성을 시작했어요. 진행 상황을 보여드릴게요.",
        "task_id": handoff.get("task_id"),
        "stream_url": handoff.get("stream_url"),
    }
    yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
    yield 'data: {"done": true}\n\n'
```

(c) `generate()` 내부 plan 경로(S2)에서 — `has_image = any(a.kind == "image" for a in body.attachments)`로 `_should_plan(route, registry, has_image=has_image)` 호출, `TurnContext` 생성 시 `attachments=tuple(body.attachments)` 주입, run_turn 결과가 `status:"started"` 핸드오프면 `_handoff_card_events(result)`를 흘리고 아니면 기존 management 카드 경로. (정확한 결선은 S2 chat 통합에 맞춰 reconcile.)

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

## Task 7: 회귀 + import 순수성 확인 (S2 의존)

- [ ] **Step 1: 전체 관련 스위트 실행**

Run: `cd backend && uv run pytest tests/orchestration/ tests/generator/ tests/management/ tests/test_attachments_contract.py -v`
Expected: PASS — management 단일·S2 멀티스텝 스텁 경로 회귀 0, S3 신규 테스트 통과.

- [ ] **Step 2: import 순수성**

`backend/tests/orchestration/test_import_purity.py`의 `_CORE`(plan/planner/executor/turn 등)가 `domain.generator`도 import하지 않음을 확인. 필요 시 `_FORBIDDEN`을 `("domain.management", "domain.generator", "domain.simulation")` 다중으로 확장하는 별도 테스트를 추가하고 통과 확인.

Run: `cd backend && uv run pytest tests/orchestration/test_import_purity.py -v`
Expected: PASS (core가 어떤 domain.*도 직접 import 안 함 — 어댑터는 generator 소유·bootstrap 등록만).

- [ ] **Step 3: 실패 시**

`systematic-debugging` 스킬로 전체 에러·스택 확인 후 원인 수정. S2 시그니처 불일치면 Precondition 표와 대조해 reconcile.

---

## Self-Review (작성자 체크)

- **스펙 커버리지** — 설계 §2(계약)=Task1, §4(generator 어댑터)=Task2, §5 단락=Task3, §3 게이트 A=Task4·6, bootstrap=Task5, 핸드오프 카드=Task6, §7 테스트(특히 §7-5 simulate 미집행)=Task3, 회귀·순수성=Task7. "job start만 보장"은 어댑터가 `start_generation` 트리거 후 즉시 핸드오프 반환(완료 await 없음)으로 충족.
- **Placeholder** — S2 의존 지점은 "reconcile"로 **명시**(은폐된 TBD 아님). S2 비의존 Task(1·2)는 완전 구체.
- **타입 정합** — 핸드오프 dict 키(`status/step_id/domain/action/task_id/stream_url/ad_id`)가 Task2(생성)·Task3(단락 판정 `status`)·Task6(카드 `task_id/stream_url`)에서 일관. `_should_plan(route, registry, *, has_image)`·`_handoff_card_events(handoff)`·`GeneratorDomainAgent.ask(ctx, step)` 시그니처 일관.
- **S2 의존 경고** — Task 3·4·5·6은 S2 미구현 시 실행 불가. 착수 전 Precondition 표로 실제 S2 코드와 reconcile 필수.
