# Task 4: 채팅 알림 sink — `remediation/chat_sink.py`

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-02-anomaly-remediation-advisor.md` · 스펙: `docs/superpowers/specs/2026-07-02-anomaly-remediation-advisor-design.md`
> **실행 규칙**: 모든 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 .py 첫 줄 한국어 헤더 주석 · 🅰 소유 파일(detection/, approval.py, agents/diagnosis*) 수정 금지(읽기만).
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.

---

**Files:**
- Create: `backend/domain/management/remediation/chat_sink.py`
- Test: `test/backend/management/test_remediation_chat_sink.py`

스팸 방지 판정표(§5) + composite 폴백(§7-1) + 배달 요약. 영속 접근은 store 포트로 분리해
단위 테스트는 fake로. `deliver()`가 결과를 반환하고 `notify()`(Protocol 준수)는 감싼다.

- [ ] **Step 1: 실패하는 테스트 작성**

`test/backend/management/test_remediation_chat_sink.py`:
```python
# chat sink 테스트 — 판정표 4분기·매핑 skip·race 방어·composite 폴백·요약·실패 격리
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from domain.management.remediation.chat_sink import ChatNotificationSink
from domain.management.remediation.contracts import ConsultResult


def _consult(status="anomaly", campaign_id="camp_1", anomaly="no_delivery"):
    from domain.management.remediation.advisor import build_options

    return ConsultResult(
        status=status,
        campaign_id=campaign_id,
        campaign_name="여름 캠페인",
        anomaly_type=anomaly if status == "anomaly" else "",
        diagnosed_at=datetime.now(UTC).isoformat(),
        message="테스트 메시지 ①②",
        options=build_options(anomaly) if status == "anomaly" else [],
    )


class Store:
    """세션·메시지 영속 포트 fake — last_read_at/기존 consult 시각을 시나리오별로 주입.

    latest_consult_at에 yield 지점(sleep 0)을 둬 race 테스트가 실제 인터리빙을 만들고,
    append가 latest_at을 갱신해 잠금 직렬화 후 두 번째 deliver가 dedup에 걸리게 한다.
    """

    def __init__(self, last_read_at=None, latest_at=None):
        self.last_read_at = last_read_at
        self.latest_at = latest_at
        self.appended: list[tuple[str, str, dict]] = []

    async def find_or_create_session(self, project_id, title):
        return "sess-1", self.last_read_at

    async def latest_consult_at(self, session_id, campaign_id, anomaly_type):
        await asyncio.sleep(0)  # 이벤트 루프 양보 — 잠금 없으면 이중 insert 재현
        return self.latest_at

    async def append_consult(self, session_id, content, meta):
        self.appended.append((session_id, content, meta))
        self.latest_at = datetime.now(UTC)


class FakeFallback:
    def __init__(self):
        self.calls: list[dict] = []

    async def notify(self, tenant_id, title, body, *, meta=None):
        self.calls.append({"tenant_id": tenant_id, "title": title, "meta": meta})


class _Settings:
    openai_api_key = None
    management_consult_cooldown_hours = 24


def _sink(store, *, resolver=None, consult_result="anomaly", fallback=None):
    async def _resolver(campaign_id, *, expected_org_id=None):
        return None if resolver == "none" else ("proj-1", "org-9")

    async def _consult_fn(settings, campaign_id, **kw):
        if consult_result == "fail":
            return None
        return _consult(status=consult_result)

    return ChatNotificationSink(
        _Settings(),
        fallback=fallback or FakeFallback(),
        store=store,
        resolver=_resolver,
        consult=_consult_fn,
    )


NOW = datetime.now(UTC)


@pytest.mark.asyncio
async def test_delivers_on_new_anomaly():
    store = Store()
    sink = _sink(store)
    out = await sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "delivered"
    assert len(store.appended) == 1
    _, content, meta = store.appended[0]
    assert meta["kind"] == "remediation_consult"
    assert meta["schema_version"] == 1
    assert meta["org_id"] == "org-9"  # tenant("global")가 아니라 해석된 org가 정본


@pytest.mark.asyncio
async def test_resolver_receives_expected_org_only_for_real_tenant():
    # fail-closed 대조 입력 검증 — "global"은 None, 실 org tenant는 그 org를 넘겨야 한다
    captured: list = []

    async def capturing_resolver(campaign_id, *, expected_org_id=None):
        captured.append(expected_org_id)
        return ("proj-1", "org-9")

    async def _consult_fn(settings, campaign_id, **kw):
        return _consult()

    sink = ChatNotificationSink(
        _Settings(),
        fallback=FakeFallback(),
        store=Store(),
        resolver=capturing_resolver,
        consult=_consult_fn,
    )
    await sink.deliver("global", "제목", "본문", meta={"campaign_id": "camp_1"})
    await sink.deliver("org-7", "제목", "본문", meta={"campaign_id": "camp_2"})
    assert captured == [None, "org-7"]


@pytest.mark.asyncio
async def test_concurrent_delivers_for_same_campaign_insert_once():
    # 스케줄 틱 + 수동 스캔 동시 배달 race — 모듈 잠금으로 정확히 1건만 insert
    store = Store()
    sink = _sink(store)
    o1, o2 = await asyncio.gather(
        sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"}),
        sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"}),
    )
    assert sorted([o1.status, o2.status]) == ["delivered", "skipped"]
    assert len(store.appended) == 1


