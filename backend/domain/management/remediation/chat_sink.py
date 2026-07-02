# 채팅 알림 sink — 이상 발견 시 advisor 상담 메시지를 프로젝트 세션에 먼저 심는다 (🅱)
"""NotificationSink 포트 준수(notify). deliver()는 배달 결과를 반환해 수동 스캔 요약에 쓴다.

스팸 방지 판정표(스펙 §5): 신규→통지 / 미열람→생략(bell_pending) / 열람+쿨다운 내→생략 /
열람+쿨다운 경과+이상 지속→후속 통지(어조 변경). 매핑 실패·저장 실패는 사용자에게 안 보이고
fallback(LogNotificationSink)으로 고정 스키마 이벤트만 남긴다. 1건 실패가 루프를 안 죽인다.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from domain.management.remediation import advisor as _advisor
from domain.management.remediation.resolver import resolve_project

logger = logging.getLogger("clickme")

_SESSION_TITLE = "⚠ 캠페인 이상 알림"
_FOLLOWUP_PREFIX = "지난번 알려드린 건이 아직 계속되고 있어요.\n\n"

#: (campaign_id:anomaly) 배달 잠금 — 스케줄 틱·수동 스캔이 겹쳐도 이중 insert 방지.
#: 모듈 레벨인 이유: sink 인스턴스가 경로마다 따로 생성돼 인스턴스 잠금은 무효.
#: 단일 프로세스 전제(단일 EC2) — 멀티워커는 DB 유니크 제약 필요(범위 밖).
_delivery_locks: dict[str, asyncio.Lock] = {}


@dataclass(frozen=True)
class DeliveryOutcome:
    campaign_id: str
    status: str  # delivered | skipped | failed
    reason: str | None = None
    session_id: str | None = None


class DbConsultStore:
    """실제 영속 — 세션 확보는 core 모델, 메시지 심기는 chat의 공개 함수 재사용."""

    async def find_or_create_session(
        self, project_id: str, title: str
    ) -> tuple[str, datetime | None]:
        from uuid import UUID  # noqa: PLC0415

        from sqlalchemy import select  # noqa: PLC0415

        from core.db import AsyncSessionLocal  # noqa: PLC0415
        from core.models import ChatSession  # noqa: PLC0415

        async with AsyncSessionLocal() as db:
            row = await db.execute(
                select(ChatSession)
                .where(ChatSession.project_id == UUID(project_id), ChatSession.title == title)
                .order_by(ChatSession.created_at.desc())
                .limit(1)
            )
            s = row.scalars().first()
            if s is None:
                s = ChatSession(project_id=UUID(project_id), title=title)
                db.add(s)
                await db.commit()
                await db.refresh(s)
            return str(s.id), s.last_read_at

    async def latest_consult_at(
        self, session_id: str, campaign_id: str, anomaly_type: str
    ) -> datetime | None:
        from uuid import UUID  # noqa: PLC0415

        from sqlalchemy import select  # noqa: PLC0415

        from core.db import AsyncSessionLocal  # noqa: PLC0415
        from core.models import ChatMessage  # noqa: PLC0415

        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == UUID(session_id))
                .order_by(ChatMessage.created_at.desc())
                .limit(50)
            )
            # JSONB 연산자 비의존(파이썬 필터) — SQLite 테스트·이식성 우선, 최근 50건이면 충분
            for m in rows.scalars():
                meta = m.meta or {}
                if (
                    meta.get("kind") == "remediation_consult"
                    and meta.get("campaign_id") == campaign_id
                    and meta.get("anomaly_type") == anomaly_type
                ):
                    return m.created_at
        return None

    async def append_consult(self, session_id: str, content: str, meta: dict) -> None:
        from domain.chat.history import append_widget_messages  # noqa: PLC0415

        saved = await append_widget_messages(session_id, [{"content": content, "meta": meta}])
        if not saved:
            raise RuntimeError("consult 메시지 저장 실패")


class ChatNotificationSink:
    def __init__(
        self,
        settings: Any,
        *,
        fallback: Any,
        store: Any = None,
        resolver: Any = None,
        consult: Any = None,
        clock: Any = None,
    ) -> None:
        self._settings = settings
        self._fallback = fallback
        self._store = store or DbConsultStore()
        self._resolve = resolver or resolve_project
        self._consult = consult or _advisor.consult
        self._clock = clock or (lambda: datetime.now(UTC))
        self._outcomes: list[DeliveryOutcome] = []

    # NotificationSink 포트 준수 — 스케줄러는 이 시그니처만 안다.
    async def notify(
        self, tenant_id: str, title: str, body: str, *, meta: dict | None = None
    ) -> None:
        await self.deliver(tenant_id, title, body, meta=meta)

    async def deliver(
        self, tenant_id: str, title: str, body: str, *, meta: dict | None = None
    ) -> DeliveryOutcome:
        campaign_id = (meta or {}).get("campaign_id") or ""
        try:
            outcome = await self._deliver(tenant_id, title, body, campaign_id)
        except Exception as exc:  # noqa: BLE001 — 1건 실패가 스캔 루프를 안 죽임
            await self._log_event(
                "notify_failed",
                tenant_id,
                title,
                body,
                campaign_id,
                "error",
                error=f"{type(exc).__name__}: {exc}",
            )
            outcome = DeliveryOutcome(campaign_id=campaign_id, status="failed", reason="error")
        self._outcomes.append(outcome)
        return outcome

    async def _deliver(
        self, tenant_id: str, title: str, body: str, campaign_id: str
    ) -> DeliveryOutcome:
        if not campaign_id:
            await self._log_event("notify_skipped", tenant_id, title, body, "", "no_campaign_id")
            return DeliveryOutcome(campaign_id="", status="skipped", reason="no_campaign_id")

        # 스케줄러 tenant("global")는 org 미상 — 실제 org tenant일 때만 fail-closed 대조.
        expected_org = None if tenant_id in ("", "global") else tenant_id
        resolved = await self._resolve(campaign_id, expected_org_id=expected_org)
        if resolved is None:
            await self._log_event(
                "notify_skipped", tenant_id, title, body, campaign_id, "no_project_mapping"
            )
            return DeliveryOutcome(
                campaign_id=campaign_id, status="skipped", reason="no_project_mapping"
            )
        project_id, resolved_org = resolved

        consult = await self._consult(self._settings, campaign_id)
        if consult is None:
            await self._log_event(
                "notify_skipped", tenant_id, title, body, campaign_id, "consult_failed"
            )
            return DeliveryOutcome(
                campaign_id=campaign_id, status="skipped", reason="consult_failed"
            )
        if consult.status == "normal":
            return DeliveryOutcome(
                campaign_id=campaign_id, status="skipped", reason="verified_normal"
            )

        # race 방어 — dedup 판정과 insert를 (campaign, anomaly) 단위로 직렬화.
        lock = _delivery_locks.setdefault(f"{campaign_id}:{consult.anomaly_type}", asyncio.Lock())
        async with lock:
            session_id, last_read_at = await self._store.find_or_create_session(
                project_id, _SESSION_TITLE
            )
            now = self._clock()
            latest = await self._store.latest_consult_at(
                session_id, campaign_id, consult.anomaly_type
            )
            followup = False
            if latest is not None:
                latest_aware = latest if latest.tzinfo else latest.replace(tzinfo=UTC)
                read = (
                    last_read_at
                    if last_read_at is None or last_read_at.tzinfo
                    else (last_read_at.replace(tzinfo=UTC))
                )
                if read is None or read < latest_aware:
                    return DeliveryOutcome(
                        campaign_id=campaign_id,
                        status="skipped",
                        reason="bell_pending",
                        session_id=session_id,
                    )
                cooldown = timedelta(
                    hours=getattr(self._settings, "management_consult_cooldown_hours", 24)
                )
                if now - latest_aware < cooldown:
                    return DeliveryOutcome(
                        campaign_id=campaign_id,
                        status="skipped",
                        reason="cooldown",
                        session_id=session_id,
                    )
                followup = True

            content = (_FOLLOWUP_PREFIX if followup else "") + consult.message
            # meta의 org 정본 = 역추적으로 해석된 org(스케줄러 tenant "global" 오염 방지).
            await self._store.append_consult(
                session_id, content, consult.to_meta(org_id=resolved_org)
            )
        return DeliveryOutcome(campaign_id=campaign_id, status="delivered", session_id=session_id)

    async def _log_event(
        self,
        event: str,
        tenant_id: str,
        title: str,
        body: str,
        campaign_id: str,
        reason: str,
        *,
        session_id: str | None = None,
        error: str | None = None,
    ) -> None:
        """고정 스키마 관측 이벤트 — 운영 디버깅용 필드 포함(기밀·예산·크리에이티브 제외)."""
        logger.info(
            '{"event": "management.%s", "campaign_id": "%s", "tenant": "%s", '
            '"reason": "%s", "session_id": "%s", "error": "%s"}',
            event,
            campaign_id,
            tenant_id,
            reason,
            session_id or "",
            (error or "")[:120],
        )
        with contextlib.suppress(Exception):  # 폴백 실패까지는 삼킨다
            await self._fallback.notify(
                tenant_id,
                title,
                body,
                meta={"campaign_id": campaign_id, "reason": reason},
            )

    def summary(self) -> dict:
        """수동 스캔 응답용 배달 요약 — {delivered, skipped[], failed[]}."""
        return {
            "delivered": sum(1 for o in self._outcomes if o.status == "delivered"),
            "skipped": [
                {"campaign_id": o.campaign_id, "reason": o.reason}
                for o in self._outcomes
                if o.status == "skipped"
            ],
            "failed": [
                {"campaign_id": o.campaign_id, "reason": o.reason}
                for o in self._outcomes
                if o.status == "failed"
            ],
        }
