# 매니지먼트 어시스턴트(에이전틱 RAG) 폴백 경로 — 키·임베딩 없이 동작 검증
"""use_mock/키 없음이면 키워드 라우팅 + 실시간 툴(mock reader) 요약으로 동작해야 한다.

풀모드(LLM+pgvector)는 OpenAI 키·DB 필요라 단위테스트 범위 밖(라이브로 검증).
"""

from types import SimpleNamespace

import pytest

from domain.management.assistant.agent import build_management_agent
from domain.management.assistant.contracts import AskRequest

_SETTINGS = SimpleNamespace(use_mock=True, openai_api_key=None)


@pytest.mark.asyncio
async def test_budget_question_routes_to_budget_tool():
    ask = build_management_agent(_SETTINGS)
    res = await ask(AskRequest(question="이번 달 예산 소진 얼마야?"))
    assert res.used_tools == ["live_budget"]
    assert res.answer  # 비어있지 않은 요약
    assert "this_month_spent_krw" in res.evidence


@pytest.mark.asyncio
async def test_campaigns_question_routes_to_campaigns_tool():
    ask = build_management_agent(_SETTINGS)
    res = await ask(AskRequest(question="지금 뭐 운영 중이야?"))
    assert res.used_tools == ["live_campaigns"]
    assert res.evidence.get("count") is not None


@pytest.mark.asyncio
async def test_campaign_id_routes_to_detail():
    ask = build_management_agent(_SETTINGS)
    res = await ask(AskRequest(question="이 캠페인 왜 안 나와?", campaign_id="camp_1"))
    assert res.used_tools == ["live_campaign_detail"]


@pytest.mark.asyncio
async def test_result_has_live_citation():
    ask = build_management_agent(_SETTINGS)
    res = await ask(AskRequest(question="예산 현황"))
    assert any(c.kind == "live" for c in res.citations)


@pytest.mark.asyncio
async def test_action_intent_returns_suggestion_not_execution():
    """행동 의도 → 추천 액션 제안. 실행은 안 함(쓰기 툴 미호출)."""
    ask = build_management_agent(_SETTINGS)
    res = await ask(AskRequest(question="이 캠페인 일시중지해줘", campaign_id="camp_1"))
    assert res.suggested_action is not None
    assert res.suggested_action.action_type == "PAUSE_CAMPAIGN"
    assert res.suggested_action.target_campaign_id == "camp_1"
    # 어시스턴트는 read 툴만 — writer/executor 흔적 없음
    assert res.used_tools == ["live_campaign_detail"]


@pytest.mark.asyncio
async def test_activate_requires_approval():
    ask = build_management_agent(_SETTINGS)
    res = await ask(AskRequest(question="게재 시작해줘", campaign_id="camp_9"))
    assert res.suggested_action is not None
    assert res.suggested_action.action_type == "ACTIVATE_CAMPAIGN"
    assert res.suggested_action.requires_approval is True  # Tier 3


@pytest.mark.asyncio
async def test_read_question_has_no_suggestion():
    ask = build_management_agent(_SETTINGS)
    res = await ask(AskRequest(question="이번 달 소진 얼마야?"))
    assert res.suggested_action is None


@pytest.mark.asyncio
async def test_expand_audience_intent():
    """타깃 확장 의도 → EXPAND_AUDIENCE 제안(Tier 3 승인)."""
    ask = build_management_agent(_SETTINGS)
    res = await ask(AskRequest(question="타깃 좀 확장해줘", campaign_id="camp_1"))
    assert res.suggested_action is not None
    assert res.suggested_action.action_type == "EXPAND_AUDIENCE"
    assert res.suggested_action.requires_approval is True  # Tier 3


@pytest.mark.asyncio
async def test_change_bid_intent_wins_over_replace():
    """'입찰 바꿔'는 generic 교체(REPLACE)가 아니라 CHANGE_BID_STRATEGY로 매칭돼야 한다."""
    ask = build_management_agent(_SETTINGS)
    res = await ask(AskRequest(question="입찰 전략 바꿔줘", campaign_id="camp_1"))
    assert res.suggested_action is not None
    assert res.suggested_action.action_type == "CHANGE_BID_STRATEGY"
    assert res.suggested_action.requires_approval is True  # Tier 3


# ── 풀모드 ReAct 그래프 — 가짜 LLM으로 도구 루프·HITL 검증(OpenAI 키 불필요) ──

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

from domain.management.assistant.graph import build_graph, to_result  # noqa: E402


class _FakeLLM:
    """bind_tools를 지원하고 미리 정한 AIMessage를 순서대로 내는 스텁."""

    def __init__(self, scripted: list[AIMessage]) -> None:
        self._s = scripted
        self._i = 0

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, _msgs):
        msg = self._s[min(self._i, len(self._s) - 1)]
        self._i += 1
        return msg


def _run(llm, question, campaign_id=None):
    g = build_graph(_SETTINGS, None, llm, checkpointer=MemorySaver())
    return g.ainvoke(
        {"messages": [HumanMessage(content=question)], "campaign_id": campaign_id},
        config={"configurable": {"thread_id": "t"}},
    )


@pytest.mark.asyncio
async def test_react_read_tool_loop_accumulates_evidence():
    llm = _FakeLLM(
        [
            AIMessage(content="", tool_calls=[{"name": "live_budget", "args": {}, "id": "c1"}]),
            AIMessage(content="이번 달 소진 현황입니다."),
        ]
    )
    res = to_result(await _run(llm, "예산 얼마야?"), "t")
    assert res.used_tools == ["live_budget"]
    assert "this_month_spent_krw" in res.evidence
    assert any(c.kind == "live" for c in res.citations)
    assert res.requires_approval is False


@pytest.mark.asyncio
async def test_react_propose_tier3_interrupts_for_approval():
    """Tier 3(게재 시작) 제안 → interrupt로 그래프가 멈춰 사람 승인 대기(HITL)."""
    llm = _FakeLLM(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "propose_action",
                        "args": {"action_type": "ACTIVATE_CAMPAIGN", "campaign_id": "camp_9"},
                        "id": "c2",
                    }
                ],
            ),
        ]
    )
    final = await _run(llm, "게재 시작해줘", "camp_9")
    intr = final.get("__interrupt__")
    assert intr, "Tier 3는 interrupt로 멈춰야 함"
    sa = intr[0].value["suggested_action"]
    assert sa["action_type"] == "ACTIVATE_CAMPAIGN"
    assert sa["requires_approval"] is True


@pytest.mark.asyncio
async def test_react_propose_tier1_does_not_interrupt():
    """Tier 1(일시중지)은 자동 승인 한도 내 → 멈추지 않고 제안만 기록."""
    llm = _FakeLLM(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "propose_action",
                        "args": {"action_type": "PAUSE_CAMPAIGN", "campaign_id": "camp_1"},
                        "id": "c3",
                    }
                ],
            ),
            AIMessage(content="일시중지를 제안합니다."),
        ]
    )
    res = to_result(await _run(llm, "이거 멈춰", "camp_1"), "t")
    assert res.suggested_action and res.suggested_action.action_type == "PAUSE_CAMPAIGN"
    assert res.requires_approval is False
