"""★③ Composition Root — 어댑터를 포트에 꽂는 유일한 지점."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.management.adapters.mock import MockAdPlatform

if TYPE_CHECKING:
    from domain.management.contracts.platform import AdPlatformReader, AdPlatformWriter


def build_reader(settings) -> AdPlatformReader:
    if getattr(settings, "use_mock", True):
        return MockAdPlatform()
    from domain.management.adapters.meta.reader import MetaAdsReader  # noqa: PLC0415

    return MetaAdsReader(settings)


def build_writer(settings) -> AdPlatformWriter:
    if getattr(settings, "use_mock", True):
        return MockAdPlatform()
    from domain.management.adapters.meta.writer import MetaAdsWriter  # noqa: PLC0415

    return MetaAdsWriter(settings)
