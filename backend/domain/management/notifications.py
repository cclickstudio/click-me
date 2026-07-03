# 능동 알림 sink — 스케줄러가 감지한 이상을 사용자 채널로 통지(기본: 구조화 로그)
"""스케줄러(scheduler.py)가 이상을 발견하면 이 포트로 통지한다.

기본 어댑터는 로그(LogNotificationSink) — 외부 자격증명 없이 동작하고 테스트 가능하다.
SES/이메일·웹훅은 같은 NotificationSink 포트를 구현해 후속으로 붙인다(seam).
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger("clickme")


@runtime_checkable
class NotificationSink(Protocol):
    async def notify(
        self, tenant_id: str, title: str, body: str, *, meta: dict | None = None
    ) -> None: ...


class LogNotificationSink:
    """기본 sink — 구조화 로그로 통지. 기밀(예산·크리에이티브)은 본문에 싣지 않는다."""

    async def notify(
        self, tenant_id: str, title: str, body: str, *, meta: dict | None = None
    ) -> None:
        logger.info("[notify] tenant=%s · %s · %s", tenant_id, title, body)


def build_notification_sink(settings) -> NotificationSink:
    """채널 설정으로 sink 선택 — mock↔실연동 전환과 같은 Composition Root 원칙."""
    channel = getattr(settings, "management_notify_channel", "log")
    if channel == "chat":
        from domain.management.remediation.chat_sink import ChatNotificationSink  # noqa: PLC0415

        return ChatNotificationSink(settings, fallback=LogNotificationSink())
    if channel == "panel":
        from domain.management.remediation.panel_sink import PanelNotificationSink  # noqa: PLC0415

        return PanelNotificationSink(settings, fallback=LogNotificationSink())
    return LogNotificationSink()
