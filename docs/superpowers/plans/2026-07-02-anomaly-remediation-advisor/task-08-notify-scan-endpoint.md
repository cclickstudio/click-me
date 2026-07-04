# Task 8: 수동 스캔 엔드포인트 + 보호장치 — `management.py`

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-02-anomaly-remediation-advisor.md` · 스펙: `docs/superpowers/specs/2026-07-02-anomaly-remediation-advisor-design.md`
> **실행 규칙**: 모든 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 .py 첫 줄 한국어 헤더 주석 · 🅰 소유 파일(detection/, approval.py, agents/diagnosis*) 수정 금지(읽기만).
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.

---

**Files:**
- Modify: `backend/api/routers/management.py` (`/anomaly/scan` 엔드포인트 아래에 추가)
- Test: `test/backend/management/test_notify_scan_endpoint.py`

보호장치 4종(스펙 §6): 인증+org 스코프 / org별 동시 실행 잠금(409) / 쿨다운(429, 설정) /
통지 dedup은 sink가 담당. 응답에 배달 요약 포함. 스케줄러 스캐너 경로(run_scan) 재사용으로
mock 모드에서도 동작.

- [ ] **Step 1: 실패하는 테스트 작성**

`test/backend/management/test_notify_scan_endpoint.py`:
```python
# 수동 알림 스캔 엔드포인트 테스트 — 동시 409·쿨다운 429·배달 요약 응답
from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app(monkeypatch):
    from fastapi import FastAPI

    from api.routers import management as mgmt
    from core.auth import get_current_user
    from core.config import settings

    # 느린 스캔을 흉내내 동시성 창을 만든다 + org 해석·요약만 검증
    async def fake_run_scan(_settings, sink, *, scanner=None):
        await asyncio.sleep(0.05)
        out = await sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_x"})
        return 1 if out.status == "delivered" else 0

    async def fake_require_org_id(user, db):
        return "org-1"

    monkeypatch.setattr("domain.management.scheduler.run_scan", fake_run_scan)
    monkeypatch.setattr(mgmt, "_require_org_id", fake_require_org_id)
    monkeypatch.setattr(settings, "management_scan_manual_cooldown_seconds", 0, raising=False)
    # 잠금·쿨다운 전역 상태 초기화(테스트 간 격리)
    mgmt._notify_scan_locks.clear()
    mgmt._notify_scan_last.clear()

    # sink는 매핑 실패로 skip되도록(외부 의존 없는 결정론) — resolver가 None을 내는 게 기본
    application = FastAPI()
    application.include_router(mgmt.router, prefix="/api/management")
    application.dependency_overrides[get_current_user] = lambda: object()
    return application


