# 오케스트레이터·의도분류 — 키워드 폴백 라우팅, 디스패치, 프로젝트 지연주입 검증
"""classifier_llm=None(키워드 폴백)으로 결정론 검증. 핸들러는 스텁."""

import pytest

from api.assistant.orchestrator import Orchestrator
from api.assistant.registry import SubagentRegistry
from core.assistant_contracts import (
    Action,
    Intent,
    ProjectRef,
    SubagentRequest,
    SubagentResult,
)
from core.schemas import ChatMessage

_REGISTERED = [Intent.GENERATE, Intent.MANAGE]


def _req(text: str, **kw) -> SubagentRequest:
    return SubagentRequest(messages=[ChatMessage(role="user", content=text)], **kw)


def _reg_with(intent: Intent, handler) -> SubagentRegistry:
    reg = SubagentRegistry()
    reg.register(intent, handler)
    return reg


@pytest.mark.asyncio
async def test_keyword_classify_generate():
    from api.assistant.intent import classify_intent

    assert await classify_intent(_req("신상 운동화 광고 만들어줘"), _REGISTERED) == Intent.GENERATE


@pytest.mark.asyncio
async def test_keyword_classify_manage():
    from api.assistant.intent import classify_intent

    assert await classify_intent(_req("이번 달 예산 소진 얼마야"), _REGISTERED) == Intent.MANAGE


@pytest.mark.asyncio
async def test_keyword_classify_advise_fallback():
    from api.assistant.intent import classify_intent

    assert await classify_intent(_req("광고가 뭐야?"), _REGISTERED) == Intent.ADVISE


@pytest.mark.asyncio
async def test_run_turn_dispatches_to_handler():
    async def gen_handler(_req):
        return SubagentResult(action=Action.ASK, message="상품명?")

    orch = Orchestrator(_reg_with(Intent.GENERATE, gen_handler), classifier_llm=None)
    intent, result = await orch.run_turn(_req("광고 만들어줘"))
    assert intent == Intent.GENERATE
    assert result is not None and result.action == Action.ASK


@pytest.mark.asyncio
async def test_run_turn_advise_returns_none():
    async def gen_handler(_req):
        return SubagentResult(action=Action.ASK)

    orch = Orchestrator(_reg_with(Intent.GENERATE, gen_handler), classifier_llm=None)
    intent, result = await orch.run_turn(_req("광고가 뭐야"))
    assert intent == Intent.ADVISE
    assert result is None  # 호출자가 CLIO로 폴백


@pytest.mark.asyncio
async def test_run_turn_injects_projects_for_generate():
    captured: dict = {}

    async def gen_handler(req):
        captured["projects"] = req.available_projects
        return SubagentResult(action=Action.ASK)

    orch = Orchestrator(_reg_with(Intent.GENERATE, gen_handler), classifier_llm=None)
    calls = {"n": 0}

    async def provider():
        calls["n"] += 1
        return [ProjectRef(id="p1", name="P1")]

    await orch.run_turn(_req("광고 만들어줘"), project_provider=provider)
    assert calls["n"] == 1
    assert captured["projects"][0].id == "p1"
