# Task 4: PanelNotificationSink 판정표 + reconcile

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-03-remediation-hybrid-notification.md` · 스펙: `docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md` §3
> **실행 규칙**: 백엔드 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 파일 첫 줄 한국어 헤더 주석 · 🅰 소유 파일 수정 금지.
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.

---

**Files:**
- Modify: `backend/domain/management/remediation/panel_sink.py` (Task 2 골격 → 본 구현)
- Test: `test/backend/management/test_remediation_panel_sink.py` (신규)

**설계 요점(스펙 §3):** deliver 순서 = campaign_id → resolver → **판정(DB 조회만)** → consult → 저장+publish. anomaly_type 힌트(meta)가 없으면 consult를 먼저 돌려 anomaly를 얻는 폴백. store는 주입 가능(chat_sink 테스트 패턴). `DbNotificationStore`는 Task 5에서 만들므로 **store 미주입 시에만 조건부 임포트**한다.

- [ ] **Step 1: 실패 테스트 작성**

`test/backend/management/test_remediation_panel_sink.py`:

```python
# panel sink 테스트 — 판정표(신규/미열람/쿨다운/후속/ignored)·race·reconcile·요약
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from domain.management.remediation.panel_sink import (
    KIND,
    DedupRaceError,
    PanelNotificationSink,
)


def _consult(status="anomaly", campaign_id="camp_1"):
    from domain.management.remediation.advisor import build_options
    from domain.management.remediation.contracts import ConsultResult

    return ConsultResult(
        status=status,
        campaign_id=campaign_id,
        campaign_name="여름 캠페인",
        anomaly_type="no_delivery" if status == "anomaly" else "",
        diagnosed_at=datetime.now(UTC).isoformat(),
        message="테스트 ①②",
        options=build_options("no_delivery") if status == "anomaly" else [],
    )


class Store:
    """알림 영속 포트 fake — open 상태·ignored 존재를 시나리오별로 주입."""

    def __init__(self, open_state=None, ignored=False, race=False):
        self._open = open_state  # None | {"id","read_at","last_notified_at"}
        self._ignored = ignored
        self._race = race
        self.inserted: list[dict] = []
        self.followups: list[tuple[str, dict]] = []
        self.auto_resolved: list[tuple] = []

    async def has_ignored(self, org_id, kind, dedup_key):
        return self._ignored

    async def open_state(self, org_id, kind, dedup_key):
        return self._open

    async def insert(self, **row):
        if self._race:
            raise DedupRaceError()
        self.inserted.append(row)
        return "notif-1"

    async def followup(self, notification_id, payload, now):
        self.followups.append((notification_id, payload))

    async def auto_resolve(self, org_id, kind, dedup_keys, now):
        self.auto_resolved.append((org_id, tuple(dedup_keys)))
        return ["org-9"] if dedup_keys else []


class FakeFallback:
    def __init__(self):
        self.calls = []

    async def notify(self, tenant_id, title, body, *, meta=None):
        self.calls.append(tenant_id)


class _Settings:
    management_consult_cooldown_hours = 24


NOW = datetime.now(UTC)


def _sink(store, *, consult_result="anomaly", resolver_none=False, published=None):
    async def _resolver(campaign_id, *, expected_org_id=None):
        return None if resolver_none else ("proj-1", "org-9")

    async def _consult_fn(settings, campaign_id, **kw):
        return None if consult_result == "fail" else _consult(status=consult_result)

    return PanelNotificationSink(
        _Settings(),
        fallback=FakeFallback(),
        store=store,
        resolver=_resolver,
        consult=_consult_fn,
        clock=lambda: NOW,
        publish=(published.append if published is not None else None),
    )


META = {"campaign_id": "camp_1", "anomaly_type": "no_delivery"}


@pytest.mark.asyncio
async def test_new_anomaly_inserts_and_publishes():
    store, published = Store(), []
    out = await _sink(store, published=published).deliver("t", "제목", "본문", meta=META)
    assert out.status == "delivered"
    row = store.inserted[0]
    assert row["dedup_key"] == "camp_1:no_delivery"
    assert row["kind"] == KIND
    assert row["payload"]["campaign_name"] == "여름 캠페인"  # 카드 표시용 확장 필드
    assert published == ["org-9"]


@pytest.mark.asyncio
async def test_ignored_skips_before_consult():
    calls = []

    async def counting_consult(settings, campaign_id, **kw):
        calls.append(1)
        return _consult()

    async def _resolver(campaign_id, *, expected_org_id=None):
        return ("proj-1", "org-9")

    sink = PanelNotificationSink(
        _Settings(),
        fallback=FakeFallback(),
        store=Store(ignored=True),
        resolver=_resolver,
        consult=counting_consult,
        clock=lambda: NOW,
    )
    out = await sink.deliver("t", "제목", "본문", meta=META)
    assert out.status == "skipped" and out.reason == "ignored"
    assert calls == []  # 판정 선행 — consult(reader I/O)를 안 탔다


@pytest.mark.asyncio
async def test_unread_open_row_skips_bell_pending():
    store = Store(open_state={"id": "n1", "read_at": None, "last_notified_at": NOW})
    out = await _sink(store).deliver("t", "제목", "본문", meta=META)
    assert out.status == "skipped" and out.reason == "bell_pending"


