# 매니지먼트 챗 tool의 실행 히스토리 적재 골든 — 캠페인 생성·조치가 롱텀 메모리에 남는지
"""sim/gen과 동일 seam(폼/카드 시점)에서 management도 실행 히스토리에 적재되는지 고정한다.

- record_execution을 monkeypatch로 캡처(DB 없이 검증) → feature_type·action·summary 계약 고정.
- project_id 없으면 적재 없음(spawn_record_execution 조기 반환).
- summary는 BM25(simple 토큰) 서치 대상이라 한글 라벨 포함을 검증한다.
"""

import asyncio

import pytest

from api.assistant.subagent_tools import build_chat_tools
from core.config import settings
from domain.chat import helpers, history

_PROJECT = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(scope="module")
def tools():
    return {t.name: t for t in build_chat_tools(settings)}


def _state(**kw):
    base = {"project_id": None, "session_id": "t", "user_id": None, "org_id": None, "messages": []}
    base.update(kw)
    return base


async def _drain_bg_tasks():
    """spawn_record_execution의 백그라운드 task가 끝날 때까지 대기."""
    for task in list(helpers._bg_tasks):
        await task


@pytest.fixture
def recorded(monkeypatch):
    calls: list[dict] = []

    async def _fake(project_id, feature_type, action, summary, payload=None, user_id=None):
        calls.append(
            {
                "project_id": project_id,
                "feature_type": feature_type,
                "action": action,
                "summary": summary,
                "payload": payload,
            }
        )

    monkeypatch.setattr(history, "record_execution", _fake)
    return calls


async def test_create_campaign_records_history(tools, recorded):
    await tools["create_campaign"].coroutine(
        state=_state(project_id=_PROJECT),
        tool_call_id="t1",
        name="여름 세일",
        objective="traffic",
        total_budget_krw=50000,
    )
    await _drain_bg_tasks()
    assert len(recorded) == 1
    row = recorded[0]
    assert row["feature_type"] == "management"
    # 폼 시점 = '요청' 기록 — 실행 확정(executor 기록)과 라벨로 구분해 거짓 양성을 막는다.
    assert row["action"] == "create_campaign_request"
    assert "캠페인 생성 요청" in row["summary"] and "여름 세일" in row["summary"]
    assert row["payload"]["total_budget_krw"] == 50000
    assert row["payload"]["stage"] == "request"


async def test_manage_campaign_records_korean_label(tools, recorded):
    await tools["manage_campaign"].coroutine(
        state=_state(project_id=_PROJECT),
        tool_call_id="t1",
        action="increase_budget",
        campaign_name="여름 세일",
        new_daily_budget_krw=30000,
    )
    await _drain_bg_tasks()
    assert len(recorded) == 1
    row = recorded[0]
    assert row["feature_type"] == "management"
    assert row["action"] == "increase_budget_request"  # 폼 시점 = '요청' 기록
    # 한국어 질의('예산 올린 거')가 BM25에 잡히도록 한글 라벨이 summary에 있어야 한다.
    assert "예산 증액" in row["summary"] and "여름 세일" in row["summary"]
    assert row["payload"]["stage"] == "request"


async def test_manage_campaign_invalid_action_not_recorded(tools, recorded):
    await tools["manage_campaign"].coroutine(
        state=_state(project_id=_PROJECT), tool_call_id="t1", action="explode"
    )
    await _drain_bg_tasks()
    assert recorded == []


async def test_no_project_no_record(tools, recorded):
    await tools["create_campaign"].coroutine(
        state=_state(), tool_call_id="t1", name="무프로젝트", objective="traffic"
    )
    await asyncio.sleep(0)
    assert recorded == []
