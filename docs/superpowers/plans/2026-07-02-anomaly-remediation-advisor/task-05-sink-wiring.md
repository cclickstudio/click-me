# Task 5: seam 분기 — `notifications.py` (⚠ 공통 성격 파일, 사전 공지)

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-02-anomaly-remediation-advisor.md` · 스펙: `docs/superpowers/specs/2026-07-02-anomaly-remediation-advisor-design.md`
> **실행 규칙**: 모든 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 .py 첫 줄 한국어 헤더 주석 · 🅰 소유 파일(detection/, approval.py, agents/diagnosis*) 수정 금지(읽기만).
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.

---

**Files:**
- Modify: `backend/domain/management/notifications.py:32-34` (`build_notification_sink`)
- Test: `test/backend/management/test_remediation_wiring.py`

⚠ notifications.py는 소유 미표기 파일 — 이 분기 1줄 추가를 🅰에게 공지(스펙 §7-2).
설정 `management_chat_notify_enabled`(getattr, 기본 False)로 기존 동작 완전 보존.

- [ ] **Step 1: 실패하는 테스트 작성**

`test/backend/management/test_remediation_wiring.py`:
```python
# sink seam 분기 테스트 — 설정 off면 기존 로그 sink, on이면 chat sink
from __future__ import annotations

from domain.management.notifications import LogNotificationSink, build_notification_sink
from domain.management.remediation.chat_sink import ChatNotificationSink


class _Off:
    management_chat_notify_enabled = False


class _On:
    management_chat_notify_enabled = True


def test_default_stays_log_sink():
    assert isinstance(build_notification_sink(_Off()), LogNotificationSink)


def test_enabled_returns_chat_sink_with_log_fallback():
    sink = build_notification_sink(_On())
    assert isinstance(sink, ChatNotificationSink)
    assert isinstance(sink._fallback, LogNotificationSink)  # noqa: SLF001 — 배선 검증
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_remediation_wiring.py -v`
Expected: FAIL — `test_enabled_returns_chat_sink_with_log_fallback`에서 LogNotificationSink 반환

- [ ] **Step 3: 분기 추가**

`backend/domain/management/notifications.py`의 `build_notification_sink`를 다음으로 교체:
```python
def build_notification_sink(settings) -> NotificationSink:
    """기본은 로그 sink. management_chat_notify_enabled면 채팅 sink(로그 폴백 내장)."""
    if getattr(settings, "management_chat_notify_enabled", False):
        from domain.management.remediation.chat_sink import ChatNotificationSink  # noqa: PLC0415

        return ChatNotificationSink(settings, fallback=LogNotificationSink())
    return LogNotificationSink()
```

- [ ] **Step 4: 통과 확인 + 기존 스케줄러 테스트 회귀 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_remediation_wiring.py -v`
Expected: PASS (2 tests)
Run: `cd backend && uv run pytest ../test/backend -k "scheduler or notification" -v`
Expected: 기존 테스트 전부 PASS (기본 off라 동작 불변)

- [ ] **Step 5: 커밋**

```bash
git add backend/domain/management/notifications.py test/backend/management/test_remediation_wiring.py
git commit -m "edit: 알림 sink seam에 채팅 sink 분기 추가(기본 off, 기존 동작 보존)"
```
