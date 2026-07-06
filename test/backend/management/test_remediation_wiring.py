# sink seam 분기 테스트 — channel=log면 기존 로그 sink, channel=chat이면 chat sink
from __future__ import annotations

from domain.management.notifications import LogNotificationSink, build_notification_sink
from domain.management.remediation.chat_sink import ChatNotificationSink


class _Off:
    management_notify_channel = "log"


class _On:
    management_notify_channel = "chat"


def test_default_stays_log_sink():
    assert isinstance(build_notification_sink(_Off()), LogNotificationSink)


def test_enabled_returns_chat_sink_with_log_fallback():
    sink = build_notification_sink(_On())
    assert isinstance(sink, ChatNotificationSink)
    assert isinstance(sink._fallback, LogNotificationSink)  # noqa: SLF001 — 배선 검증
