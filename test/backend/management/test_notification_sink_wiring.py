# sink 채널 분기 테스트 — log(기본)/chat/panel 3분기 (Composition Root 단일 전환점)
from __future__ import annotations


class _S:
    def __init__(self, channel):
        self.management_notify_channel = channel


def test_default_channel_is_log():
    from domain.management.notifications import LogNotificationSink, build_notification_sink

    assert isinstance(build_notification_sink(_S("log")), LogNotificationSink)


def test_chat_channel_builds_chat_sink():
    from domain.management.notifications import build_notification_sink
    from domain.management.remediation.chat_sink import ChatNotificationSink

    assert isinstance(build_notification_sink(_S("chat")), ChatNotificationSink)


def test_panel_channel_builds_panel_sink():
    from domain.management.notifications import build_notification_sink
    from domain.management.remediation.panel_sink import PanelNotificationSink

    assert isinstance(build_notification_sink(_S("panel")), PanelNotificationSink)


def test_unknown_channel_falls_back_to_log_with_warning(caplog):
    import logging

    from domain.management.notifications import LogNotificationSink, build_notification_sink

    with caplog.at_level(logging.WARNING, logger="clickme"):
        sink = build_notification_sink(_S("chatt"))
    assert isinstance(sink, LogNotificationSink)
    assert any("management_notify_channel" in r.message for r in caplog.records)
