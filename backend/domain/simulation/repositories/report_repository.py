# 통합 리포트(report_view) 영속화 — simulation_reports 1행을 simulation_id로 upsert·조회
#
# 시뮬당 1행(simulation_id UNIQUE). 토론할 때마다 최신 합산 report_view로 upsert.
# 세션은 service(영속화 핸들러)에서 열어 주입 — 여기서는 SQL만.
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.simulation.models import SimulationReport


def _as_uuid(value: str | None) -> uuid.UUID | None:
    """식별자 문자열을 UUID로 — UUID 형식이면 그대로, 아니면 결정적 uuid5. None은 그대로."""
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return uuid.uuid5(uuid.NAMESPACE_OID, value or "clickme-report")


class ReportRepository:
    """통합 리포트 1행(simulation_id UNIQUE) upsert·조회. 세션 주입(트랜잭션은 호출자가 관리)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        simulation_id: str,
        report_view: dict,
        run_id: str | None = None,
        debate_id: str | None = None,
        debate_count: int = 0,
    ) -> None:
        """simulation_id 기존 행 있으면 update, 없으면 insert. commit은 호출자(핸들러)가 한다."""
        sim_uuid = _as_uuid(simulation_id)
        row = (
            await self._session.execute(
                select(SimulationReport).where(SimulationReport.simulation_id == sim_uuid)
            )
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        if row is None:
            self._session.add(
                SimulationReport(
                    simulation_id=sim_uuid,
                    run_id=run_id,
                    debate_id=_as_uuid(debate_id),
                    debate_count=debate_count,
                    report_view=report_view,
                    generated_at=now,
                    updated_at=now,
                )
            )
        else:
            row.report_view = report_view
            row.run_id = run_id
            row.debate_id = _as_uuid(debate_id)
            row.debate_count = debate_count
            row.generated_at = now
            row.updated_at = now

    async def get_by_simulation(self, simulation_id: str) -> dict | None:
        """simulation_id로 저장된 report_view(JSONB) 반환. 없으면 None."""
        sim_uuid = _as_uuid(simulation_id)
        row = (
            await self._session.execute(
                select(SimulationReport).where(SimulationReport.simulation_id == sim_uuid)
            )
        ).scalar_one_or_none()
        return row.report_view if row is not None else None
