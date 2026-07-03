# Task 2: 설정 교체 + build_notification_sink 분기

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-03-remediation-hybrid-notification.md` · 스펙: `docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md` §3
> **실행 규칙**: 백엔드 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 파일 첫 줄 한국어 헤더 주석 · 🅰 소유 파일 수정 금지.
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.

---

**Files:**
- Modify: `backend/core/config.py` (119행 `management_chat_notify_enabled` 자리)
- Modify: `backend/domain/management/notifications.py:32-38`
- Create: `backend/domain/management/remediation/panel_sink.py` (골격 — 본 구현은 Task 4)
- Test: `test/backend/management/test_notification_sink_wiring.py` (신규)

- [ ] **Step 1: 기존 플래그 참조처 전수 확인**

```bash
grep -rn "management_chat_notify_enabled\|MANAGEMENT_CHAT_NOTIFY_ENABLED" backend test docs frontend --include="*.py" --include="*.md" --include="*.env*" -l
```
나온 파일 전부를 이 Task 안에서 함께 수정한다(문서는 이행 노트로: "`MANAGEMENT_CHAT_NOTIFY_ENABLED=true` → `MANAGEMENT_NOTIFY_CHANNEL=chat`").

- [ ] **Step 2: 실패 테스트 작성**

`test/backend/management/test_notification_sink_wiring.py`:

```python
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
```

- [ ] **Step 3: 실패 확인**

```bash
cd backend && uv run pytest ../test/backend/management/test_notification_sink_wiring.py -v
```
Expected: FAIL (`panel_sink` 모듈 없음 / channel 분기 없음)

- [ ] **Step 4: config.py 교체**

`backend/core/config.py` 119행 `management_chat_notify_enabled: bool = False`를 삭제하고 그 자리에:

```python
    management_notify_channel: str = "log"  # log | chat | panel — 이상 알림 배달 채널
    management_notify_sse_enabled: bool = True  # 알림 SSE(단일 프로세스 전제) — 멀티워커면 끈다
```

- [ ] **Step 5: build_notification_sink 분기 교체**

`backend/domain/management/notifications.py`의 `build_notification_sink` 전체 교체:

```python
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
```

- [ ] **Step 6: panel_sink 최소 골격 생성** (Task 4에서 본 구현)

`backend/domain/management/remediation/panel_sink.py`:

```python
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
```

- [ ] **Step 7: 통과 확인 + Ruff + 커밋**

```bash
cd backend && uv run pytest ../test/backend/management/test_notification_sink_wiring.py -v
cd backend && uv run ruff format . && uv run ruff check . --fix && cd ..
git add -A backend test docs
git commit -m "edit: 알림 채널 설정 일원화 — management_notify_channel(log|chat|panel) 분기"
```
