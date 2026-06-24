# AgentRegistry — domain 문자열로 등록/조회
import pytest

from api.orchestration.registry import AgentRegistry


class _StubAgent:
    domain = "stub"

    async def ask(self, req):
        return req


def test_register_then_get_returns_agent():
    reg = AgentRegistry()
    agent = _StubAgent()
    reg.register(agent)
    assert reg.get("stub") is agent


def test_get_unknown_domain_returns_none():
    assert AgentRegistry().get("missing") is None


def test_duplicate_domain_registration_raises():
    reg = AgentRegistry()
    reg.register(_StubAgent())
    with pytest.raises(ValueError):
        reg.register(_StubAgent())


@pytest.mark.asyncio
async def test_registered_agent_ask_is_callable():
    reg = AgentRegistry()
    reg.register(_StubAgent())
    assert await reg.get("stub").ask("ping") == "ping"
