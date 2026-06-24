# 슈퍼바이저 LLM 팩토리 — use_mock/키부재면 None(결정론 폴백 신호)(hermetic).
from types import SimpleNamespace

from domain.chat.adapters.llm_factory import build_supervisor_llm


def test_use_mock_returns_none():
    s = SimpleNamespace(
        use_mock=True,
        anthropic_api_key="sk-x",
        chat_orchestrator_provider="anthropic",
        chat_orchestrator_model="claude-sonnet-4-6",
        chat_orchestrator_temperature=0.3,
    )
    assert build_supervisor_llm(s) is None


def test_no_api_key_returns_none():
    s = SimpleNamespace(
        use_mock=False,
        anthropic_api_key=None,
        chat_orchestrator_provider="anthropic",
        chat_orchestrator_model="claude-sonnet-4-6",
        chat_orchestrator_temperature=0.3,
    )
    assert build_supervisor_llm(s) is None
