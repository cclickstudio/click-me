# 챗 wiring 조립 — build_subagents·build_orchestrator(hermetic, use_mock).
from types import SimpleNamespace

import pytest

from domain.chat.contracts.agent_io import Route
from domain.chat.service.orchestrator import ChatOrchestratorService
from domain.chat.wiring import build_orchestrator, build_subagents


def _mock_settings():
    return SimpleNamespace(
        use_mock=True,
        anthropic_api_key=None,
        embedding_provider="mock",
        embedding_dim=1024,
        chat_orchestrator_provider="anthropic",
        chat_orchestrator_model="claude-sonnet-4-6",
        chat_orchestrator_temperature=0.3,
    )


def test_build_subagents_has_three_routes():
    subs = build_subagents(_mock_settings())
    assert set(subs.keys()) == {
        Route.MANAGEMENT.value,
        Route.SIMULATION.value,
        Route.GENERATION.value,
    }
    for route, sub in subs.items():
        assert sub.route == route  # 각 어댑터의 route 속성 == 키


@pytest.mark.asyncio
async def test_build_orchestrator_returns_service():
    # use_mock: checkpointer=MemorySaver, supervisor llm=None, executor=mock — DB 접촉 없이 조립.
    svc = await build_orchestrator(_mock_settings())
    assert isinstance(svc, ChatOrchestratorService)
