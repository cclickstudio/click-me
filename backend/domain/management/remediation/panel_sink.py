# 패널 알림 sink — 이상 발견 시 management_notifications에 저장(채팅 세션 안 건드림) (🅱)
"""chat_sink와 같은 판정표(스펙 §3), 신호만 세션 last_read_at → 알림 read_at/resolved_at.

deliver 순서: campaign_id → resolver → 판정(DB 조회만 — ignored/미열람/쿨다운) →
advisor.consult(통지 확정 후에만 — skip 경로 reader I/O 절약) → INSERT/후속 UPDATE + publish.
동시성: 모듈 잠금(dedup_key 단위, 단일 프로세스) + DB 부분 유니크 백스톱(IntegrityError →
skip(dedup_race) — race 창이 수 초라 payload 신선도 이득 없음, 미열람 행 덮어쓰기는 판정표 우회).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any

from domain.management.remediation import advisor as _advisor
from domain.management.remediation import broker
from domain.management.remediation.chat_sink import DeliveryOutcome
from domain.management.remediation.resolver import resolve_project

logger = logging.getLogger("clickme")

KIND = "management.remediation_consult"


class DedupRaceError(Exception):
    """부분 유니크 충돌 — 다른 워커가 먼저 INSERT했다."""


_delivery_locks: dict[str, asyncio.Lock] = {}


class PanelNotificationSink:
    def __init__(
        self,
        settings: Any,
        *,
        fallback: Any,
        store: Any = None,
        resolver: Any = None,
        consult: Any = None,
        clock: Any = None,
        publish: Any = None,
    ) -> None:
        if store is None:  # 조건부 임포트 — fake 주입 테스트·Task 순서(store는 Task 5)와 분리
            from domain.management.remediation.notification_store import (  # noqa: PLC0415
                DbNotificationStore,
            )

            store = DbNotificationStore()
        self._settings = settings
        self._fallback = fallback
        self._store = store
        self._resolve = resolver or resolve_project
        self._consult = consult or _advisor.consult
        self._clock = clock or (lambda: datetime.now(UTC))
        self._publish = publish or broker.publish
        self._outcomes: deque[DeliveryOutcome] = deque(maxlen=100)

    async def notify(
        self, tenant_id: str, title: str, body: str, *, meta: dict | None = None
    ) -> None:
        await self.deliver(tenant_id, title, body, meta=meta)

    async def deliver(
        self, tenant_id: str, title: str, body: str, *, meta: dict | None = None
    ) -> DeliveryOutcome:
        campaign_id = (meta or {}).get("campaign_id") or ""
        anomaly_hint = (meta or {}).get("anomaly_type") or ""
        try:
            outcome = await self._deliver(tenant_id, title, body, campaign_id, anomaly_hint)
        except Exception as exc:  # noqa: BLE001 — 1건 실패가 스캔 루프를 안 죽임
            await self._log_event(
                "panel_notify_failed",
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
        self, tenant_id: str, title: str, body: str, campaign_id: str, anomaly_hint: str
    ) -> DeliveryOutcome:
        if not campaign_id:
            await self._log_event(
                "panel_notify_skipped", tenant_id, title, body, "", "no_campaign_id"
            )
            return DeliveryOutcome(campaign_id="", status="skipped", reason="no_campaign_id")

        expected_org = None if tenant_id in ("", "global") else tenant_id
        resolved = await self._resolve(campaign_id, expected_org_id=expected_org)
        if resolved is None:
            await self._log_event(
                "panel_notify_skipped", tenant_id, title, body, campaign_id, "no_project_mapping"
            )
            return DeliveryOutcome(
                campaign_id=campaign_id, status="skipped", reason="no_project_mapping"
            )
        project_id, org_id = resolved

        # 힌트가 없으면 consult를 먼저 돌려 anomaly_type을 얻는다(구 스캐너 호환 폴백).
        consult = None
        anomaly = anomaly_hint
        if not anomaly:
            consult = await self._consult(self._settings, campaign_id)
            if consult is None:
                await self._log_event(
                    "panel_notify_skipped", tenant_id, title, body, campaign_id, "consult_failed"
                )
                return DeliveryOutcome(
                    campaign_id=campaign_id, status="skipped", reason="consult_failed"
                )
            if consult.status == "normal":
                return DeliveryOutcome(
                    campaign_id=campaign_id, status="skipped", reason="verified_normal"
                )
            anomaly = consult.anomaly_type

        dedup_key = f"{campaign_id}:{anomaly}"
        lock = _delivery_locks.setdefault(dedup_key, asyncio.Lock())
        async with lock:
            if await self._store.has_ignored(org_id, KIND, dedup_key):
                return DeliveryOutcome(campaign_id=campaign_id, status="skipped", reason="ignored")
            state = await self._store.open_state(org_id, KIND, dedup_key)
            now = self._clock()
            followup = False
            if state is not None:
                if state["read_at"] is None:
                    return DeliveryOutcome(
                        campaign_id=campaign_id, status="skipped", reason="bell_pending"
                    )
                last = state["last_notified_at"]
                last = last if last.tzinfo else last.replace(tzinfo=UTC)
                cooldown = timedelta(
                    hours=getattr(self._settings, "management_consult_cooldown_hours", 24)
                )
                if now - last < cooldown:
                    return DeliveryOutcome(
                        campaign_id=campaign_id, status="skipped", reason="cooldown"
                    )
                followup = True

            if consult is None:
                consult = await self._consult(self._settings, campaign_id)
                if consult is None:
                    await self._log_event(
                        "panel_notify_skipped",
                        tenant_id,
                        title,
                        body,
                        campaign_id,
                        "consult_failed",
                    )
                    return DeliveryOutcome(
                        campaign_id=campaign_id, status="skipped", reason="consult_failed"
                    )
                if consult.status == "normal":
                    if state is not None:
                        # 열려 있던 알림이 재검증에서 정상 — 다음 스캔 reconcile을 기다리지
                        # 않고 즉시 auto_normal로 닫는다(배지 진실성).
                        for o in await self._store.auto_resolve(org_id, KIND, [dedup_key], now):
                            self._publish(o)
                    return DeliveryOutcome(
                        campaign_id=campaign_id, status="skipped", reason="verified_normal"
                    )

            payload = consult.to_meta(org_id=org_id)
            payload["campaign_name"] = consult.campaign_name  # 패널 카드 표시용 확장
            payload["message"] = consult.message
            if followup:
                await self._store.followup(state["id"], payload, now)
            else:
                try:
                    await self._store.insert(
                        organization_id=org_id,
                        project_id=project_id,
                        campaign_id=campaign_id,
                        kind=KIND,
                        dedup_key=dedup_key,
                        payload=payload,
                        now=now,
                    )
                except DedupRaceError:
                    return DeliveryOutcome(
                        campaign_id=campaign_id, status="skipped", reason="dedup_race"
                    )
        self._publish(org_id)
        return DeliveryOutcome(campaign_id=campaign_id, status="delivered")

    async def reconcile(self, normals: list[dict]) -> int:
        """정상 확인된 (tenant, campaign, anomaly)의 미해결 알림을 auto_normal로 자동 해소.

        fail-closed: 스캐너가 '성공 조회 + 정상'으로 보고한 항목만 받는다(조회 실패 ≠ 정상).
        [무시] 완전 억제 정책의 오염 방지 — stale 알림을 사용자가 [무시]로 치우면
        미래의 진짜 재발까지 억제되므로, 정상화는 시스템이 치운다(스펙 §3).
        """
        count = 0
        by_tenant: dict[str, list[str]] = {}
        for n in normals:
            tenant = n.get("tenant_id") or ""
            key = f"{n.get('campaign_id')}:{n.get('anomaly_type')}"
            by_tenant.setdefault(tenant, []).append(key)
        for tenant, keys in by_tenant.items():
            org = None if tenant in ("", "global") else tenant
            orgs = await self._store.auto_resolve(org, KIND, keys, self._clock())
            for org_id in orgs:
                self._publish(org_id)
            count += len(orgs)
        return count

    async def _log_event(
        self, event, tenant_id, title, body, campaign_id, reason, *, error=None
    ) -> None:
        logger.info(
            '{"event": "management.%s", "campaign_id": "%s", "tenant": "%s", '
            '"reason": "%s", "error": "%s"}',
            event,
            campaign_id,
            tenant_id,
            reason,
            (error or "")[:120],
        )
        with contextlib.suppress(Exception):
            await self._fallback.notify(
                tenant_id, title, body, meta={"campaign_id": campaign_id, "reason": reason}
            )

    def summary(self) -> dict:
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
