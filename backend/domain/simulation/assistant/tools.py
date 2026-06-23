# 시뮬레이션 어시스턴트 결과조회 도구 — 저장된 시뮬 결과를 4대 KPI 요약으로
"""숫자는 여기(저장된 실측 결과)서만 가져온다. 정의·해석은 KB(retriever)로 분리."""

from __future__ import annotations

import uuid

from core.db import AsyncSessionLocal
from domain.simulation.repositories.simulation_repository import SimulationRepository


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