@pytest.mark.asyncio
async def test_concurrent_second_request_gets_409(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r1, r2 = await asyncio.gather(
            client.post("/api/management/anomaly/notify-scan"),
            client.post("/api/management/anomaly/notify-scan"),
        )
    codes = sorted([r1.status_code, r2.status_code])
    assert codes == [200, 409]  # 정확히 1건 통과, 1건 잠금 거부


@pytest.mark.asyncio
async def test_cooldown_returns_429(app, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "management_scan_manual_cooldown_seconds", 60, raising=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r1 = await client.post("/api/management/anomaly/notify-scan")
        r2 = await client.post("/api/management/anomaly/notify-scan")
    assert r1.status_code == 200
    assert r2.status_code == 429


@pytest.mark.asyncio
async def test_response_contains_delivery_summary(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.post("/api/management/anomaly/notify-scan")
    body = r.json()
    assert set(body) >= {"scanned_findings", "delivered", "skipped", "failed"}


@pytest.mark.asyncio
async def test_different_orgs_do_not_block_each_other(app, monkeypatch):
    # org별 잠금 분리 — 서로 다른 org의 동시 요청은 양쪽 다 통과해야 한다(스펙 §10)
    from itertools import count

    from api.routers import management as mgmt

    seq = count()

    async def rotating_org(user, db):
        return f"org-{next(seq)}"

    monkeypatch.setattr(mgmt, "_require_org_id", rotating_org)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r1, r2 = await asyncio.gather(
            client.post("/api/management/anomaly/notify-scan"),
            client.post("/api/management/anomaly/notify-scan"),
        )
    assert [r1.status_code, r2.status_code] == [200, 200]


@pytest.mark.asyncio
async def test_scanner_is_org_scoped(app, monkeypatch):
    # org 스코프의 핵심 검증 — 스캐너가 org reader를 쓰고 findings tenant가 호출자 org인지
    from types import SimpleNamespace

    from api.routers import management as mgmt

    class FakeReader:
        async def list_campaigns(self):
            return [SimpleNamespace(campaign_id="camp_0", name="테스트")]

        async def get_metrics(self, campaign_id, now):
            return SimpleNamespace(impressions=0)

    captured: dict = {}

    async def capturing_run_scan(_settings, sink, *, scanner=None):
        assert scanner is not None  # 엔드포인트가 org 스캐너를 주입해야 한다
        captured["findings"] = await scanner(_settings)
        return len(captured["findings"])

    monkeypatch.setattr(mgmt, "build_reader", lambda s: FakeReader())
    monkeypatch.setattr("domain.management.scheduler.run_scan", capturing_run_scan)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.post("/api/management/anomaly/notify-scan")
    assert r.status_code == 200
    finding = captured["findings"][0]
    assert finding["tenant_id"] == "org-1"  # "global"이 아니라 호출자 org
    assert finding["meta"]["campaign_id"] == "camp_0"
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_notify_scan_endpoint.py -v`
Expected: FAIL — 404 (엔드포인트 없음)

- [ ] **Step 3: 엔드포인트 구현**

`backend/api/routers/management.py`의 `/anomaly/scan` 엔드포인트(`anomaly_scan` 함수) 바로 아래에 추가.

**파일 상단 import 체크리스트** (이미 있으면 생략 — grep으로 확인 후 없는 것만 추가):
- `import asyncio` · `import time`
- `import logging` + `logger = logging.getLogger("clickme")` (모듈 상단)
- `from datetime import UTC, datetime` — `_org_scanner`가 사용(기존 파일에 이미 있음, 확인만)
- `build_reader`(wiring import 목록에 기존 존재) · `_require_reader`(같은 파일에 정의) — 확인만
- `HTTPException`·`Depends`·`User`·`AsyncSession`·`get_db`·`get_current_user`·`settings` — 기존 존재

```python
# 수동 알림 스캔 — org별 인프로세스 잠금·쿨다운(단일 EC2 전제, 스펙 §6)
_notify_scan_locks: dict[str, asyncio.Lock] = {}
_notify_scan_last: dict[str, float] = {}


@router.post("/anomaly/notify-scan")
async def anomaly_notify_scan(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """이상 스캔 + 채팅 선제 알림 트리거(데모·수동) — 배달 요약 반환.

    org 스코프 end-to-end: reader(live면 로그인 org 연결, fail-closed)·findings tenant·
    resolver org 대조까지 전부 호출자 org로 묶인다. 예약(스케줄러) 경로만 settings 전역
    (단일 테넌트 데모 전제 — 문서화). 통지 스팸은 sink 판정표가 이중 방어.
    """
    org_id = await _require_org_id(user, db)
    key = str(org_id)

    cooldown = getattr(settings, "management_scan_manual_cooldown_seconds", 60)
    now_mono = time.monotonic()
    last = _notify_scan_last.get(key)
    if last is not None and now_mono - last < cooldown:
        raise HTTPException(429, f"{int(cooldown - (now_mono - last)) + 1}초 후 다시 시도하세요.")

    lock = _notify_scan_locks.setdefault(key, asyncio.Lock())
    if lock.locked():
        raise HTTPException(409, "이미 스캔이 진행 중입니다.")

    # org 스코프 reader — live는 로그인 org 연결(미연결 409), mock은 전역 mock.
    if getattr(settings, "use_mock", True):
        reader = build_reader(settings)
    else:
        reader = await _require_reader(db, org_id)

    async def _org_scanner(_settings) -> list[dict]:
        """스케줄러 기본 스캐너와 같은 신호(노출 0) — 단 reader·tenant가 org 스코프."""
        try:
            camps = await reader.list_campaigns()
        except Exception:  # noqa: BLE001 — 조회 실패는 빈 결과(다음 시도)
            return []
        findings: list[dict] = []
        now = datetime.now(UTC)
        for c in camps:
            try:
                m = await reader.get_metrics(c.campaign_id, now)
            except Exception:  # noqa: BLE001 — 캠페인 1건 실패가 스캔을 안 막음
                continue
            if m.impressions == 0:
                findings.append(
                    {
                        "tenant_id": key,  # 실제 org — sink의 fail-closed 대조 활성화
                        "title": f"게재 점검 — {c.name or c.campaign_id}",
                        "body": "활성 캠페인인데 노출이 0입니다.",
                        "meta": {"campaign_id": c.campaign_id},
                    }
                )
        return findings

    async with lock:
        _notify_scan_last[key] = time.monotonic()
        from functools import partial  # noqa: PLC0415

        from domain.management.notifications import LogNotificationSink  # noqa: PLC0415
        from domain.management.remediation.advisor import consult as _consult  # noqa: PLC0415
        from domain.management.remediation.chat_sink import ChatNotificationSink  # noqa: PLC0415
        from domain.management.scheduler import run_scan  # noqa: PLC0415

        sink = ChatNotificationSink(
            settings,
            fallback=LogNotificationSink(),
            consult=partial(_consult, reader=reader),  # 재검증도 같은 org reader로
        )
        count = await run_scan(settings, sink, scanner=_org_scanner)
        summary = sink.summary()

    # 고정 스키마 집계 로그 — 예약 실행은 건별 이벤트 로그로 관측(스케줄러 무변경 원칙).
    logger.info(
        '{"event": "management.scan_summary", "org": "%s", "findings": %d, "delivered": %d}',
        key,
        count,
        summary["delivered"],
    )
    return {"scanned_findings": count, **summary}
```

`logger`가 이 파일에 없으면 상단에 `logger = logging.getLogger("clickme")` + `import logging` 추가.

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_notify_scan_endpoint.py -v`
Expected: PASS (5 tests)

주의: 테스트의 run_scan monkeypatch 대상은 `domain.management.scheduler.run_scan`
(엔드포인트가 함수 내부에서 지연 import하므로 원본 모듈 패치가 유효).

- [ ] **Step 5: 커밋**

```bash
git add backend/api/routers/management.py test/backend/management/test_notify_scan_endpoint.py
git commit -m "add: 수동 알림 스캔 엔드포인트 — org 잠금·쿨다운·배달 요약"
```
