# 스코프 플러밍 — 신원 병합(_scope_context_ids) + gen 툴 org_id 변환·전달(hermetic).
import uuid

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
