# 오케스트레이터 I/O 계약 — 스키마 round-trip + SubAgent 포트 구조적 적합성(hermetic).
import uuid

import pytest

from domain.chat.contracts.agent_io import (
    ChatTurnRequest,
    Citation,
    ProposedAction,
    Route,
    SubAgentRequest,
    SubAgentResult,
)
from domain.chat.contracts.ports import SubAgent


def test_route_enum_values():
    assert {r.value for r in Route} == {"general", "management", "simulation", "generation"}


def test_chat_turn_request_defaults():
    r = ChatTurnRequest(session_id=uuid.uuid4(), user_text="안녕")
    assert r.history == [] and r.project_id is None and r.context_ad_id is None


def test_subagent_result_roundtrip():
    res = SubAgentResult(
        route=Route.SIMULATION,
        answer="결과",
        citations=[Citation(kind="kb", source="x.md", title="T")],
        structured={"kind": "simulation_aggregate", "data": {"click_intent_rate": 0.1}},
        proposed_action=None,
    )
    dumped = res.model_dump()
    again = SubAgentResult(**dumped)
    assert again.route is Route.SIMULATION and again.structured["kind"] == "simulation_aggregate"


def test_proposed_action_defaults():
    pa = ProposedAction(
        action_type="PAUSE_CAMPAIGN", tier="TIER_1", requires_approval=False, rationale="r"
    )
    assert pa.run_days == 7 and pa.target_campaign_id is None and pa.budget_after_krw is None


@pytest.mark.asyncio
async def test_subagent_protocol_structural():
    class Dummy:
        route = "simulation"

        async def run(self, req: SubAgentRequest) -> SubAgentResult:
            return SubAgentResult(route=Route.SIMULATION, answer=req.question)

    agent: SubAgent = Dummy()  # structural conformance (runtime_checkable not required)
    out = await agent.run(SubAgentRequest(question="q"))
    assert out.answer == "q"
