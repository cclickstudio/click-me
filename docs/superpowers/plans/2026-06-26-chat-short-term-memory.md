# 챗 숏텀 메모리(state 기반 컨텍스트 유지) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 서브에이전트(시뮬·생성·매니지먼트)가 같은 세션의 직전 대화를 보고 다중턴 슬롯필링("표본 몇 명?" → "50명" → 실행)을 수행하게 한다.

**Architecture:** 숏텀 메모리는 이미 배선된 LangGraph 체크포인터(`state["messages"]` 자동 누적)를 단일 소스로 쓴다. `delegate`가 최근 N개를 `SubAgentRequest.history`로 동봉하고, 각 챗 도메인 어댑터가 이를 프리앰블로 질문 앞에 붙인다. 광고 컨텍스트(ad_id·이미지)는 `context_ids` merge 리듀서로 턴을 넘겨 생존시킨다. `chat_messages` 테이블은 표시 전용으로 남긴다.

**Tech Stack:** FastAPI · LangGraph(StateGraph·add_messages·AsyncPostgresSaver) · LangChain(Anthropic) · pydantic · pytest(asyncio).

**스펙:** [docs/superpowers/specs/2026-06-26-chat-short-term-memory-design.md](../specs/2026-06-26-chat-short-term-memory-design.md)

**공통 규칙(CLAUDE.md):** 백엔드 `.py` 변경 → **각 커밋 전** `cd backend && uv run ruff format . && uv run ruff check . --fix`. 커밋 메시지는 `타입: 한국어 설명`. 타 도메인(`domain/management/*`·`domain/simulation/*`) 내부는 무수정.

**테스트 실행 위치:** `cd backend && uv run pytest ...`. 신규 단위 테스트는 모두 hermetic(실 DB·실 LLM 무의존).

---

## Task 1: `SubAgentRequest.history` 계약 추가

**Files:**
- Modify: `backend/domain/chat/contracts/agent_io.py:52-56`
- Test: `backend/tests/chat/test_short_term_memory.py`

- [ ] **Step 1: 실패 테스트 작성** — `backend/tests/chat/test_short_term_memory.py` 신규 생성

```python
# 챗 숏텀 메모리(state 기반) — 계약·리듀서·헬퍼·delegate·어댑터 프리앰블 검증.
import pytest


def test_subagent_request_history_defaults_empty():
    from domain.chat.contracts.agent_io import SubAgentRequest

    req = SubAgentRequest(question="hi")
    assert req.history == []
    req2 = SubAgentRequest(question="hi", history=[{"role": "user", "content": "x"}])
    assert req2.history[0]["content"] == "x"
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/chat/test_short_term_memory.py::test_subagent_request_history_defaults_empty -v`
Expected: FAIL — `TypeError`/`ValidationError`(history 미정의 또는 unexpected) 또는 `AttributeError`.

- [ ] **Step 3: 구현** — `agent_io.py`의 `SubAgentRequest`에 필드 추가

```python
class SubAgentRequest(BaseModel):
    # 단발 위임 — 슈퍼바이저가 history를 question/context_ids에 녹여 전달(서브에이전트는 무상태).
    question: str
    context_ids: dict = Field(default_factory=dict)
    knobs: dict = Field(default_factory=dict)
    history: list[dict] = Field(default_factory=list)  # [{role, content}] 최근 윈도우(어댑터가 프리앰블화)
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/chat/test_short_term_memory.py::test_subagent_request_history_defaults_empty -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/domain/chat/contracts/agent_io.py backend/tests/chat/test_short_term_memory.py
git commit -m "add: SubAgentRequest.history 필드 — 서브에이전트 대화 컨텍스트 전달 통로"
```

---

## Task 2: `context_ids` merge 리듀서 (광고 컨텍스트 턴 생존)

**Files:**
- Modify: `backend/domain/chat/graph/state.py`
- Test: `backend/tests/chat/test_short_term_memory.py`

- [ ] **Step 1: 실패 테스트 추가** (파일 끝에 append)

