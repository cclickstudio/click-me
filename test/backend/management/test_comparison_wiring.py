# 🅰 비교 서비스가 wiring(기본 mock) 경유로 크래시 없이 LiftResult를 내는지 검증
"""build_comparison_service(use_mock=True)는 MockAdPlatform을 ad reader로 꽂는다.

회귀: MockAdPlatform이 Port의 get_metrics를 구현하지 않아 compare()가 AttributeError로
죽던 버그(코드리뷰 2026-06-17)를 막는다. test_lift.py는 직접 만든 _FakeAd를 쓰므로
wiring 경로를 타지 않아 이 케이스를 잡지 못했다.
"""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from domain.management.comparison.schemas import LiftResult
from domain.management.wiring import build_comparison_service


def test_build_comparison_service_mock_compare_returns_lift():
    settings = SimpleNamespace(use_mock=True)
    svc = build_comparison_service(settings)
    result = asyncio.run(svc.compare("post-1", "camp-1", datetime.now(UTC)))
    assert isinstance(result, LiftResult)
    # mock 광고측은 누적 reach/impressions가 있어야(0 분모 회피) 비교가 성립
    assert result.paid.reach > 0


def test_build_prediction_reader_is_sim():
    from types import SimpleNamespace

    from domain.management.comparison.prediction_adapters import SimPredictionReader
    from domain.management.wiring import build_prediction_reader

    reader = build_prediction_reader(SimpleNamespace(use_mock=True))
    assert isinstance(reader, SimPredictionReader)
