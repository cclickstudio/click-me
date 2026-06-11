import os

import pytest

# 임베딩 API(OpenAI)를 실제 호출하는 통합 테스트.
# 키가 없는 환경(CI 등)에서는 건너뛴다. 로컬에서 OPENAI_API_KEY가 있으면 실행된다.
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY 미설정 — 임베딩 API 테스트 건너뜀",
)

GOLDEN_TEXT = """\
첫 주목: 중앙의 붉은 CTA 버튼이 먼저 눈에 들어왔다
첫 감정: 기대감과 약간의 의심이 동시에 들었다
본능 반응: 가격이 싸 보여서 일단 멈췄는데, 너무 좋아 보이면 의심부터 간다
지지 생각: 가격이 경쟁사보다 낮아 보임; 후기 수가 많음
반대 생각: 환불 정책 불명확; 브랜드 인지도 낮음
최종 태도: 관심은 있으나 더 검색이 필요한 상태
"""


@pytest.mark.asyncio
async def test_ssr_deterministic(ssr_scorer):
    result1 = await ssr_scorer.score(GOLDEN_TEXT)
    result2 = await ssr_scorer.score(GOLDEN_TEXT)
    for dim in result1:
        assert abs(result1[dim].mean - result2[dim].mean) < 1e-6


@pytest.mark.asyncio
async def test_ssr_distribution_realistic(ssr_scorer):
    result = await ssr_scorer.score(GOLDEN_TEXT)
    for dim, dist in result.items():
        assert dist.std > 0.01, f"{dim} std too small: {dist.std}"


@pytest.mark.asyncio
async def test_ssr_probs_sum_to_one(ssr_scorer):
    result = await ssr_scorer.score(GOLDEN_TEXT)
    for dim, dist in result.items():
        total = sum(dist.raw_probs)
        assert abs(total - 1.0) < 1e-5, f"{dim} probs sum={total}"


@pytest.mark.asyncio
async def test_score_ranges_valid(ssr_scorer):
    result = await ssr_scorer.score(GOLDEN_TEXT)
    assert -1.0 <= result["sentiment"].mean <= 1.0
    for dim in ["attention", "click_intent", "conversion_intent", "comprehension", "recall"]:
        assert 0.0 <= result[dim].mean <= 1.0
