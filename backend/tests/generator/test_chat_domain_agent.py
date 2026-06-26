# generator 챗 어댑터 — s3_key→bytes→start_generation 트리거, started 핸드오프 반환
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

import domain.generator.chat.domain_agent as mod
from domain.generator.chat.domain_agent import GeneratorDomainAgent


@dataclass
class _Ctx:
    user_input: str
    attachments: tuple = ()
    results: dict = field(default_factory=dict)


def _step(action="generate", domain="generator", idx=1, inputs=None):
    return SimpleNamespace(id=f"{action}-{idx}", action=action, domain=domain, inputs=inputs or {})


@pytest.mark.asyncio
async def test_triggers_generation_and_returns_handoff(monkeypatch):
    seen = {}

    async def _fake_download(key):
        seen["downloaded"] = key
        return b"IMGBYTES"

    async def _fake_store(data):
        seen["stored"] = data
        return "temp-key-1"

    async def _fake_start(req):
        seen["req"] = req
        return "gen-123"

    monkeypatch.setattr(mod, "download_bytes", _fake_download)
    monkeypatch.setattr(mod, "store_temp_image", _fake_store)
    monkeypatch.setattr(mod, "start_generation", _fake_start)

    agent = GeneratorDomainAgent()
    ctx = _Ctx(
        user_input="이 텀블러로 광고 만들어줘",
        attachments=(SimpleNamespace(kind="image", s3_key="uploads/p.png"),),
    )
    out = await agent.ask(ctx, _step())

    assert seen["downloaded"] == "uploads/p.png"
    assert seen["stored"] == b"IMGBYTES"
    assert seen["req"].product_image_temp_key == "temp-key-1"
    assert seen["req"].product_description == "이 텀블러로 광고 만들어줘"
    assert seen["req"].target_audience == "전체"
    assert out == {
        "status": "started",
        "step_id": "generate-1",
        "domain": "generator",
        "action": "generate",
        "task_id": "gen-123",
        "stream_url": "/api/generator/generations/gen-123/stream",
        "ad_id": None,
    }


@pytest.mark.asyncio
async def test_no_attachment_skips_download(monkeypatch):
    async def _fail_download(key):  # 호출되면 실패
        raise AssertionError("download_bytes는 첨부 없으면 호출되면 안 됨")

    async def _fake_start(req):
        return "gen-9"

    monkeypatch.setattr(mod, "download_bytes", _fail_download)
    monkeypatch.setattr(mod, "start_generation", _fake_start)

    agent = GeneratorDomainAgent()
    out = await agent.ask(_Ctx(user_input="광고 만들어줘"), _step())
    assert out["task_id"] == "gen-9"
    assert out["status"] == "started"


@pytest.mark.asyncio
async def test_step_inputs_query_takes_priority_over_user_input(monkeypatch):
    seen = {}

    async def _fake_start(req):
        seen["req"] = req
        return "gen-2"

    monkeypatch.setattr(mod, "start_generation", _fake_start)

    agent = GeneratorDomainAgent()
    ctx = _Ctx(user_input="대화 전체 맥락")
    await agent.ask(ctx, _step(inputs={"query": "스텝 지정 설명"}))
    assert seen["req"].product_description == "스텝 지정 설명"  # step.inputs 우선