@pytest.mark.asyncio
async def test_skips_when_no_project_mapping():
    fb = FakeFallback()
    sink = _sink(Store(), resolver="none", fallback=fb)
    out = await sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "skipped" and out.reason == "no_project_mapping"
    assert len(fb.calls) == 1  # composite 폴백 — 로그 sink로 위임


@pytest.mark.asyncio
async def test_skips_when_verified_normal():
    sink = _sink(Store(), consult_result="normal")
    out = await sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "skipped" and out.reason == "verified_normal"


@pytest.mark.asyncio
async def test_skips_when_bell_pending():
    # 기존 consult 있음 + 세션 미열람(last_read_at이 consult보다 과거/None) → 생략
    store = Store(last_read_at=None, latest_at=NOW - timedelta(hours=1))
    out = await _sink(store).deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "skipped" and out.reason == "bell_pending"


@pytest.mark.asyncio
async def test_skips_within_cooldown_after_read():
    latest = NOW - timedelta(hours=2)
    store = Store(last_read_at=NOW - timedelta(hours=1), latest_at=latest)  # 열람함
    out = await _sink(store).deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "skipped" and out.reason == "cooldown"


@pytest.mark.asyncio
async def test_followup_after_cooldown_with_changed_tone():
    latest = NOW - timedelta(hours=30)  # cooldown 24h 경과
    store = Store(last_read_at=NOW - timedelta(hours=25), latest_at=latest)
    out = await _sink(store).deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "delivered"
    _, content, _ = store.appended[0]
    assert "아직 계속" in content  # 후속 어조


@pytest.mark.asyncio
async def test_one_failure_does_not_break_loop_and_summary_aggregates():
    class BrokenStore(Store):
        async def append_consult(self, *a):
            raise RuntimeError("db down")

    fb = FakeFallback()
    sink = _sink(BrokenStore(), fallback=fb)
    out1 = await sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out1.status == "failed"  # 예외가 밖으로 안 나감
    assert len(fb.calls) == 1
    s = sink.summary()
    assert s["failed"][0]["campaign_id"] == "camp_1"
    assert s["delivered"] == 0
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_remediation_chat_sink.py -v`
Expected: FAIL — `ModuleNotFoundError: domain.management.remediation.chat_sink`

- [ ] **Step 3: 구현**

`backend/domain/management/remediation/chat_sink.py`:
```python
# 채팅 알림 sink — 이상 발견 시 advisor 상담 메시지를 프로젝트 세션에 먼저 심는다 (🅱)
"""NotificationSink 포트 준수(notify). deliver()는 배달 결과를 반환해 수동 스캔 요약에 쓴다.

스팸 방지 판정표(스펙 §5): 신규→통지 / 미열람→생략(bell_pending) / 열람+쿨다운 내→생략 /
열람+쿨다운 경과+이상 지속→후속 통지(어조 변경). 매핑 실패·저장 실패는 사용자에게 안 보이고
fallback(LogNotificationSink)으로 고정 스키마 이벤트만 남긴다. 1건 실패가 루프를 안 죽인다.
"""

from __future__ import annotations

import asyncio
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
            # JSONB 연산자 비의존(파이썬 필터) — SQLite 테스트·이식성 우선, 세션당 최근 50건이면 충분
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
                "notify_failed", tenant_id, title, body, campaign_id, "error",
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
        lock = _delivery_locks.setdefault(
            f"{campaign_id}:{consult.anomaly_type}", asyncio.Lock()
        )
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
                read = last_read_at if last_read_at is None or last_read_at.tzinfo else (
                    last_read_at.replace(tzinfo=UTC)
                )
                if read is None or read < latest_aware:
                    return DeliveryOutcome(
                        campaign_id=campaign_id, status="skipped", reason="bell_pending",
                        session_id=session_id,
                    )
                cooldown = timedelta(
                    hours=getattr(self._settings, "management_consult_cooldown_hours", 24)
                )
                if now - latest_aware < cooldown:
                    return DeliveryOutcome(
                        campaign_id=campaign_id, status="skipped", reason="cooldown",
                        session_id=session_id,
                    )
                followup = True

            content = (_FOLLOWUP_PREFIX if followup else "") + consult.message
            # meta의 org 정본 = 역추적으로 해석된 org(스케줄러 tenant "global" 오염 방지).
            await self._store.append_consult(
                session_id, content, consult.to_meta(org_id=resolved_org)
            )
        return DeliveryOutcome(
            campaign_id=campaign_id, status="delivered", session_id=session_id
        )

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
        try:
            await self._fallback.notify(
                tenant_id, title, body,
                meta={"campaign_id": campaign_id, "reason": reason},
            )
        except Exception:  # noqa: BLE001 — 폴백 실패까지는 삼킨다
            pass

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
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_remediation_chat_sink.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: 커밋**

```bash
git add backend/domain/management/remediation/chat_sink.py test/backend/management/test_remediation_chat_sink.py
git commit -m "add: 채팅 알림 sink — 판정표 스팸 방지·race 잠금·composite 폴백·배달 요약"
```
