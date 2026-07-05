# 제너레이터 자동화 워커 — 최근 생성 품질 다이제스트(읽기 전용)를 주기 집계·적재
"""매니지먼트와 동일한 확장 seam으로 제너레이터를 크로스도메인 자동화에 편입한다.

- register_automation("generation", ...)로 공용 레지스트리에 등록(목록·문서화).
- run_quality_digest: 최근 완료 생성의 QA 통과 현황을 집계해 automation_runs에 남긴다
  (읽기 전용 — 생성·집행 write 없음, 원칙: 관측은 워커 자율).
- start_scheduler: settings.generator_scheduler_enabled일 때만 기동(기본 off, dev/CI 안전).

프론트 조회(GET /api/automation/runs?domain=generation)는 코드 수정 없이 이 적재분을 읽는다.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from core.automation import record_automation_run, register_automation
from core.db import AsyncSessionLocal
from core.models import AdGeneration

logger = logging.getLogger("clickme")

# 공용 레지스트리에 제너레이터 자동화 등록 — 매니지먼트와 같은 방식(확장 seam).
register_automation(
    "generation",
    "quality_digest",
    interval_minutes=1440,
    description="최근 24시간 완료 생성 건수·실패 현황 다이제스트(읽기 전용 집계) → automation_runs 적재",
)

_scheduler = None  # AsyncIOScheduler 싱글톤(프로세스 1개)


async def run_quality_digest(settings, window_hours: int = 24) -> bool:
    """최근 window_hours 완료/실패 생성 건수를 집계해 automation_runs에 남긴다(읽기 전용).

    집계할 게 없으면(완료 0건) 적재하지 않고 False. 실패는 조용히 무시(워커를 막지 않게).
    """
    try:
        # created_at 컬럼이 tz-naive라 naive UTC로 비교(경계 계산만 tz-aware로 안전하게).
        since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=window_hours)
        async with AsyncSessionLocal() as db:
            completed = await db.scalar(
                select(func.count())
                .select_from(AdGeneration)
                .where(AdGeneration.status == "completed", AdGeneration.created_at >= since)
            )
            failed = await db.scalar(
                select(func.count())
                .select_from(AdGeneration)
                .where(AdGeneration.status == "failed", AdGeneration.created_at >= since)
            )
        if not completed:
            return False  # 완료 생성 없음 → 다이제스트 생략
        total = completed + (failed or 0)
        rate = round(completed / total * 100) if total else 0
        await record_automation_run(
            domain="generation",
            job_name="quality_digest",
            title=f"생성 품질 다이제스트 — 최근 {window_hours}시간",
            body=f"완료 {completed}건 · 실패 {failed or 0}건 (성공률 {rate}%)",
            status="digest",
            payload={
                "window_hours": window_hours,
                "completed": completed,
                "failed": failed or 0,
                "success_rate": rate,
            },
        )
        return True
    except Exception as exc:  # noqa: BLE001 — 집계 실패가 워커/스케줄러를 죽이지 않게
        logger.warning("generator quality_digest 집계 실패(무시): %s", exc)
        return False


def start_scheduler(settings) -> bool:
    """settings.generator_scheduler_enabled일 때만 기동. 기본 off → 테스트/CI/dev 안전.

    기동했으면 True, (비활성이라) 건너뛰었으면 False.
    """
    global _scheduler  # noqa: PLW0603
    if not getattr(settings, "generator_scheduler_enabled", False):
        return False
    if _scheduler is not None:
        return True
    from apscheduler.schedulers.asyncio import AsyncIOScheduler  # noqa: PLC0415

    interval = getattr(settings, "generator_quality_digest_interval_minutes", 1440)

    async def _digest_job() -> None:
        try:
            await run_quality_digest(settings)
        except Exception as exc:  # noqa: BLE001 — 잡 실패가 스케줄러를 죽이지 않게
            logger.warning("generator 다이제스트 잡 실패(무시): %s", exc)

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(_digest_job, "interval", minutes=interval, id="gen-quality-digest")
    _scheduler.start()
    logger.info("generator 스케줄러 기동 — 품질 다이제스트 %d분", interval)
    return True
