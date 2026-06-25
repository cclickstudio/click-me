# 채팅 추천 조치 승인→executor 실행(HITL) 글루 — use_mock 봉인(Meta 미접촉) 검증
"""POST /api/chat/approve 가 propose→approve→executor.execute 단일경로로 실행되는지 본다.

USE_MOCK=true(conftest)에서 실행모드는 MOCK으로 봉인 — 실제 Meta write 없이 글루만 검증한다.
"""

import pytest

from api.routers.chat import ApproveActionRequest, chat_approve


@pytest.mark.asyncio
async def test_chat_approve_tier1_executes_in_mock():
    """Tier 1(일시중지) 승인 → executor 실행, 모드는 MOCK 봉인."""
    res = await chat_approve(
        ApproveActionRequest(action_type="PAUSE_CAMPAIGN", campaign_id="camp_1")
    )
    assert res["execution_mode"] == "mock"  # use_mock 봉인 — Meta 미접촉
    assert res["action_type"] == "PAUSE_CAMPAIGN"
    assert res["campaign_id"] == "camp_1"
    assert res["status"]  # 빈 문자열 아님(실행 경로 통과)
    assert isinstance(res["result"], dict)


@pytest.mark.asyncio
async def test_chat_approve_tier3_executes_with_human_approver():
    """Tier 3(증액)도 사람 승인(approver_id)으로 실행 경로를 통과한다."""
    res = await chat_approve(
        ApproveActionRequest(
            action_type="INCREASE_BUDGET", campaign_id="camp_9", approver_id="user-42"
        )
    )
    assert res["execution_mode"] == "mock"
    assert res["action_type"] == "INCREASE_BUDGET"
    assert res["status"]


@pytest.mark.asyncio
async def test_chat_approve_defaults_campaign_when_missing():
    res = await chat_approve(ApproveActionRequest(action_type="PAUSE_CAMPAIGN"))
    assert res["campaign_id"] == "demo_campaign"
    assert res["execution_mode"] == "mock"