```python
def test_merge_context_keeps_old_overlays_nonnull():
    from domain.chat.graph.state import _merge_context

    out = _merge_context({"ad_id": "a", "x": 1}, {"ad_id": None, "y": 2})
    assert out == {"ad_id": "a", "x": 1, "y": 2}  # 기존 유지 + 새 non-null만 덮어쓰기


def test_merge_context_handles_none_old():
    from domain.chat.graph.state import _merge_context

    assert _merge_context(None, {"a": 1, "b": None}) == {"a": 1}
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/chat/test_short_term_memory.py -k merge_context -v`
Expected: FAIL — `ImportError: cannot import name '_merge_context'`.

- [ ] **Step 3: 구현** — `state.py` 전체를 아래로 교체

```python
# 슈퍼바이저 그래프 상태 — 챗 한 턴의 누적 상태(TypedDict).
from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


def _merge_context(old: dict | None, new: dict | None) -> dict:
    """context_ids 리듀서 — 기존 값 유지, 새 입력의 non-null만 덮어쓴다(turn2 null이 ad_id를 못 지움)."""
    merged = dict(old or {})
    for k, v in (new or {}).items():
        if v is not None:
            merged[k] = v
    return merged


class ChatState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    short_term: list[dict]
    long_term: list[dict]
    brand_profile: dict | None
    project_id: str | None
    user_id: str | None
    organization_id: str | None
    context_ids: Annotated[dict, _merge_context]
    route: str
    delegations: int
    sub_results: list[dict]
    citations: list[dict]
    pending_action: dict | None
    execution_result: dict | None
    approval_decision: dict | None
    final_answer: str
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/chat/test_short_term_memory.py -k merge_context -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/domain/chat/graph/state.py backend/tests/chat/test_short_term_memory.py
git commit -m "add: context_ids merge 리듀서 — 광고 컨텍스트가 턴을 넘겨 생존(null 미덮어쓰기)"
```

---

## Task 3: 히스토리 헬퍼 — `_messages_to_history` + `history_to_preamble`

**Files:**
- Modify: `backend/domain/chat/graph/nodes.py` (import + 상수 + 헬퍼)
- Create: `backend/domain/chat/adapters/history.py`
- Test: `backend/tests/chat/test_short_term_memory.py`

- [ ] **Step 1: 실패 테스트 추가** (append)

```python
def test_messages_to_history_maps_roles_and_windows():
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    from domain.chat.graph.nodes import _messages_to_history

    msgs = [
        SystemMessage(content="sys"),
        HumanMessage(content="q1"),
        AIMessage(content="a1"),
        HumanMessage(content="q2"),
    ]
    out = _messages_to_history(msgs, window=2)  # 원시 마지막 2개(a1,q2)만
    assert out == [
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
    ]


def test_messages_to_history_skips_non_chat_roles():
    from langchain_core.messages import HumanMessage, SystemMessage

    from domain.chat.graph.nodes import _messages_to_history

    out = _messages_to_history([SystemMessage(content="s"), HumanMessage(content="q")], window=10)
    assert out == [{"role": "user", "content": "q"}]


def test_history_to_preamble_empty_is_blank():
    from domain.chat.adapters.history import history_to_preamble

    assert history_to_preamble([]) == ""
    assert history_to_preamble(None) == ""


def test_history_to_preamble_format():
    from domain.chat.adapters.history import history_to_preamble

    out = history_to_preamble(
        [
            {"role": "user", "content": "이 광고 시뮬 돌려줘"},
            {"role": "assistant", "content": "표본 몇 명으로 할까요?"},
        ]
    )
    assert out.startswith("[이전 대화]\n")
    assert "사용자: 이 광고 시뮬 돌려줘" in out
    assert "어시스턴트: 표본 몇 명으로 할까요?" in out
    assert out.endswith("[현재 질문]\n")
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/chat/test_short_term_memory.py -k "history" -v`
Expected: FAIL — `ImportError`(`_messages_to_history` 또는 `domain.chat.adapters.history`).

- [ ] **Step 3a: 구현 — `adapters/history.py` 신규 생성**

