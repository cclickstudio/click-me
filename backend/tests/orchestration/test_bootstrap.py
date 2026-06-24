# bootstrap — 어댑터 계약 만족 + build_orchestration이 '등록'을 제대로 하는지(빌더는 stub)
import pytest

import api.orchestration.bootstrap as bootstrap
from api.orchestration.bootstrap import (
    MGMT_KEYWORDS,
    ManagementDomainAgent,
    build_orchestration,
)


def _patch_builder(monkeypatch):
    # 실제 management 에이전트 빌드를 우회 — composition root는 '등록'만 검증한다.
    # (실제 builder의 설정 필드 의존에서 테스트를 분리)
    async def _fake_ask(req):
        return req

    monkeypatch.setattr(bootstrap, "build_management_agent", lambda settings: _fake_ask)


@pytest.mark.asyncio
async def test_adapter_satisfies_domain_agent_contract():
    async def _ask(req):
        return f"ok:{req}"

    agent = ManagementDomainAgent(_ask)
    assert agent.domain == "management"
    assert await agent.ask("q") == "ok:q"


def test_build_orchestration_routes_management_keyword(monkeypatch):
    _patch_builder(monkeypatch)
    router, registry = build_orchestration(settings=object())
    assert router.route("이번 캠페인 예산 어때").domain == "management"
    assert registry.get("management") is not None
    assert registry.get("management").domain == "management"


def test_build_orchestration_non_keyword_is_default(monkeypatch):
    _patch_builder(monkeypatch)
    router, _ = build_orchestration(settings=object())
    assert router.route("안녕하세요").domain == "clio"


def test_mgmt_keywords_nonempty():
    assert "캠페인" in MGMT_KEYWORDS and len(MGMT_KEYWORDS) >= 10
