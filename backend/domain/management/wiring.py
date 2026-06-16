"""★③ Composition Root — 어댑터를 포트에 꽂는 유일한 지점."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.management.contracts.platform import AdPlatformReader, AdPlatformWriter


def build_reader(settings) -> AdPlatformReader:
    if getattr(settings, "use_mock", True):
        # 지연 import — MockAdPlatform(🅰 소유)은 A-1 구현 전까지 빈 stub
        from domain.management.adapters.mock import MockAdPlatform  # noqa: PLC0415

        return MockAdPlatform()
    from domain.management.adapters.meta.reader import MetaAdsReader  # noqa: PLC0415

    return MetaAdsReader(settings)


def build_writer(settings) -> AdPlatformWriter:
    # mock/데모 writer = DRY_RUN MetaAdsWriter (실제 쓰기 없이 계약만 검증).
    # MockAdPlatform은 reader 전용이라 writer Port를 만족하지 못함 — 분기에서 제외.
    from domain.management.adapters.meta.writer import MetaAdsWriter  # noqa: PLC0415

    if getattr(settings, "use_mock", True):
        from domain.management.contracts.enums import ExecutionMode  # noqa: PLC0415

        return MetaAdsWriter(settings, mode=ExecutionMode.DRY_RUN)
    return MetaAdsWriter(settings)


def build_organic_reader(settings):
    """🅰 오가닉 인사이트 reader (OrganicInsightsReader) — use_mock 분기."""
    if getattr(settings, "use_mock", True):
        from domain.management.adapters.mock import MockOrganicReader  # noqa: PLC0415

        return MockOrganicReader()
    from domain.management.adapters.meta.organic_reader import MetaOrganicReader  # noqa: PLC0415

    return MetaOrganicReader(settings)


def build_comparison_service(settings):
    """🅰 오가닉↔광고 비교 서비스 — organic reader + ad reader 합성."""
    from domain.management.comparison.service.comparison_service import (  # noqa: PLC0415
        ComparisonService,
    )

    return ComparisonService(build_organic_reader(settings), build_reader(settings))
