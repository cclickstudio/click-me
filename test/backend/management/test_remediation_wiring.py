# sink seam 분기 테스트 — 선제 알림은 항상 센터(panel)로만, chat 채널 옵션은 폐기(2026-07-09)
from __future__ import annotations

from domain.management.notifications import LogNotificationSink, build_notification_sink


class _Off:
    management_notify_channel = "log"


class _Legacy:
    management_notify_channel = "chat"


def test_default_stays_log_sink():
    assert isinstance(build_notification_sink(_Off()), LogNotificationSink)


def test_discontinued_chat_channel_falls_back_to_log():
    # 구 chat 채널 설정이 남아 있어도 안전하게 log로 폴백한다(폐기 정책).
    assert isinstance(build_notification_sink(_Legacy()), LogNotificationSink)
