# 집행 전(시뮬 예측) 읽기 어댑터 — Mock(지금) + Sim(추후 교체 stub)
"""PredictionReader 구현. 시뮬 로직이 바뀌어도 management는 이 포트에만 의존한다.

지금은 MockPredictionReader로 화면을 동작시키고, 시뮬 KPI가 안정화되면 wiring에서
SimPredictionReader로 교체한다(화면·API 변경 없음).
"""

from __future__ import annotations

from datetime import UTC, datetime

from domain.management.comparison.schemas import PredictionSnapshot


def _grade(score: int) -> str:
    if score >= 70:
        return "높음"
    if score >= 45:
        return "보통"
    return "낮음"


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
        score = 40 + (seed % 55)  # 40~94
        return PredictionSnapshot(
            ad_id=simulation_id,
            click_intent_rate=min(click_intent, 1.0),
            purchase_intent=min(purchase, 5.0),
            trust_avg=min(trust, 5.0),
            rejection_rate=min(rejection, 1.0),
            objective_fit_score=score,
            grade=_grade(score),
            as_of=datetime.now(UTC),
            source="mock",
        )


class SimPredictionReader:
    """실 시뮬 예측 읽기 — 추후 simulation 도메인을 simulation_id로 조회해 채운다(현재 미배선).

    시뮬 로직 안정화 후 여기서 simulation aggregate를 PredictionSnapshot(source='sim')으로
    매핑한다. 그전까지는 None(시뮬 미연결)으로 둬 화면이 '연결 대기'를 표시.
    """

    async def get_prediction(self, simulation_id: str, tenant_id: str) -> PredictionSnapshot | None:
        return None
