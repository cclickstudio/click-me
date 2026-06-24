# 생성 채팅 슬롯필링 에이전트 — 되묻기/프로젝트선택/트리거 결정론 검증(LLM 스텁)
"""키 없이 동작. 추출기·starter를 주입해 슬롯 충족 여부에 따른 분기를 검증한다."""

import uuid
from types import SimpleNamespace

import pytest

from core.assistant_contracts import Action, ProjectRef, SubagentRequest
from core.schemas import ChatMessage
from domain.generator.chat.contracts import ExtractedSlots
from domain.generator.chat.slot_agent import build_generation_chat_agent

_SETTINGS = SimpleNamespace(gemini_api_key=None)


def _extractor(slots: ExtractedSlots):
    async def _extract(_messages):
        return slots

    return _extract


def _starter_spy():
    calls: dict = {}

    async def _start(req, created_by=None):
        calls["req"] = req
        calls["created_by"] = created_by
        return "gen-123"

    return _start, calls


def _req(**kw):
    kw.setdefault("messages", [ChatMessage(role="user", content="광고 만들어줘")])
    return SubagentRequest(**kw)


@pytest.mark.asyncio
async def test_missing_slots_asks():
    slots = ExtractedSlots(product_name="나이키 운동화")  # 설명·타깃 누락
    starter, _ = _starter_spy()
    agent = build_generation_chat_agent(_SETTINGS, extractor=_extractor(slots), starter=starter)
    res = await agent(_req())
    assert res.action == Action.ASK
    assert "타깃" in res.message  # 누락 슬롯 되묻기


@pytest.mark.asyncio
async def test_all_slots_with_project_id_triggers():
    slots = ExtractedSlots(
        product_name="나이키", product_description="가벼운 러닝화", target_audience="20대 남성"
    )
    starter, calls = _starter_spy()
    agent = build_generation_chat_agent(_SETTINGS, extractor=_extractor(slots), starter=starter)
    uid = str(uuid.uuid4())
    res = await agent(_req(project_id="proj-1", user_id=uid))
    assert res.action == Action.TRIGGER
    assert res.started_event is not None
    assert res.started_event.job_id == "gen-123"
    assert "gen-123" in res.started_event.stream_url
    assert calls["req"].project_id == "proj-1"
    assert str(calls["created_by"]) == uid


@pytest.mark.asyncio
async def test_no_project_with_hint_matches_and_triggers():
    slots = ExtractedSlots(
        product_name="나이키",
        product_description="가벼운 러닝화",
        target_audience="20대 남성",
        project_hint="마케팅",
    )
    starter, calls = _starter_spy()
    agent = build_generation_chat_agent(_SETTINGS, extractor=_extractor(slots), starter=starter)
    projects = [ProjectRef(id="p1", name="마케팅 캠페인"), ProjectRef(id="p2", name="신제품")]
    res = await agent(_req(available_projects=projects))
    assert res.action == Action.TRIGGER
    assert calls["req"].project_id == "p1"
    assert calls["created_by"] is None  # 미인증 → None


@pytest.mark.asyncio
async def test_no_project_no_hint_asks_to_pick():
    slots = ExtractedSlots(
        product_name="나이키", product_description="가벼운 러닝화", target_audience="20대 남성"
    )
    starter, _ = _starter_spy()
    agent = build_generation_chat_agent(_SETTINGS, extractor=_extractor(slots), starter=starter)
    projects = [ProjectRef(id="p1", name="마케팅 캠페인"), ProjectRef(id="p2", name="신제품")]
    res = await agent(_req(available_projects=projects))
    assert res.action == Action.ASK
    assert "마케팅 캠페인" in res.message and "신제품" in res.message
