# sink 채널 분기 테스트 — log(기본)/panel 2분기, chat 채널은 폐기(2026-07-09, 항상 센터로)
from __future__ import annotations


class _S:
    def __init__(self, channel):
        self.management_notify_channel = channel


def test_default_channel_is_log():
    from domain.management.notifications import LogNotificationSink, build_notification_sink

    assert isinstance(build_notification_sink(_S("log")), LogNotificationSink)


def test_discontinued_chat_channel_falls_back_to_log():
    # chat 채널 폐기(선제 알림은 항상 panel) — 구 설정이 남아도 log 폴백으로 안전.
    from domain.management.notifications import LogNotificationSink, build_notification_sink

    assert isinstance(build_notification_sink(_S("chat")), LogNotificationSink)


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
