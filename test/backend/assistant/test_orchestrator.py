# 오케스트레이터·의도분류 — 의도분류 동작, 디스패치, 프로젝트 지연주입 검증
"""classifier_llm=None일 때 ADVISE 기본값 검증. 핸들러는 스텁."""

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
async def test_llm_none_returns_advise():
    """LLM 없으면(키 미설정) 의도와 관계없이 ADVISE 반환 — 키워드 폴백 금지."""
    from api.assistant.intent import classify_intent

    # 매니지먼트 키워드가 있어도 llm=None이면 ADVISE
    assert await classify_intent(_req("이번 달 예산 소진 얼마야"), _REGISTERED) == Intent.ADVISE
    # 생성 키워드가 있어도 llm=None이면 ADVISE
    assert await classify_intent(_req("신상 운동화 광고 만들어줘"), _REGISTERED) == Intent.ADVISE
    # 일반 질문도 ADVISE
    assert await classify_intent(_req("광고가 뭐야?"), _REGISTERED) == Intent.ADVISE


class _StubLLM:
    """테스트용 mock LLM — 고정 의도를 반환."""

    def __init__(self, intent: Intent):
        self._intent = intent

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages, config=None):
        from api.assistant.intent import _IntentPick  # noqa: PLC0415

        return _IntentPick(intent=self._intent)


@pytest.mark.asyncio
async def test_run_turn_dispatches_to_handler():
    async def gen_handler(_req):
        return SubagentResult(action=Action.ASK, message="상품명?")

    orch = Orchestrator(
        _reg_with(Intent.GENERATE, gen_handler),
        classifier_llm=_StubLLM(Intent.GENERATE),
    )
    intent, result = await orch.run_turn(_req("광고 만들어줘"))
    assert intent == Intent.GENERATE
    assert result is not None and result.action == Action.ASK


@pytest.mark.asyncio
async def test_run_turn_advise_returns_none():
    async def gen_handler(_req):
        return SubagentResult(action=Action.ASK)

    orch = Orchestrator(
        _reg_with(Intent.GENERATE, gen_handler),
        classifier_llm=_StubLLM(Intent.ADVISE),
    )
    intent, result = await orch.run_turn(_req("광고가 뭐야"))
    assert intent == Intent.ADVISE
    assert result is None  # 호출자가 CLIO로 폴백


@pytest.mark.asyncio
async def test_run_turn_injects_projects_for_generate():
    captured: dict = {}

    async def gen_handler(req):
        captured["projects"] = req.available_projects
        return SubagentResult(action=Action.ASK)

    orch = Orchestrator(
        _reg_with(Intent.GENERATE, gen_handler),
        classifier_llm=_StubLLM(Intent.GENERATE),
    )
    calls = {"n": 0}

    async def provider():
        calls["n"] += 1
        return [ProjectRef(id="p1", name="P1")]

    await orch.run_turn(_req("광고 만들어줘"), project_provider=provider)
    assert calls["n"] == 1
    assert captured["projects"][0].id == "p1"
