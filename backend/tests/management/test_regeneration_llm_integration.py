"""실 LLM 통합(스모크) 테스트 — 옵트인. 단위 스위트(fake)와 분리한다.

실행 조건: OPENAI 키가 있을 때만. 키가 없으면 skip(=CI 안전), 키는 있으나 쿼터
소진/레이트리밋이면 역시 skip(=계정 문제지 코드 회귀가 아님). 쿼터가 살아 있으면
LLMCreativeGenerator → ChatOpenAI 실경로가 실제로 카피를 만드는지 검증한다.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from core.config import settings
from domain.management.agents.regeneration_tools import (
    MAX_CANDIDATES,
    LLMCreativeGenerator,
)
from domain.management.contracts.enums import AnomalyType
from domain.management.contracts.schemas import DiagnosisResult

pytestmark = pytest.mark.skipif(
    not getattr(settings, "openai_api_key", None),
    reason="OPENAI_API_KEY 없음 — 실 LLM 통합 테스트는 옵트인",
)


def _diagnosis() -> DiagnosisResult:
    return DiagnosisResult(
        diagnosis_id="it-1",
        tenant_id="org-1",
        campaign_id="camp-1",
        anomaly_type=AnomalyType.BID_LOSS,
        source="agent",
        hypothesis="입찰 경쟁 심화로 노출 급감",
        confidence=0.7,
        evidence_metrics={"cpm_krw": 14000, "win_rate": 0.25},
        metrics_as_of=datetime.now(UTC),
        status="confirmed",
    )


def test_real_llm_generates_parsable_candidates():
    """실 LLM이 진단을 받아 파싱 가능한 카피 후보를 만든다 (api_key는 Settings에서 주입)."""
    import openai  # noqa: PLC0415 — 옵트인 테스트에서만 필요

    generator = LLMCreativeGenerator(api_key=settings.openai_api_key)
    try:
        candidates = asyncio.run(generator.generate(_diagnosis(), 3))
    except (openai.RateLimitError, openai.APIStatusError) as exc:
        pytest.skip(f"OpenAI 쿼터/레이트리밋 — 계정 문제지 코드 회귀 아님: {exc}")

    assert 1 <= len(candidates) <= MAX_CANDIDATES
    for c in candidates:
        assert isinstance(c.ad_copy, str)
        assert c.ad_copy.strip()  # 빈 카피 아님