```python
# 대화 히스토리를 서브에이전트 질문 앞에 붙일 프리앰블 문자열로 포매팅한다.
"""history_to_preamble([{role, content}]) → '[이전 대화]…[현재 질문]\n' 또는 ''(빈 히스토리)."""

from __future__ import annotations

_ROLE_LABEL = {"user": "사용자", "assistant": "어시스턴트"}


def history_to_preamble(history: list[dict] | None) -> str:
    """히스토리를 한국어 프리앰블로. 비어 있으면 빈 문자열(1턴 동작 불변)."""
    if not history:
        return ""
    lines: list[str] = []
    for h in history:
        content = (h.get("content") or "").strip()
        if not content:
            continue
        label = _ROLE_LABEL.get(h.get("role"), h.get("role") or "")
        lines.append(f"{label}: {content}")
    if not lines:
        return ""
    return "[이전 대화]\n" + "\n".join(lines) + "\n\n[현재 질문]\n"
```

- [ ] **Step 3b: 구현 — `nodes.py` import 보강**

`nodes.py:13`의 import를 아래로 교체(`HumanMessage` 추가).

```python
from langchain_core.messages import AIMessage, HumanMessage
```

- [ ] **Step 3c: 구현 — `nodes.py` 상수·헬퍼 추가**

`_MAX_DELEGATIONS = 4` 정의 **아래**(`nodes.py:27` 부근)에 추가.

```python
# 서브에이전트·short_term에 전달할 최근 메시지 수(=10턴). 무한 누적 state를 읽을 때 슬라이스.
_HISTORY_WINDOW = 20


def _messages_to_history(messages: list, window: int = _HISTORY_WINDOW) -> list[dict]:
    """LangChain 메시지 → [{role, content}](user/assistant만), 최근 window개로 슬라이스."""
    out: list[dict] = []
    for m in messages[-window:]:
        if isinstance(m, HumanMessage):
            role = "user"
        elif isinstance(m, AIMessage):
            role = "assistant"
        else:
            continue
        content = m.content if isinstance(m.content, str) else str(m.content)
        out.append({"role": role, "content": content})
    return out
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/chat/test_short_term_memory.py -k "history" -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/domain/chat/adapters/history.py backend/domain/chat/graph/nodes.py backend/tests/chat/test_short_term_memory.py
git commit -m "add: 히스토리 헬퍼 — messages→dict 윈도우 + 프리앰블 포매터"
```

---

## Task 4: `delegate`가 히스토리를 동봉

**Files:**
- Modify: `backend/domain/chat/graph/nodes.py:155-182` (`delegate`)
- Test: `backend/tests/chat/test_short_term_memory.py`

- [ ] **Step 1: 실패 테스트 추가** (append)

```python
@pytest.mark.asyncio
async def test_delegate_passes_history_excluding_current():
    from langchain_core.messages import AIMessage, HumanMessage

    from domain.chat.contracts.agent_io import Route, SubAgentResult
    from domain.chat.graph.nodes import ChatGraphDeps, make_nodes

    captured = {}

    class FakeSub:
        route = Route.SIMULATION

        async def run(self, req):
            captured["req"] = req
            return SubAgentResult(route=Route.SIMULATION, answer="ok")

    deps = ChatGraphDeps(
        llm=None, repo=None, memory=None, subagents={Route.SIMULATION.value: FakeSub()}
    )
    nodes = make_nodes(deps)
    state = {
        "route": Route.SIMULATION.value,
        "messages": [
            HumanMessage(content="시뮬 돌려줘"),
            AIMessage(content="표본 몇 명?"),
            HumanMessage(content="50명"),
        ],
        "context_ids": {},
    }
    await nodes.delegate(state)
    req = captured["req"]
    assert req.history == [
        {"role": "user", "content": "시뮬 돌려줘"},
        {"role": "assistant", "content": "표본 몇 명?"},
    ]
    assert req.question == "50명"  # 현재 턴은 history 제외, question으로 분리 전달
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/chat/test_short_term_memory.py::test_delegate_passes_history_excluding_current -v`
Expected: FAIL — `assert req.history == [...]` (현재 `history`는 빈 리스트 기본값).

- [ ] **Step 3: 구현** — `delegate`의 `SubAgentRequest(...)` 생성부(`nodes.py:167-171`)를 교체

```python
        req = SubAgentRequest(
            question=_last_user_text(state["messages"]),
            context_ids=_scope_context_ids(state),
            knobs=(state.get("context_ids") or {}).get("knobs", {}),
            history=_messages_to_history(state.get("messages", [])[:-1]),
        )
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/chat/test_short_term_memory.py::test_delegate_passes_history_excluding_current -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/domain/chat/graph/nodes.py backend/tests/chat/test_short_term_memory.py
git commit -m "add: delegate가 최근 대화(history)를 서브에이전트 요청에 동봉"
```

