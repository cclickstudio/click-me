# 챗 시뮬 read 툴 — 저장된 시뮬 결과·페르소나 표본을 DB에서 조회(read-only).
"""서브에이전트가 부르는 조회 함수. 숫자·신뢰지표는 DB 영속 결과(get_full_result)에서만 가져온다.

get_result(인메모리)가 아니라 get_full_result(DB)를 쓴다 — 서버 재시작·재진입 후에도 답하려면 필수.
에러는 management tools 패턴과 동일하게 {"error": ...}로 표면화한다.
"""

from __future__ import annotations

import uuid
from collections import Counter

from core.db import AsyncSessionLocal

_OCEAN_KEYS = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")


def _age_band(age: int) -> str:
    if age < 20:
        return "10대"
    if age < 30:
        return "20대"
    if age < 40:
        return "30대"
    if age < 50:
        return "40대"
    if age < 60:
        return "50대"
    return "60대+"


async def _full_result(simulation_id: str) -> dict | None:
    """simulation_id로 DB 영속 결과 재조립(없거나 오류면 None은 호출부에서 분기)."""
    from domain.simulation.repositories.simulation_repository import SimulationRepository

    async with AsyncSessionLocal() as db:
        return await SimulationRepository(db).get_full_result(uuid.UUID(simulation_id))


async def sim_result(simulation_id: str) -> dict:
    """저장된 시뮬레이션의 4대 KPI + 신뢰 지표(CI·유효표본수·QA·분산경고). 없으면 {"error":...}."""
    try:
        full = await _full_result(simulation_id)
    except ValueError:
        return {"error": "invalid_simulation_id"}
    except Exception as e:  # noqa: BLE001 — DB/S3 오류는 표면화(read tool 계약)
        return {"error": "lookup_failed", "detail": str(e)}
    if not full:
        return {"error": "not_found", "simulation_id": simulation_id}

    agg: dict = full.get("aggregate") or {}
    reactions: list = full.get("reactions") or []
    return {
        "simulation_id": full.get("simulation_id"),
        "click_intent_rate": agg.get("click_intent_rate"),
        "ci_low": agg.get("ci_low"),
        "ci_high": agg.get("ci_high"),
        "purchase_intent": agg.get("purchase_intent"),
        "trust_avg": agg.get("trust_avg"),
        "rejection_rate": agg.get("rejection_rate"),
        "brand_recognition_rate": agg.get("brand_recognition_rate"),
        "effective_n": agg.get("effective_n"),
        "variance_warning": agg.get("variance_warning"),
        "sample_size": len(reactions),
        "qa_passed": sum(1 for r in reactions if r.get("qa_passed")),
        "objective_fit": full.get("objective_fit"),
    }


async def sim_persona_basis(simulation_id: str) -> dict:
    """시뮬에 쓰인 페르소나 표본의 분포 요약(연령대·성별·지역·OCEAN 평균). 없으면 {"error":...}.

    "무슨 데이터로 페르소나를 만들었나"의 표본 측면을 답한다.
    데이터 출처·방법론은 KB(persona_methodology)를 참고한다.
    """
    try:
        full = await _full_result(simulation_id)
    except ValueError:
        return {"error": "invalid_simulation_id"}
    except Exception as e:  # noqa: BLE001
        return {"error": "lookup_failed", "detail": str(e)}
    if not full:
        return {"error": "not_found", "simulation_id": simulation_id}

    personas: list = full.get("personas") or []
    if not personas:
        return {"error": "no_personas", "simulation_id": full.get("simulation_id")}

    genders = Counter(p.get("gender") for p in personas if p.get("gender"))
    regions = Counter(p.get("region") for p in personas if p.get("region"))
    age_bands = Counter(_age_band(p["age"]) for p in personas if isinstance(p.get("age"), int))
    ocean_avg: dict[str, float] = {}
    for key in _OCEAN_KEYS:
        vals = [
            float(p["ocean"][key])
            for p in personas
            if isinstance(p.get("ocean"), dict) and key in p["ocean"]
        ]
        if vals:
            ocean_avg[key] = round(sum(vals) / len(vals), 3)

    return {
        "simulation_id": full.get("simulation_id"),
        "sample_size": len(personas),
        "gender_dist": dict(genders),
        "region_top": dict(regions.most_common(5)),
        "age_band_dist": dict(age_bands),
        "ocean_avg": ocean_avg,
    }
