"""★③ Composition Root — 어댑터를 포트에 꽂는 유일한 지점."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.management.contracts.platform import AdPlatformReader, AdPlatformWriter
    from domain.management.execution.audit_log import AuditSink
    from domain.management.execution.executor import IdempotencyStore


def build_reader(settings) -> AdPlatformReader:
    if getattr(settings, "use_mock", True):
        # 지연 import — MockAdPlatform(🅰 소유)은 A-1 구현 전까지 빈 stub
        from domain.management.adapters.mock import MockAdPlatform  # noqa: PLC0415

        return MockAdPlatform()
    from domain.management.adapters.meta.reader import MetaAdsReader  # noqa: PLC0415

    return MetaAdsReader(settings)


def build_writer(settings) -> AdPlatformWriter:
    if getattr(settings, "use_mock", True):
        from domain.management.adapters.mock import MockAdPlatform  # noqa: PLC0415

        return MockAdPlatform()
    from domain.management.adapters.meta.writer import MetaAdsWriter  # noqa: PLC0415

    return MetaAdsWriter(settings)


def build_idempotency_store(settings) -> IdempotencyStore:
    """멱등 저장소 — use_mock이면 인메모리, 아니면 DB(idempotency_keys)."""
    if getattr(settings, "use_mock", True):
        from domain.management.execution.executor import (  # noqa: PLC0415
            InMemoryIdempotencyStore,
        )

        return InMemoryIdempotencyStore()
    from domain.management.execution.db_stores import DbIdempotencyStore  # noqa: PLC0415

    return DbIdempotencyStore()


def build_audit_sink(settings) -> AuditSink:
    """감사 sink — use_mock이면 인메모리, 아니면 DB(audit_events)."""
    if getattr(settings, "use_mock", True):
        from domain.management.execution.audit_log import InMemoryAuditLog  # noqa: PLC0415

        return InMemoryAuditLog()
    from domain.management.execution.db_stores import DbAuditSink  # noqa: PLC0415

    return DbAuditSink()