---

## Task 5: `load_context` short_term을 state에서 파생 (DB 조회 은퇴)

**Files:**
- Modify: `backend/domain/chat/graph/nodes.py:9` (uuid import 제거), `:107-138` (`load_context`)
- Test: `backend/tests/chat/test_short_term_memory.py`

- [ ] **Step 1: 실패 테스트 추가** (append)

```python
@pytest.mark.asyncio
async def test_load_context_short_term_from_state_no_db():
    from langchain_core.messages import AIMessage, HumanMessage

    from domain.chat.graph.nodes import ChatGraphDeps, make_nodes

    deps = ChatGraphDeps(llm=None, repo=None, memory=None)  # repo=None → DB 의존 없음
    nodes = make_nodes(deps)
    state = {"messages": [HumanMessage(content="안녕"), AIMessage(content="네")]}
    out = await nodes.load_context(state, {"configurable": {"thread_id": "t"}})
    assert out["short_term"] == [
        {"role": "user", "content": "안녕"},
        {"role": "assistant", "content": "네"},
    ]
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/chat/test_short_term_memory.py::test_load_context_short_term_from_state_no_db -v`
Expected: FAIL — 현재 `short_term`은 `repo` 없으면 `[]`.

- [ ] **Step 3a: 구현 — `nodes.py:9`의 `import uuid` 삭제**

(load_context가 더는 `uuid.UUID(session_id)`를 쓰지 않으므로 미사용 import 제거. ruff F401 방지.)

- [ ] **Step 3b: 구현 — `load_context` 본문(`nodes.py:107-138`)을 교체**

```python
    # ── load_context ──────────────────────────────────────────────────────────
    async def load_context(self, state: dict, config: Optional[RunnableConfig] = None) -> dict:  # noqa: UP045
        deps = self._d
        # 숏텀 메모리 = 체크포인터가 누적한 state["messages"]에서 파생(DB 조회 불필요).
        # chat_messages 테이블은 표시·세션목록·리로드용으로 orchestrator가 별도 영속한다.
        short_term: list[dict] = _messages_to_history(state.get("messages", []))
        long_term: list[dict] = []

        if deps.memory:
            try:
                hits = await deps.memory.recall(
                    query=_last_user_text(state["messages"]),
                    project_id=state.get("project_id"),
                    user_id=state.get("user_id"),
                    k=5,
                    salience_floor=0.9,
                )
                long_term = [h.content for h in hits]
            except Exception:  # noqa: BLE001
                long_term = []

        return {
            "short_term": short_term,
            "long_term": long_term,
            "pending_action": None,
            "route": "",
        }
```

- [ ] **Step 4: 통과 확인 + 회귀 없음**

Run: `cd backend && uv run pytest tests/chat/test_short_term_memory.py::test_load_context_short_term_from_state_no_db -v`
Expected: PASS

Run: `cd backend && uv run pytest tests/chat -q`
Expected: 전체 PASS(기존 챗 테스트 회귀 없음). 실패 시 멈추고 원인(주로 load_context를 mock repo로 가정한 기존 테스트) 확인 후 수정.

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/domain/chat/graph/nodes.py backend/tests/chat/test_short_term_memory.py
git commit -m "edit: load_context short_term을 state에서 파생 — DB 조회 은퇴(체크포인터 단일 소스)"
```

---

## Task 6: 어댑터에서 히스토리 프리앰블을 질문 앞에 주입 (sim·gen·management)

**Files:**
- Modify: `backend/domain/chat/adapters/simulation_subagent.py:58-71`
- Modify: `backend/domain/chat/adapters/generator_subagent.py:71-85`
- Modify: `backend/domain/chat/adapters/management_subagent.py:49-58`
- Test: `backend/tests/chat/test_short_term_memory.py`

- [ ] **Step 1: 실패 테스트 추가** (append)

```python
@pytest.mark.asyncio
async def test_simulation_subagent_prepends_history():
    from domain.chat.adapters.simulation_subagent import SimulationSubAgent
    from domain.chat.contracts.agent_io import SubAgentRequest

    captured = {}

    async def fake_agent(question, context_ids):
        captured["q"] = question
        return {"answer": "ok", "used_tools": [], "kb_citations": [], "sim_data": {}}

    sub = SimulationSubAgent()
    sub._agent = fake_agent  # build 우회(키 불필요)
    req = SubAgentRequest(
        question="50명",
        history=[
            {"role": "user", "content": "시뮬 돌려줘"},
            {"role": "assistant", "content": "표본 몇 명?"},
        ],
    )
    await sub.run(req)
    assert captured["q"].startswith("[이전 대화]")
    assert captured["q"].endswith("[현재 질문]\n50명")


