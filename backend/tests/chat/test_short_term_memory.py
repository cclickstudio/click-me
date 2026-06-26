# 챗 숏텀 메모리(state 기반) — 계약·리듀서·헬퍼·delegate·어댑터 프리앰블 검증.
import pytest


def test_subagent_request_history_defaults_empty():
    from domain.chat.contracts.agent_io import SubAgentRequest

    req = SubAgentRequest(question="hi")
    assert req.history == []
    req2 = SubAgentRequest(question="hi", history=[{"role": "user", "content": "x"}])
    assert req2.history[0]["content"] == "x"


def test_merge_context_keeps_old_overlays_nonnull():
    from domain.chat.graph.state import _merge_context

    out = _merge_context({"ad_id": "a", "x": 1}, {"ad_id": None, "y": 2})
    assert out == {"ad_id": "a", "x": 1, "y": 2}  # 기존 유지 + 새 non-null만 덮어쓰기


def test_merge_context_handles_none_old():
    from domain.chat.graph.state import _merge_context

    assert _merge_context(None, {"a": 1, "b": None}) == {"a": 1}


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
