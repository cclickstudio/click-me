# 능동 매니지먼트 스케줄러 — 주기 이상 스캔 → 알림 (APScheduler 인프로세스, 무SQS)
"""기존 in-process asyncio 잡 패턴과 일관(단일 EC2). 기본 off — 운영에서만 켠다.

run_scan은 1회 스캔이고 scanner 주입으로 테스트 가능하다. 기본 스캐너는 보수적으로 빈 결과를
낸다 — detection 파이프라인이 fault 주입형 데모라, 실 캠페인 campaign-queryable 진단이 준비되면
여기 연결한다(seam). 통지는 NotificationSink(기본 로그)로만 나간다.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from domain.management.notifications import NotificationSink, build_notification_sink

logger = logging.getLogger("clickme")

_Scanner = Callable[[object], Awaitable[list[dict] | tuple[list[dict], list[dict]]]]


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


_scheduler = None


def start_scheduler(settings) -> bool:
    """settings.management_scheduler_enabled일 때만 기동. 기본 off → 테스트/CI/dev 안전.

    기동했으면 True, (비활성이라) 건너뛰었으면 False.
    """
    global _scheduler  # noqa: PLW0603
    if not getattr(settings, "management_scheduler_enabled", False):
        return False
    if _scheduler is not None:
        return True
    from apscheduler.schedulers.asyncio import AsyncIOScheduler  # noqa: PLC0415

    sink = build_notification_sink(settings)
    interval = getattr(settings, "management_scan_interval_minutes", 60)

    async def _job() -> None:
        try:
            await run_scan(settings, sink)
        except Exception as exc:  # noqa: BLE001 — 잡 실패가 스케줄러를 죽이지 않게
            logger.warning("management 스캔 실패(무시): %s", exc)

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(_job, "interval", minutes=interval, id="mgmt-scan")
    _scheduler.start()
    logger.info("management 스케줄러 기동 — %d분 간격", interval)
    return True