@pytest.mark.asyncio
async def test_simulation_subagent_no_history_unchanged():
    from domain.chat.adapters.simulation_subagent import SimulationSubAgent
    from domain.chat.contracts.agent_io import SubAgentRequest

    captured = {}

    async def fake_agent(question, context_ids):
        captured["q"] = question
        return {"answer": "ok", "used_tools": [], "kb_citations": [], "sim_data": {}}

    sub = SimulationSubAgent()
    sub._agent = fake_agent
    await sub.run(SubAgentRequest(question="현황 보여줘"))
    assert captured["q"] == "현황 보여줘"  # 빈 히스토리 → 질문 불변


@pytest.mark.asyncio
async def test_generator_subagent_prepends_history():
    from domain.chat.adapters.generator_subagent import GeneratorSubAgent
    from domain.chat.contracts.agent_io import SubAgentRequest

    captured = {}

    async def fake_agent(question, context_ids):
        captured["q"] = question
        return {"answer": "ok", "used_tools": [], "kb_citations": [], "gen_data": {}}

    sub = GeneratorSubAgent()
    sub._agent = fake_agent
    req = SubAgentRequest(
        question="비타민",
        history=[
            {"role": "user", "content": "광고 만들어줘"},
            {"role": "assistant", "content": "어떤 상품을 만들까요?"},
        ],
    )
    await sub.run(req)
    assert captured["q"].startswith("[이전 대화]")
    assert captured["q"].endswith("[현재 질문]\n비타민")


@pytest.mark.asyncio
async def test_management_subagent_prepends_history():
    from types import SimpleNamespace

    from domain.chat.adapters.management_subagent import ManagementSubAgent
    from domain.chat.contracts.agent_io import SubAgentRequest

    captured = {}

    async def fake_ask(ask_req):
        captured["q"] = ask_req.question
        return SimpleNamespace(answer="ok", citations=[], used_tools=[], suggested_action=None)

    sub = ManagementSubAgent(ask=fake_ask)
    req = SubAgentRequest(
        question="예산 어때?",
        history=[
            {"role": "user", "content": "캠페인 보여줘"},
            {"role": "assistant", "content": "어느 캠페인이요?"},
        ],
    )
    await sub.run(req)
    assert captured["q"].startswith("[이전 대화]")
    assert captured["q"].endswith("[현재 질문]\n예산 어때?")
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/chat/test_short_term_memory.py -k "subagent_prepends or subagent_no_history" -v`
Expected: FAIL — 프리앰블 미적용(질문이 그대로 전달됨).

- [ ] **Step 3a: 구현 — `simulation_subagent.py` ReAct 분기**

`_dispatch`의 `if agent is not None:` 블록 첫 줄을 교체(`out = await agent(...)` 직전).

```python
        agent = self._get_agent()
        if agent is not None:
            from domain.chat.adapters.history import history_to_preamble  # noqa: PLC0415

            question = history_to_preamble(req.history) + req.question
            out = await agent(question, req.context_ids)
            sim_data = out.get("sim_data") or {}
```

- [ ] **Step 3b: 구현 — `generator_subagent.py` ReAct 분기**

```python
        agent = self._get_agent()
        if agent is not None:
            from domain.chat.adapters.history import history_to_preamble  # noqa: PLC0415

            question = history_to_preamble(req.history) + req.question
            out = await agent(question, req.context_ids)
            gen_data = out.get("gen_data") or {}
