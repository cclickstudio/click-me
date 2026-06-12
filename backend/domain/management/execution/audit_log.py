"""🅱 감사 로그 — append-only (UPDATE/DELETE 코드 경로 없음, 게이트 #7).

7/8 스코프는 앱 레벨 insert-only — DB 트리거/권한 강제는 Won't (합의문서 §7).
영속화(audit_events 테이블)는 core/models.py 공동 설계 후 Sink 구현만 교체한다.
토큰·민감값은 기록 전에 마스킹 (게이트 #8 방어선의 일부 — 정본은 client.py 공동층).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final, Protocol
from uuid import uuid4

_SENSITIVE_KEY_TOKENS: Final[tuple[str, ...]] = (
    "token",
    "secret",
    "password",
    "authorization",
    "api_key",
    "credential",
)
MASKED: Final[str] = "***"


def mask_sensitive(payload: Mapping[str, Any]) -> dict[str, Any]:
    """민감 키워드가 포함된 키의 값을 재귀적으로 마스킹한다."""
    masked: dict[str, Any] = {}
    for key, value in payload.items():
        if any(token in key.lower() for token in _SENSITIVE_KEY_TOKENS):
            masked[key] = MASKED
        elif isinstance(value, Mapping):
            masked[key] = mask_sensitive(value)
        else:
            masked[key] = value
    return masked


@dataclass(frozen=True)
class AuditEvent:
    """감사 이벤트 1건 — 불변. proposal/approval/run ID로 전 과정을 연결한다."""

    category: str  # 예: "executor.rejected" / "executor.retry" / "executor.completed"
    tenant_id: str
    proposal_id: str | None = None
    approval_id: str | None = None
    run_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class AuditSink(Protocol):
    def append(self, event: AuditEvent) -> None: ...


class InMemoryAuditLog:
    """insert-only 인메모리 감사 로그 — 조회는 읽기 전용 튜플로만 노출."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        safe = dataclasses.replace(event, payload=mask_sensitive(event.payload))
        self._events.append(safe)

    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def for_approval(self, approval_id: str) -> tuple[AuditEvent, ...]:
        """게이트 #7 — 부분 실패·재시도 결과를 승인 단위로 추적."""
        return tuple(e for e in self._events if e.approval_id == approval_id)
