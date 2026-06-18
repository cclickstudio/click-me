# 🅰 결정론 진단 — 기대 노출 0 구간에서 0 나눗셈 크래시 방지 회귀 테스트
"""코드리뷰 2026-06-17: expected_window==0(무예산·저페이싱 구간)일 때 deficit_ratio
계산이 ZeroDivisionError로 진단 파이프라인을 죽이던 버그를 막는다.
"""

import asyncio
from datetime import UTC, datetime

from domain.management.adapters.mock import MockAdPlatform
from domain.management.contracts.schemas import DiagnosisResult
from domain.management.detection.deterministic_dx import diagnose


def test_diagnose_handles_zero_expected_window_without_crash():
    day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    snaps = asyncio.run(MockAdPlatform().fetch_hourly_metrics("camp-x", day))
    expected = [0.0] * 24  # 기대 노출 0 → expected_window 0 (가드 없으면 크래시)

    result = diagnose("org-1", "camp-x", snaps, expected, [14, 15])

    assert isinstance(result, DiagnosisResult)