```

- [ ] **Step 3c: 구현 — `management_subagent.py` `_dispatch`**

`ask_req = AskRequest(...)` 생성부를 교체.

```python
        from domain.chat.adapters.history import history_to_preamble  # noqa: PLC0415

        ask = self._get_ask()
        ask_req = AskRequest(
            question=history_to_preamble(req.history) + req.question,
            campaign_id=req.context_ids.get("campaign_id"),
            ad_id=req.context_ids.get("ad_id"),
        )
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/chat/test_short_term_memory.py -k "subagent_prepends or subagent_no_history" -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/domain/chat/adapters/simulation_subagent.py backend/domain/chat/adapters/generator_subagent.py backend/domain/chat/adapters/management_subagent.py backend/tests/chat/test_short_term_memory.py
git commit -m "add: 서브에이전트 어댑터가 대화 히스토리를 질문 프리앰블로 주입(sim·gen·mgmt)"
```

---

## Task 7: sim·gen `_SYSTEM` 되묻기 프롬프트 전환

**Files:**
- Modify: `backend/domain/chat/adapters/sim_agent.py:31-35`
- Modify: `backend/domain/chat/adapters/gen_agent.py:23-25`

> 프롬프트(LLM 행동) 변경이라 hermetic 단위 테스트 없음 — Task 10 라이브에서 검증. 컴파일 가드는 Task 9 전체 실행으로 커버.

- [ ] **Step 1: `sim_agent.py` `_SYSTEM` 트리거 블록 교체**

기존(아래)을

```python
    "- [현재 맥락]에 '첨부된 광고 있음'이 보이고 사용자가 시뮬 '실행/돌려'를 원하면 "
    "start_simulation으로 바로 실행한다(되묻지 말 것).\n"
    "  메시지에 표본·타깃·제목·목표가 있으면 반영, 없으면 기본(표본20·전체)으로 실행한다.\n"
    "  사용한 설정을 답에 명시하고 다른 설정을 원하면 함께 말해달라고 안내한다.\n"
    "  맥락에 첨부된 광고가 없으면 start_simulation을 호출하지 말고 먼저 이미지 첨부를 요청한다.\n"
```

아래로 교체.

```python
    "- [현재 맥락]에 '첨부된 광고 있음'이 보이고 사용자가 시뮬 '실행/돌려'를 원할 때, "
    "표본·타깃이 이번 메시지·[이전 대화] 어디에도 없고 [이전 대화]에서 아직 묻지 않았으면 "
    "start_simulation을 호출하지 말고 '표본 몇 명으로, 어떤 타깃으로 돌릴까요? "
    "(기본 표본 20·전체)'라고 한 번만 되묻는다.\n"
    "  [이전 대화]에 이미 그 되물음이 있고 이번 메시지가 그 답(또는 '그냥/기본/아무거나')이거나, "
    "이번 메시지에 표본·타깃·제목·목표가 있으면, 그 값(없으면 기본 표본20·전체)으로 바로 실행한다.\n"
    "  사용한 설정을 답에 명시하고 다른 설정을 원하면 함께 말해달라고 안내한다.\n"
    "  맥락에 첨부된 광고가 없으면 start_simulation을 호출하지 말고 먼저 이미지 첨부를 요청한다.\n"
```

- [ ] **Step 2: `gen_agent.py` `_SYSTEM` 트리거 블록 교체**

기존(아래)을

```python
    "- 사용자가 '새 시안/광고 만들어/생성해'를 원하면 메시지의 상품명·설명·타깃·목표를 반영해 "
    "start_generation으로 바로 실행한다(되묻지 말 것). 안 준 값은 기본, 사용 설정은 명시한다.\n"
    "  단 상품명이 없으면 실행하지 말고 '어떤 상품을 만들까요?'라고 한 번만 물어본다.\n"
```

아래로 교체.

```python
    "- 사용자가 '새 시안/광고 만들어/생성해'를 원하면 이번 메시지·[이전 대화]의 상품명·설명·타깃·"
    "목표를 반영해 start_generation으로 실행한다. 안 준 값은 기본, 사용 설정은 명시한다.\n"
    "  상품명이 없고 [이전 대화]에서 아직 묻지 않았으면 '어떤 상품을 만들까요?'라고 한 번만 물어본다. "
    "[이전 대화]에서 이미 물었고 이번 메시지가 그 답이면 그 상품명으로 바로 실행한다.\n"
