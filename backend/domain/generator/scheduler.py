# 제너레이터 자동화 워커 — 품질 다이제스트·멈춘 생성 감지(읽기 전용)를 주기 집계·적재
"""매니지먼트와 동일한 확장 seam으로 제너레이터를 크로스도메인 자동화에 편입한다.

- register_automation("generation", ...)로 공용 레지스트리에 등록(목록·문서화).
- run_quality_digest: 최근 완료 생성의 QA 통과 현황을 집계해 automation_runs에 남긴다
  (읽기 전용 — 생성·집행 write 없음, 원칙: 관측은 워커 자율).
- run_stuck_scan: pending/running인데 임계 시간 넘게 갱신 없는 생성(프로세스 사망 등)을
  감지해 automation_runs에 남긴다(읽기 전용 — status 정정 write는 하지 않음).
- start_scheduler: settings.generator_scheduler_enabled일 때만 기동(기본 off, dev/CI 안전).

프론트 조회(GET /api/automation/runs?domain=generation)는 코드 수정 없이 이 적재분을 읽는다.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from core.automation import record_automation_run, register_automation
from core.db import AsyncSessionLocal
from core.models import AdGeneration, AdGenerationCandidate

logger = logging.getLogger("clickme")

# 공용 레지스트리에 제너레이터 자동화 등록 — 매니지먼트와 같은 방식(확장 seam).
register_automation(
    "generation",
    "quality_digest",
    interval_minutes=1440,
    description="최근 24시간 완료 생성 건수·실패 현황 다이제스트(읽기 전용 집계) → automation_runs 적재",
)
register_automation(
    "generation",
    "stuck_scan",
    interval_minutes=30,
    description="pending/running인데 임계 시간 넘게 갱신 없는 생성 감지(읽기 전용) → automation_runs 적재",
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
            # 후보(시안) 레벨 QA 통과율 — qa_passed는 QA Harness 판정 결과(Boolean).
            qa_total = await db.scalar(
                select(func.count())
                .select_from(AdGenerationCandidate)
                .where(AdGenerationCandidate.created_at >= since)
            )
            qa_passed = await db.scalar(
                select(func.count())
                .select_from(AdGenerationCandidate)
                .where(
                    AdGenerationCandidate.created_at >= since,
                    AdGenerationCandidate.qa_passed.is_(True),
                )
            )
        if not completed:
            return False  # 완료 생성 없음 → 다이제스트 생략
        total = completed + (failed or 0)
        rate = round(completed / total * 100) if total else 0
        qa_note = f" · QA 통과 {qa_passed or 0}/{qa_total}" if qa_total else ""
        await record_automation_run(
            domain="generation",
            job_name="quality_digest",
            title=f"생성 품질 다이제스트 — 최근 {window_hours}시간",
            body=f"완료 {completed}건 · 실패 {failed or 0}건 (성공률 {rate}%){qa_note}",
            status="digest",
            payload={
                "window_hours": window_hours,
                "completed": completed,
                "failed": failed or 0,
                "success_rate": rate,
                "qa_passed": qa_passed or 0,
                "qa_total": qa_total or 0,
            },
        )
        return True
    except Exception as exc:  # noqa: BLE001 — 집계 실패가 워커/스케줄러를 죽이지 않게
        logger.warning("generator quality_digest 집계 실패(무시): %s", exc)
        return False


async def run_stuck_scan(settings) -> int:
    """pending/running인데 임계 시간 넘게 갱신 없는 생성을 감지해 automation_runs에 남긴다.

    인프로세스 asyncio 잡 특성상 프로세스가 죽으면 생성이 pending/running에 영구 고정된다.
    감지·기록만 하고 status 정정 write는 하지 않는다(관측은 워커 자율, 정정은 별도 논의).
    감지 건수를 반환. 실패는 조용히 무시(워커를 막지 않게).
    """
    try:
        threshold = getattr(settings, "generator_stuck_threshold_minutes", 30)
        # updated_at 컬럼이 tz-naive라 naive UTC로 비교(quality_digest와 동일 패턴).
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=threshold)
        async with AsyncSessionLocal() as db:
            rows = (
                (
                    await db.execute(
                        select(AdGeneration).where(
                            AdGeneration.status.in_(("pending", "running")),
                            AdGeneration.updated_at < cutoff,
                        )
                    )
                )
                .scalars()
                .all()
            )
        for generation in rows:
            name = (generation.input or {}).get("product_name") or "이름 없는 생성"
            await record_automation_run(
                domain="generation",
                job_name="stuck_scan",
                title="생성 파이프라인 멈춤 감지",
                body=f"'{name}' 생성이 {threshold}분 넘게 {generation.status} 상태예요. "
                "서버 재시작 등으로 중단됐을 수 있어요 — 다시 생성해 주세요.",
                project_id=str(generation.project_id) if generation.project_id else None,
                status="finding",
                severity="warning",
                payload={
                    "generation_id": str(generation.id),
                    "status": generation.status,
                    "threshold_minutes": threshold,
                },
                # 같은 생성이 계속 멈춰 있어도 미해결 1행 유지(재통지 방지 — dedup 계약)
                dedup_key=f"gen-stuck:{generation.id}",
            )
        return len(rows)
    except Exception as exc:  # noqa: BLE001 — 감지 실패가 워커/스케줄러를 죽이지 않게
        logger.warning("generator stuck_scan 감지 실패(무시): %s", exc)
        return 0


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
    stuck_interval = getattr(settings, "generator_stuck_scan_interval_minutes", 30)

    async def _digest_job() -> None:
        try:
            await run_quality_digest(settings)
        except Exception as exc:  # noqa: BLE001 — 잡 실패가 스케줄러를 죽이지 않게
            logger.warning("generator 다이제스트 잡 실패(무시): %s", exc)

    async def _stuck_job() -> None:
        try:
            await run_stuck_scan(settings)
        except Exception as exc:  # noqa: BLE001 — 잡 실패가 스케줄러를 죽이지 않게
            logger.warning("generator stuck 스캔 잡 실패(무시): %s", exc)

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(_digest_job, "interval", minutes=interval, id="gen-quality-digest")
    _scheduler.add_job(_stuck_job, "interval", minutes=stuck_interval, id="gen-stuck-scan")
    _scheduler.start()
    logger.info(
        "generator 스케줄러 기동 — 품질 다이제스트 %d분 · stuck 스캔 %d분", interval, stuck_interval
    )
    return True
