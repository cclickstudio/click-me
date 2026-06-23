# 시뮬레이션 어시스턴트 결과조회 도구 — 저장된 시뮬 결과를 4대 KPI 요약으로
"""숫자는 여기(저장된 실측 결과)서만 가져온다. 정의·해석은 KB(retriever)로 분리."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from core.db import AsyncSessionLocal
from domain.simulation.repositories.simulation_repository import SimulationRepository

if TYPE_CHECKING:
    from domain.simulation.service.simulation_service import SimulationService


async def fetch_simulation_result(simulation_id: str) -> dict:
    """simulation_id로 저장된 결과의 4대 KPI·목표적합도 요약. 없으면 error 키."""
    try:
        sid = uuid.UUID(simulation_id)
    except (ValueError, TypeError, AttributeError):
        return {"error": "invalid_id"}
    async with AsyncSessionLocal() as db:
        result = await SimulationRepository(db).get_full_result(sid)
    if result is None:
        return {"error": "not_found"}
    agg = result.get("aggregate") or {}
    return {
        "simulation_id": result.get("simulation_id"),
        "click_intent_rate": agg.get("click_intent_rate"),
        "ci_low": agg.get("ci_low"),
        "ci_high": agg.get("ci_high"),
        "purchase_intent": agg.get("purchase_intent"),
        "trust_avg": agg.get("trust_avg"),
        "rejection_rate": agg.get("rejection_rate"),
        "brand_recognition_rate": agg.get("brand_recognition_rate"),
        "effective_n": agg.get("effective_n"),
        "variance_warning": agg.get("variance_warning"),
        "objective_fit": result.get("objective_fit"),
        "reaction_count": len(result.get("reactions") or []),
    }


_sim_service = None


def _get_simulation_service() -> SimulationService:
    """시뮬 서비스 싱글톤 — wiring(무거운 어댑터)을 첫 호출에만 빌드."""
    global _sim_service
    if _sim_service is None:
        from core.config import settings  # noqa: PLC0415
        from domain.simulation.wiring import build_simulation_service  # noqa: PLC0415

        _sim_service = build_simulation_service(settings=settings)
    return _sim_service


async def run_simulation(
    ad_content: str,
    ad_title: str | None = None,
    product_category: str | None = None,
    ad_objective: str | None = None,
    sample_size: int = 10,
) -> dict:
    """채팅에서 광고 텍스트로 시뮬레이션을 실행한다(광고 등록 없이, 메모리). 4대 KPI 요약 반환.

    ad_id는 chat-{uuid}로 자동 생성하고 project_id를 생략해 영속화는 건너뛴다(메모리 run).
    채팅 실행은 가볍게 — sample_size를 1~30으로 제한한다. 동기 실행(끝까지 대기).
    """
    from domain.simulation.contracts.schemas import SimulationRunRequest  # noqa: PLC0415

    service = _get_simulation_service()
    req = SimulationRunRequest(
        ad_id=f"chat-{uuid.uuid4()}",
        ad_content=ad_content,
        ad_title=ad_title,
        product_category=product_category,
        ad_objective=ad_objective,
        sample_size=max(1, min(sample_size, 30)),
    )
    result = await service.run(req)
    agg = result.get("aggregate") or {}
    return {
        "run_id": result.get("run_id"),
        "click_intent_rate": agg.get("click_intent_rate"),
        "ci_low": agg.get("ci_low"),
        "ci_high": agg.get("ci_high"),
        "purchase_intent": agg.get("purchase_intent"),
        "trust_avg": agg.get("trust_avg"),
        "rejection_rate": agg.get("rejection_rate"),
        "effective_n": agg.get("effective_n"),
    }