```

- [ ] **Step 3: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/domain/chat/adapters/sim_agent.py backend/domain/chat/adapters/gen_agent.py
git commit -m "edit: 시뮬·생성 트리거 프롬프트를 단일턴→되묻기로 — 슬롯 없으면 1회 질문 후 다음 턴 실행"
```

---

## Task 8: 슈퍼바이저 라우팅 연속성 규칙(B1)

**Files:**
- Modify: `backend/domain/chat/graph/supervisor.py:74-77` (`_ROUTING_SYSTEM` 끝부분)

> 라우팅 행동(LLM)이라 hermetic 단위 테스트 없음 — Task 10 라이브에서 검증.

- [ ] **Step 1: `_ROUTING_SYSTEM` 마지막 두 줄 교체**

기존(아래)을

```python
    "주의: '몇 개/목록/내가 만든·생성한'이 생성물(시안)을 가리키면 캠페인(management)이 아니라 "
    "route_to_generation 이다.\n"
    "반드시 도구 하나만 호출한다."
```

아래로 교체(연속성 규칙 삽입).

```python
    "주의: '몇 개/목록/내가 만든·생성한'이 생성물(시안)을 가리키면 캠페인(management)이 아니라 "
    "route_to_generation 이다.\n"
    "연속성: 직전 어시스턴트 메시지가 특정 기능의 되물음(예: 시뮬 표본 수·타깃, 또는 생성할 상품명)"
    "이고 이번 사용자 메시지가 그 짧은 답이면, 새 의도로 보지 말고 그 기능과 같은 위임처로 라우팅한다.\n"
    "반드시 도구 하나만 호출한다."
```

- [ ] **Step 2: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/domain/chat/graph/supervisor.py
git commit -m "add: 라우터 연속성 규칙 — 직전 되물음의 짧은 답을 같은 위임처로(B1)"
```

---

## Task 9: 전체 검증(ruff + 챗 테스트 스위트)

**Files:** 없음(검증 전용)

- [ ] **Step 1: ruff 통과 확인**

Run: `cd backend && uv run ruff format . && uv run ruff check .`
Expected: `All checks passed!` (E501 등 잔여 시 해당 줄 분할 후 재실행)

- [ ] **Step 2: 챗 테스트 전체 실행**

Run: `cd backend && uv run pytest tests/chat -q`
Expected: 전체 PASS. 신규 `test_short_term_memory.py`(약 12개) + 기존 챗 테스트(컴파일 가드 포함) 회귀 없음.

- [ ] **Step 3: 실패 시 처리**

기존 테스트가 `load_context`를 mock repo 기반으로 가정해 깨지면(Task 5 영향), 해당 테스트의 기대를 "state 파생 short_term"으로 수정한다. 새 동작이 스펙이므로 테스트를 새 계약에 맞춘다(구현을 되돌리지 않음). 수정 후 Step 2 재실행.

- [ ] **Step 4: (테스트 수정이 있었다면) 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/tests/chat
git commit -m "edit: load_context state 파생 전환에 맞춰 기존 챗 테스트 정합"
```

---

## Task 10: 라이브 검증(실 Claude, 시뮬 실행은 가짜 서비스로 가로채 비용 0)

**Files:**
- Create(비커밋): `C:\Users\804\AppData\Local\Temp\claude\C--Users-804-Documents-main-project-chat-click-me\5ec0ccd2-ef10-47c9-93f8-b3abb7caf012\scratchpad\_stm_live.py`

> **전제(실모드 필수):** `backend/.env`에 `ANTHROPIC_API_KEY` 존재 + `use_mock=False`. mock이면 `build_simulation_agent`가 None을 반환해 ReAct가 안 돌고 슬롯필링이 동작하지 않는다(폴백 즉발). 실제 시뮬 엔진은 `build_simulation_service`를 가짜로 바꿔 호출하지 않는다. 서브에이전트를 직접 2턴 구동해 슬롯필링만 확인한다(B1 라우팅은 UI/슈퍼바이저 경유라 별도).

- [ ] **Step 1: 스크립트 작성**