@pytest.mark.asyncio
async def test_read_within_cooldown_skips():
    state = {"id": "n1", "read_at": NOW, "last_notified_at": NOW - timedelta(hours=1)}
    out = await _sink(Store(open_state=state)).deliver("t", "제목", "본문", meta=META)
    assert out.status == "skipped" and out.reason == "cooldown"


@pytest.mark.asyncio
async def test_read_past_cooldown_followups():
    state = {"id": "n1", "read_at": NOW, "last_notified_at": NOW - timedelta(hours=25)}
    store, published = Store(open_state=state), []
    out = await _sink(store, published=published).deliver("t", "제목", "본문", meta=META)
    assert out.status == "delivered"
    assert store.followups and store.followups[0][0] == "n1"
    assert not store.inserted
    assert published == ["org-9"]


@pytest.mark.asyncio
async def test_dedup_race_skips():
    out = await _sink(Store(race=True)).deliver("t", "제목", "본문", meta=META)
    assert out.status == "skipped" and out.reason == "dedup_race"


@pytest.mark.asyncio
async def test_consult_normal_skips_verified_normal():
    out = await _sink(Store(), consult_result="normal").deliver("t", "제목", "본문", meta=META)
    assert out.status == "skipped" and out.reason == "verified_normal"


@pytest.mark.asyncio
async def test_followup_path_normal_closes_open_row():
    """열린 알림의 후속 경로에서 재검증이 정상이면 — skip에 그치지 않고 즉시 auto_normal."""
    state = {"id": "n1", "read_at": NOW, "last_notified_at": NOW - timedelta(hours=25)}
    store, published = Store(open_state=state), []
    out = await _sink(store, published=published, consult_result="normal").deliver(
        "t", "제목", "본문", meta=META
    )
    assert out.status == "skipped" and out.reason == "verified_normal"
    assert store.auto_resolved == [("org-9", ("camp_1:no_delivery",))]
    assert published == ["org-9"]


@pytest.mark.asyncio
async def test_no_hint_falls_back_to_consult_first():
    store = Store()
    out = await _sink(store).deliver("t", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "delivered"
    assert store.inserted[0]["dedup_key"] == "camp_1:no_delivery"  # consult 결과에서 유도


@pytest.mark.asyncio
async def test_no_mapping_skips_and_falls_back():
    fb = FakeFallback()
    sink = _sink(Store(), resolver_none=True)
    sink._fallback = fb
    out = await sink.deliver("t", "제목", "본문", meta=META)
    assert out.status == "skipped" and out.reason == "no_project_mapping"
    assert fb.calls  # 고정 스키마 폴백 로그 경로


@pytest.mark.asyncio
async def test_reconcile_auto_resolves_and_publishes():
    store, published = Store(), []
    sink = _sink(store, published=published)
    n = await sink.reconcile(
        [{"tenant_id": "org-9", "campaign_id": "camp_2", "anomaly_type": "no_delivery"}]
    )
    assert n == 1
    assert store.auto_resolved == [("org-9", ("camp_2:no_delivery",))]
    assert published == ["org-9"]


@pytest.mark.asyncio
async def test_summary_counts():
    store = Store()
    sink = _sink(store)
    await sink.deliver("t", "제목", "본문", meta=META)
    await sink.deliver("t", "제목", "본문", meta={})  # no_campaign_id
    s = sink.summary()
    assert s["delivered"] == 1
    assert s["skipped"][0]["reason"] == "no_campaign_id"
```

- [ ] **Step 2: 실패 확인**

```bash
cd backend && uv run pytest ../test/backend/management/test_remediation_panel_sink.py -v
```
Expected: FAIL (NotImplementedError / KIND·DedupRaceError 없음)

- [ ] **Step 3: 본 구현**

`backend/domain/management/remediation/panel_sink.py` 전체 교체:

```python
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
                "panel_notify_failed", tenant_id, title, body, campaign_id, "error",
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
                    return DeliveryOutcome(
                        campaign_id=campaign_id, status="skipped", reason="consult_failed"
                    )
                if consult.status == "normal":
                    if state is not None:
                        # 열려 있던 알림이 재검증에서 정상 — 다음 스캔 reconcile을 기다리지
                        # 않고 즉시 auto_normal로 닫는다(배지 진실성).
                        for o in await self._store.auto_resolve(
                            org_id, KIND, [dedup_key], now
                        ):
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
            event, campaign_id, tenant_id, reason, (error or "")[:120],
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
```

- [ ] **Step 4: 통과 확인 + Ruff + 커밋**

```bash
# wiring 테스트의 panel 분기(store 미주입 생성)는 Task 5의 store 생성 후 전체 회귀에서 확인
cd backend && uv run pytest ../test/backend/management/test_remediation_panel_sink.py -v
cd backend && uv run ruff format . && uv run ruff check . --fix && cd ..
git add backend/domain/management/remediation/panel_sink.py test/backend/management/test_remediation_panel_sink.py
git commit -m "add: PanelNotificationSink — 판정표 이식(판정 선행)·dedup race·reconcile"
```
