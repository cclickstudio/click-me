# Task 6: 스캐너 anomaly 힌트 + run_scan reconcile

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-03-remediation-hybrid-notification.md` · 스펙: `docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md` §3
> **실행 규칙**: 백엔드 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 파일 첫 줄 한국어 헤더 주석 · 🅰 소유 파일 수정 금지.
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.

---

**Files:**
- Modify: `backend/domain/management/scheduler.py:21-60` (`_default_scanner`·`run_scan`)
- Modify: `backend/api/routers/management.py` (`_org_scanner`, 457행 부근)
- Test: `test/backend/management/test_scan_reconcile.py` (신규)

- [ ] **Step 1: 실패 테스트 작성**

`test/backend/management/test_scan_reconcile.py`:

```python
# run_scan 확장 테스트 — (findings, normals) 튜플 스캐너 + reconcile 호출·구형 스캐너 호환
from __future__ import annotations

import pytest

from domain.management.scheduler import run_scan


class SinkSpy:
    def __init__(self):
        self.notified, self.reconciled = [], []

    async def notify(self, tenant_id, title, body, *, meta=None):
        self.notified.append(meta)

    async def reconcile(self, normals):
        self.reconciled.append(normals)
        return len(normals)


class PlainSink:  # reconcile 없는 기존 sink (LogNotificationSink 상당)
    def __init__(self):
        self.notified = []

    async def notify(self, tenant_id, title, body, *, meta=None):
        self.notified.append(meta)


@pytest.mark.asyncio
async def test_tuple_scanner_delivers_and_reconciles():
    async def scanner(_s):
        findings = [{"tenant_id": "org-1", "title": "t", "body": "b",
                     "meta": {"campaign_id": "c1", "anomaly_type": "no_delivery"}}]
        normals = [{"tenant_id": "org-1", "campaign_id": "c2", "anomaly_type": "no_delivery"}]
        return findings, normals

    sink = SinkSpy()
    n = await run_scan(object(), sink, scanner=scanner)
    assert n == 1
    assert sink.notified[0]["anomaly_type"] == "no_delivery"
    assert sink.reconciled == [[{"tenant_id": "org-1", "campaign_id": "c2",
                                 "anomaly_type": "no_delivery"}]]


@pytest.mark.asyncio
async def test_legacy_list_scanner_still_works():
    async def scanner(_s):
        return [{"tenant_id": "g", "title": "t", "body": "b", "meta": {"campaign_id": "c1"}}]

    sink = PlainSink()
    assert await run_scan(object(), sink, scanner=scanner) == 1


@pytest.mark.asyncio
async def test_normals_without_reconcile_capable_sink_is_noop():
    async def scanner(_s):
        return [], [{"tenant_id": "g", "campaign_id": "c2", "anomaly_type": "no_delivery"}]

    sink = PlainSink()
    assert await run_scan(object(), sink, scanner=scanner) == 0  # 예외 없이 무시
```

- [ ] **Step 2: 실패 확인**

```bash
cd backend && uv run pytest ../test/backend/management/test_scan_reconcile.py -v
```
Expected: FAIL (튜플 언팩 없음)

- [ ] **Step 3: run_scan·기본 스캐너 수정**

`backend/domain/management/scheduler.py`의 `_default_scanner`와 `run_scan` 교체:

```python
async def _default_scanner(settings) -> tuple[list[dict], list[dict]]:
    """기본 스캐너 — 활성 캠페인 게재 점검. (findings, normals) 튜플 반환.

    normals는 '성공 조회 + 정상'으로 확인된 캠페인만(fail-closed — 조회 실패 ≠ 정상).
    reconcile이 이걸로 정상화된 미해결 알림을 auto_normal 자동 해소한다(스펙 §3).
    """
    from domain.management.assistant import tools as live_tools  # noqa: PLC0415

    data = await live_tools.live_campaigns(settings)
    if data.get("error"):
        return [], []  # 조회 실패는 통지도 reconcile도 안 함 — 다음 틱에 재시도
    findings: list[dict] = []
    normals: list[dict] = []
    for c in data.get("campaigns", []):
        cid = c.get("campaign_id")
        if c.get("impressions", 0) == 0:
            name = c.get("name") or cid or "?"
            findings.append(
                {
                    "tenant_id": "global",
                    "title": f"게재 점검 — {name}",
                    "body": "활성 캠페인인데 노출이 0입니다. 심사·예산·타깃을 점검하세요.",
                    "meta": {"campaign_id": cid, "anomaly_type": "no_delivery"},
                }
            )
        else:
            normals.append(
                {"tenant_id": "global", "campaign_id": cid, "anomaly_type": "no_delivery"}
            )
    return findings, normals