```python
# 챗 숏텀 메모리 라이브 검증 — 실 Claude로 시뮬 서브에이전트 2턴 슬롯필링(시뮬 실행은 가짜).
import asyncio
import os
import sys

# backend를 sys.path에 절대경로로 추가(scratchpad에서 실행 — cwd는 sys.path에 자동 포함 안 됨).
sys.path.insert(0, r"C:\Users\804\Documents\main_project\chat\click-me\backend")

os.environ.setdefault("PYTHONUTF8", "1")


class _FakeSvc:
    def __init__(self):
        self.calls = []

    async def start(self, req):
        self.calls.append(req)
        return "11111111-1111-1111-1111-111111111111"


async def main():
    import domain.simulation.wiring as simwiring

    fake = _FakeSvc()
    simwiring.build_simulation_service = lambda settings: fake  # 실제 시뮬 비실행

    from domain.chat.adapters.history import history_to_preamble  # noqa: F401
    from domain.chat.adapters.simulation_subagent import SimulationSubAgent
    from domain.chat.contracts.agent_io import SubAgentRequest

    ctx = {
        "ad_id": "ad-live-1",
        "ad_image_url": "https://example.com/ad.png",
        "ad_image_key": "ads/live-1.png",
        "project_id": "proj-live-1",
        "organization_id": "org-live-1",
    }

    sub = SimulationSubAgent()

    # 턴1: 표본 미지정 → 되묻기 기대(start_simulation 미호출)
    r1 = await sub.run(SubAgentRequest(question="이 광고 시뮬 돌려줘", context_ids=ctx, history=[]))
    print("=== 턴1 ===\n", r1.answer)
    print("start 호출수:", len(fake.calls))

    # 턴2: "50명" + 턴1 대화 history → start_simulation(sample_size=50) 기대
    hist = [
        {"role": "user", "content": "이 광고 시뮬 돌려줘"},
        {"role": "assistant", "content": r1.answer},
    ]
    r2 = await sub.run(SubAgentRequest(question="20대 여성 표본 50명으로 돌려줘", context_ids=ctx, history=hist))
    print("\n=== 턴2 ===\n", r2.answer)
    print("start 호출수:", len(fake.calls))
    if fake.calls:
        c = fake.calls[-1]
        print("sample_size:", c.sample_size, "target_filter:", c.target_filter, "ad_id:", c.ad_id)


asyncio.run(main())
```

- [ ] **Step 2: 실행**

Run: `cd backend && uv run python "C:\Users\804\AppData\Local\Temp\claude\C--Users-804-Documents-main-project-chat-click-me\5ec0ccd2-ef10-47c9-93f8-b3abb7caf012\scratchpad\_stm_live.py"`

Expected:
- 턴1 — 답변이 "표본 몇 명…" 되묻기, `start 호출수: 0`.
- 턴2 — `start 호출수: 1`, `sample_size: 50`, `target_filter`에 age 20-29·gender female, `ad_id: ad-live-1`(컨텍스트 생존 확인).

- [ ] **Step 3: 실패 시**

턴1에서 즉시 실행(호출수 1)되면 sim `_SYSTEM` 되묻기 문구를 강화(Task 7). 턴2에서 미실행이면 프리앰블이 question에 들어갔는지(`history_to_preamble`) 확인. 수정 후 Task 9 재실행.

- [ ] **Step 4: 정리(비커밋 산출물 삭제)**

```bash
rm -f "C:\Users\804\AppData\Local\Temp\claude\C--Users-804-Documents-main-project-chat-click-me\5ec0ccd2-ef10-47c9-93f8-b3abb7caf012\scratchpad\_stm_live.py"
```

---

## 완료 기준

- 단위(hermetic): `SubAgentRequest.history` 기본값, `_merge_context`(유지·null무시·None old), `_messages_to_history`(매핑·윈도우·비챗 스킵), `history_to_preamble`(빈/포맷), `delegate` history 동봉(현재 턴 제외), `load_context` state 파생, 어댑터 3종 프리앰블 주입/무히스토리 불변 — 전부 green.
- `cd backend && uv run ruff check .` green, `uv run pytest tests/chat -q` green.
- 라이브: 턴1 되묻기·턴2 `start_simulation(sample_size=50, target age20-29·female)` + ad_id 생존.
- 비범위(미구현): LTM 회상, 저장소 prune(`RemoveMessage`), B2 확정적 라우팅, 세션 요약.
