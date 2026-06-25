# 무키 폴백에서 진단 질문 → AskResult.diagnostic 채워짐(앱·DB·LLM 없이)
import pytest

from domain.management.assistant import tools as t
from domain.management.assistant.agent import build_management_agent
from domain.management.assistant.contracts import AskRequest, DiagnosticResult


class _Settings:
    use_mock = True
    gemini_api_key = None
    openai_api_key = None
    anthropic_api_key = None


@pytest.mark.asyncio
async def test_keyless_fallback_diagnosis_sets_diagnostic(monkeypatch):
    async def fake_diag(settings, campaign_id, tenant_id=None):
        return DiagnosticResult(diagnostic_status="unavailable", reason="테스트")

    monkeypatch.setattr(t, "live_diagnosis", fake_diag)
    ask = build_management_agent(_Settings())
    res = await ask(AskRequest(question="이 캠페인 진단해줘", campaign_id="camp_1"))
    assert res.diagnostic is not None
    assert res.diagnostic.diagnostic_status == "unavailable"
