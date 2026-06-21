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
