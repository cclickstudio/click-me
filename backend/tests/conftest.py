import pytest
import pytest_asyncio
from tools.simulation.ssr_scorer import SSRScorer


@pytest_asyncio.fixture(scope="session")
async def ssr_scorer():
    scorer = SSRScorer()
    await scorer.precompute_anchors()
    return scorer
