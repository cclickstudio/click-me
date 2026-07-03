# 패널 알림 sink — 이상 발견 시 management_notifications에 저장(채팅 세션 안 건드림) (🅱)
"""판정 신호가 세션 last_read_at → 알림 read_at/resolved_at로 바뀐 것 외에는 chat_sink와
같은 판정표(스펙 §3). 단일 프로세스 잠금 + DB 부분 유니크 2중 방어."""

from __future__ import annotations

from typing import Any


class PanelNotificationSink:
    def __init__(self, settings: Any, *, fallback: Any, **kw: Any) -> None:
        self._settings = settings
        self._fallback = fallback

    async def notify(
        self, tenant_id: str, title: str, body: str, *, meta: dict | None = None
    ) -> None:
        raise NotImplementedError  # Task 4에서 구현
