# 테스트는 항상 mock 어댑터로 — 앱 런타임 기본값(USE_MOCK=false, 실데이터)과 무관하게 hermetic.
# 데모 ID(camp_1 등)는 실 Meta에 없어 실모드면 깨지고, 실 호출은 네트워크·비용·비결정이라 부적합.
# core.config Settings() 인스턴스화보다 먼저 set — load_dotenv(override=False)가 .env 값으로 안 덮음.
import os

os.environ["USE_MOCK"] = "true"

import pytest_asyncio
from dotenv import load_dotenv

load_dotenv()

from tools.simulation.ssr_scorer import SSRScorer


@pytest_asyncio.fixture(scope="session")
async def ssr_scorer():
    scorer = SSRScorer()
    await scorer.precompute_anchors()
    return scorer