async def run_scan(settings, sink: NotificationSink, *, scanner: _Scanner | None = None) -> int:
    """이상 스캔 1회 → 통지 + (가능하면) 정상화 reconcile. 통지 건수 반환."""
    scan = scanner or _default_scanner
    out = await scan(settings)
    findings, normals = out if isinstance(out, tuple) else (out, [])
    for f in findings:
        await sink.notify(
            f.get("tenant_id", "global"),
            f.get("title", "anomaly"),
            f.get("body", ""),
            meta=f.get("meta"),
        )
    if normals and hasattr(sink, "reconcile"):
        await sink.reconcile(normals)
    if findings:
        logger.info("management 스캔 — %d건 통지", len(findings))
    return len(findings)
```

- [ ] **Step 4: 수동 스캔 `_org_scanner` 동일 확장**

`backend/api/routers/management.py`의 `_org_scanner`(457행 부근)를 (findings, normals) 튜플 반환으로 수정 — 기존 루프에 else 가지 추가:

```python
        async def _org_scanner(_settings) -> tuple[list[dict], list[dict]]:
            """스케줄러 기본 스캐너와 같은 신호(노출 0) — 단 reader·tenant가 org 스코프."""
            try:
                camps = await reader.list_campaigns()
            except Exception:  # noqa: BLE001 — 조회 실패는 빈 결과(다음 시도)
                return [], []
            findings: list[dict] = []
            normals: list[dict] = []
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
                            "meta": {
                                "campaign_id": c.campaign_id,
                                "anomaly_type": "no_delivery",
                            },
                        }
                    )
                else:
                    normals.append(
                        {
                            "tenant_id": key,
                            "campaign_id": c.campaign_id,
                            "anomaly_type": "no_delivery",
                        }
                    )
            return findings, normals
```

주의: 기존 `_org_scanner`의 findings meta에 `anomaly_type`이 없었다 — 이 수정으로 chat sink 경로도 동작 불변(chat_sink는 meta의 campaign_id만 읽음).

- [ ] **Step 4-1: 수동 스캔 sink를 채널 인지로 교체** (Task 2 품질 리뷰 발견 — 엔드포인트가 `ChatNotificationSink`를 직접 생성해 채널 설정을 무시함)

같은 엔드포인트의 sink 생성부(488행 부근, `sink = ChatNotificationSink(...)`)를 채널 분기로 교체 — org reader 주입(consult partial)은 유지:

```python
        from functools import partial  # noqa: PLC0415

        from domain.management.notifications import LogNotificationSink  # noqa: PLC0415
        from domain.management.remediation.advisor import consult as _consult  # noqa: PLC0415
        from domain.management.scheduler import run_scan  # noqa: PLC0415

        channel = getattr(settings, "management_notify_channel", "log")
        if channel == "panel":
            from domain.management.remediation.panel_sink import (  # noqa: PLC0415
                PanelNotificationSink,
            )

            sink = PanelNotificationSink(
                settings,
                fallback=LogNotificationSink(),
                consult=partial(_consult, reader=reader),  # 재검증도 같은 org reader로
            )
        else:
            # chat·log 공통 — 수동 스캔은 데모 트리거라 log 채널에서도 chat sink로 시연
            # 동작을 유지한다(기존 동작 보존). 예약 스케줄러만 channel을 엄격히 따른다.
            from domain.management.remediation.chat_sink import (  # noqa: PLC0415
                ChatNotificationSink,
            )

            sink = ChatNotificationSink(
                settings,
                fallback=LogNotificationSink(),
                consult=partial(_consult, reader=reader),
            )
        count = await run_scan(settings, sink, scanner=_org_scanner)
        summary = sink.summary()
```

테스트 추가(`test_scan_reconcile.py` 또는 `test_notify_scan_endpoint.py`에 1케이스): `management_notify_channel="panel"`로 monkeypatch 후 notify-scan 호출 시 PanelNotificationSink가 생성되는지 — sink 생성부를 seam으로 빼기 어렵다면 `monkeypatch.setattr`로 PanelNotificationSink를 스파이로 교체해 검증.

- [ ] **Step 5: 통과 확인 + 기존 스캔 테스트 회귀 + Ruff + 커밋**

```bash
cd backend && uv run pytest ../test/backend/management/test_scan_reconcile.py ../test/backend/management/test_notify_scan_endpoint.py -v
cd backend && uv run ruff format . && uv run ruff check . --fix && cd ..
git add backend/domain/management/scheduler.py backend/api/routers/management.py test/backend/management/test_scan_reconcile.py
git commit -m "edit: 스캐너 anomaly 힌트·normals 반환 + run_scan reconcile 연결"
```
