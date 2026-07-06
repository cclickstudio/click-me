# recall_history tool 골든 — 실행 히스토리 회수 도구의 포맷·빈결과 처리(DB 없이 검증)
"""tsvector 검색 자체는 Postgres 의존이라(SqlMemoryStore와 동일 사유) 여기선 도구 계약만 고정한다.

- project_id=None → search_execution_history 조기 반환 → "(수행 이력 없음)".
- search_execution_history를 canned rows로 monkeypatch → 라벨·시각·요약 포맷을 고정.
"""

import pytest

from api.assistant.subagent_tools import build_chat_tools
from core.config import settings
from domain.chat import history


@pytest.fixture(scope="module")
def tools():
    return {t.name: t for t in build_chat_tools(settings)}


def _state(**kw):
    base = {"project_id": None, "session_id": "t", "user_id": None, "org_id": None, "messages": []}
    base.update(kw)
    return base


def test_recall_history_registered(tools):
    assert "recall_history" in tools


def test_history_date_bound_parsing():
    from domain.chat.history import _KST, _history_date_bound

    assert _history_date_bound(None, end=False) is None
    assert _history_date_bound("not-a-date", end=False) is None
    start = _history_date_bound("2026-06-20", end=False)
    until = _history_date_bound("2026-06-20", end=True)
    assert start.tzinfo == _KST and start.day == 20
    assert (until - start).days == 1  # end=True → 다음날 0시(미만 비교)


async def test_recall_history_empty_without_project(tools):
    out = await tools["recall_history"].coroutine(state=_state(), query="시뮬")
    assert out == "(수행 이력 없음)"


async def test_recall_history_formats_rows(tools, monkeypatch):
    rows = [
        {
            "feature_type": "simulation",
            "action": "run_simulation",
            "summary": "시뮬 입력 제목 여름세일 카피 시원하게 카테고리 음료 목표 클릭",
            "payload": {},
            "executed_at": "2026-07-01T13:45:00",
        },
        {
            "feature_type": "generation",
            "action": "run_generation",
            "summary": "생성 입력 상품 바나나우유 설명 진한맛 타깃 20대 목표 인지",
            "payload": {},
            "executed_at": "2026-06-30T09:00:00",
        },
    ]

    async def _fake(project_id, query, k=5, feature_type=None, date_from=None, date_to=None):
        return rows

    monkeypatch.setattr(history, "search_execution_history", _fake)
    out = await tools["recall_history"].coroutine(state=_state(project_id="p1"), query="여름")
    lines = out.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("- [2026-07-01 13:45] 시뮬:")
    assert "여름세일" in lines[0]
    assert lines[1].startswith("- [2026-06-30 09:00] 생성:")
    assert "바나나우유" in lines[1]


async def test_recall_history_passes_filters(tools, monkeypatch):
    seen = {}

    async def _fake(project_id, query, k=5, feature_type=None, date_from=None, date_to=None):
        seen.update(feature_type=feature_type, date_from=date_from, date_to=date_to)
        return []

    monkeypatch.setattr(history, "search_execution_history", _fake)
    out = await tools["recall_history"].coroutine(
        state=_state(project_id="p1"),
        query="",
        feature_type="simulation",
        date_from="2026-06-20",
        date_to="2026-06-20",
    )
    assert out == "(수행 이력 없음)"
    assert seen == {
        "feature_type": "simulation",
        "date_from": "2026-06-20",
        "date_to": "2026-06-20",
    }
