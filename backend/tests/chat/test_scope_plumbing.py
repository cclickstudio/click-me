# 스코프 플러밍 — 신원 병합(_scope_context_ids) + gen/sim 툴 org_id 변환·조회(hermetic).
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest

from domain.chat.graph.nodes import _scope_context_ids


def test_scope_context_ids_merges_identity():
    state = {
        "context_ids": {"simulation_id": "s1"},
        "organization_id": "org-1",
        "user_id": "u-1",
        "project_id": "p-1",
    }
    ctx = _scope_context_ids(state)
    assert ctx["simulation_id"] == "s1"  # 기존 엔티티 보존
    assert ctx["organization_id"] == "org-1"
    assert ctx["user_id"] == "u-1"
    assert ctx["project_id"] == "p-1"


def test_scope_context_ids_skips_missing():
    ctx = _scope_context_ids({"context_ids": {}, "organization_id": None})
    assert "organization_id" not in ctx and "user_id" not in ctx


@pytest.mark.asyncio
async def test_gen_list_converts_org_to_uuid(monkeypatch):
    seen = {}

    async def fake_list(limit=20, org_id=None):
        seen["limit"], seen["org_id"] = limit, org_id
        return [{"generation_id": "g1"}]

    import domain.generator.service.generator_service as gs

    monkeypatch.setattr(gs, "list_generations", fake_list)
    from domain.chat.adapters import gen_tools

    oid = str(uuid.uuid4())
    out = await gen_tools.gen_list(limit=5, org_id=oid)
    assert out["count"] == 1
    assert seen["org_id"] == uuid.UUID(oid)  # str→UUID 변환 확인(미변환 시 '없음' 오답 방지)
    assert seen["limit"] == 5


@pytest.mark.asyncio
async def test_gen_list_none_org_is_global(monkeypatch):
    seen = {}

    async def fake_list(limit=20, org_id=None):
        seen["org_id"] = org_id
        return []

    import domain.generator.service.generator_service as gs

    monkeypatch.setattr(gs, "list_generations", fake_list)
    from domain.chat.adapters import gen_tools

    await gen_tools.gen_list(limit=3)
    assert seen["org_id"] is None  # 무인증/내부 = 전역(스펙: mock 전역 보존)


# ---- 시뮬 목록/이름 조회(sim_list / sim_find_by_name) ----
def _sim_fake_row(**kw):
    base = {
        "id": "00000000-0000-0000-0000-000000000001",
        "status": "COMPLETED",
        "sample_size": 20,
        "created_at": datetime(2026, 1, 1, 12, 0, 0),
        "created_by_name": "홍길동",
        "ad_title": "여름 세일 광고",
        "click_intent_rate": 0.12,
        "ci_low": 0.10,
        "ci_high": 0.15,
        "purchase_intent_avg": 3.4,
        "trust_avg": 3.1,
        "effective_n": 18.0,
    }
    base.update(kw)
    return SimpleNamespace(**base)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows, captured):
        self._rows, self._captured = rows, captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, stmt, params=None):
        self._captured["params"] = params
        return _FakeResult(self._rows)


def _patch_sim_session(monkeypatch, rows, captured):
    from domain.chat.adapters import sim_tools

    monkeypatch.setattr(sim_tools, "AsyncSessionLocal", lambda: _FakeSession(rows, captured))


@pytest.mark.asyncio
async def test_sim_list_org_uuid_and_kpi_shape(monkeypatch):
    captured = {}
    rows = [_sim_fake_row(), _sim_fake_row(status="QUEUED", click_intent_rate=None)]
    _patch_sim_session(monkeypatch, rows, captured)
    from domain.chat.adapters import sim_tools

    oid = str(uuid.uuid4())
    out = await sim_tools.sim_list(limit=5, org_id=oid)
    assert out["count"] == 2
    assert captured["params"]["org"] == oid and captured["params"]["limit"] == 5
    # 완료 행: purchase_intent_avg(DB) → purchase_intent(키) 매핑·float
    assert out["simulations"][0]["kpi"]["purchase_intent"] == 3.4
    assert out["simulations"][0]["ad_title"] == "여름 세일 광고"
    # 미완(QUEUED): 집계 없음 → kpi null
    assert out["simulations"][1]["kpi"] is None


@pytest.mark.asyncio
async def test_sim_list_none_org_is_global(monkeypatch):
    captured = {}
    _patch_sim_session(monkeypatch, [], captured)
    from domain.chat.adapters import sim_tools

    out = await sim_tools.sim_list()
    assert captured["params"]["org"] is None
    assert out == {"simulations": [], "count": 0}


@pytest.mark.asyncio
async def test_sim_list_invalid_org():
    from domain.chat.adapters import sim_tools

    assert await sim_tools.sim_list(org_id="not-a-uuid") == {"error": "invalid_organization_id"}


@pytest.mark.asyncio
async def test_sim_find_by_name_pattern_and_query(monkeypatch):
    captured = {}
    _patch_sim_session(monkeypatch, [_sim_fake_row(ad_title="냐오옹 캠페인")], captured)
    from domain.chat.adapters import sim_tools

    out = await sim_tools.sim_find_by_name("냐오옹", org_id=str(uuid.uuid4()))
    assert captured["params"]["pattern"] == "%냐오옹%"
    assert out["count"] == 1 and out["query"] == "냐오옹"


@pytest.mark.asyncio
async def test_sim_find_by_name_empty_guard():
    from domain.chat.adapters import sim_tools

    assert await sim_tools.sim_find_by_name("  ") == {"error": "need_name"}
