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

    미완료(aggregate 없음)/미존재/삭제됨(soft delete)/형식오류는 None(연결 대기).
    org 대조는 하지 않는다 — 호출부의 링크 행(created_campaigns)이 이미 뷰어 org로
    스코프돼 있고, 링크 생성 경로가 org를 검증하므로 링크된 시뮬은 신뢰한다.
    (제너레이터 org에서 돌린 시뮬을 매니지먼트 org 캠페인에 붙이는 교차-워크스페이스 흐름 허용.)
    simulation 도메인 ORM import 금지 — 테이블·컬럼명 문자열로만 접근.
    as_of는 시뮬 완료시각(UTC aware).
    """

    # deleted_at IS NULL — 소프트삭제된 시뮬은 예측에서 제외(삭제가 성과 비교에 반영되게).
    _SQL = text(
        """
        SELECT s.ad_id, s.organization_id, s.completed_at,
               a.click_intent_rate, a.purchase_intent_avg, a.trust_avg, a.rejection_rate
        FROM simulations s
        JOIN simulation_aggregates a ON a.simulation_id = s.id
        WHERE s.id = :sid AND s.deleted_at IS NULL
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
