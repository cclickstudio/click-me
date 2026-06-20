"""실 SSR 통합(스모크) 테스트 — 옵트인. SsrSimulationScorer가 실제 SSRScorer와 맞물리는지.

키 없으면 skip(CI 안전), 키 있으나 임베딩 쿼터/레이트리밋이면 skip(계정 문제). 쿼터가
살아 있으면 precompute → conversion_intent 채점 → 0~1 정규화를 검증한다. 단위 보증은
test_regeneration_tools(fake SSR)가 담당.
"""

from __future__ import annotations

import asyncio

import pytest

from core.config import settings
from domain.management.agents.regeneration import CreativeCandidate
from domain.management.agents.regeneration_tools import SsrSimulationScorer

pytestmark = pytest.mark.skipif(
    not getattr(settings, "openai_api_key", None),
    reason="OPENAI_API_KEY 없음 — 실 SSR 통합 테스트는 옵트인",
)


def test_real_ssr_scores_candidate_in_unit_interval():
    import openai  # noqa: PLC0415

    from tools.simulation.ssr_scorer import SSRScorer  # noqa: PLC0415 — tools는 읽기 허용

    async def run():
        ssr = SSRScorer()
        try:
            await ssr.precompute_anchors()
            scorer = SsrSimulationScorer(ssr)  # 기본 dimension=conversion_intent
            score = await scorer.score(
                CreativeCandidate(candidate_id="c1", ad_copy="지금 구매하면 50% 할인, 오늘만!")
            )
        except (openai.RateLimitError, openai.APIStatusError) as exc:
            pytest.skip(f"OpenAI 쿼터/레이트리밋 — 계정 문제지 코드 회귀 아님: {exc}")
        assert 0.0 <= score <= 1.0

    asyncio.run(run())
