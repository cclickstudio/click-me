# 집행 전(시뮬 예측) 읽기 어댑터 — Sim(운영) + Mock(데모·테스트 폴백)
"""PredictionReader 구현. 시뮬 로직이 바뀌어도 management는 이 포트에만 의존한다.

운영 wiring은 SimPredictionReader(simulation_aggregates를 raw SQL로 읽음)를 쓴다.
MockPredictionReader는 데모·단위 테스트에서 직접 주입하는 합성 예측(운영 합성 금지).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from domain.management.comparison.schemas import PredictionSnapshot


class MockPredictionReader:
    """simulation_id 기반 결정론 합성 예측 — 실 시뮬과 동일 필드(슬롯 채움, source='mock')."""

    async def get_prediction(self, simulation_id: str, tenant_id: str) -> PredictionSnapshot | None:
        if not simulation_id:
            return None
        seed = sum(ord(c) for c in simulation_id)
        click_intent = round(0.35 + (seed % 50) / 100, 3)  # 0.35~0.84
        purchase = round(2.5 + (seed % 25) / 10, 1)  # 2.5~4.9
        trust = round(2.8 + (seed % 20) / 10, 1)  # 2.8~4.7
        rejection = round((seed % 30) / 100, 3)  # 0.00~0.29
        return PredictionSnapshot(
            ad_id=simulation_id,
            click_intent_rate=min(click_intent, 1.0),
            purchase_intent=min(purchase, 5.0),
            trust_avg=min(trust, 5.0),
            rejection_rate=min(rejection, 1.0),
            as_of=datetime.now(UTC),
            source="mock",
        )


class SimPredictionReader:
    """실 시뮬 예측 읽기 — simulation_id로 simulation_aggregates를 raw SQL 조회(도메인 경계).

    org 불일치/미완료(aggregate 없음)/미존재/형식오류는 None(연결 대기). simulation 도메인
    ORM import 금지 — 테이블·컬럼명 문자열로만 접근. as_of는 시뮬 완료시각(UTC aware).
    """

    _SQL = text(
        """
        SELECT s.ad_id, s.organization_id, s.completed_at,
               a.click_intent_rate, a.purchase_intent_avg, a.trust_avg, a.rejection_rate
        FROM simulations s
        JOIN simulation_aggregates a ON a.simulation_id = s.id
        WHERE s.id = :sid
        """
    )

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def get_prediction(self, simulation_id: str, tenant_id: str) -> PredictionSnapshot | None:
        try:
            sid = uuid.UUID(str(simulation_id))
        except (ValueError, TypeError):
            return None
        async with self._session_factory() as db:
            row = (await db.execute(self._SQL, {"sid": str(sid)})).first()
        if row is None:
            return None
        if str(row[1]) != str(tenant_id):  # org 대조
            return None
        as_of = row[2].replace(tzinfo=UTC) if row[2] is not None else datetime.now(UTC)
        return PredictionSnapshot(
            ad_id=str(row[0]),
            click_intent_rate=float(row[3]),
            purchase_intent=float(row[4]),
            trust_avg=float(row[5]),
            rejection_rate=float(row[6]),
            as_of=as_of,
            source="sim",
        )
