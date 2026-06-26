# 챗 시뮬 read 툴 — 저장된 시뮬 결과·페르소나 표본을 DB에서 조회(read-only).
"""서브에이전트가 부르는 조회 함수. 숫자·신뢰지표는 DB 영속 결과(get_full_result)에서만 가져온다.

get_result(인메모리)가 아니라 get_full_result(DB)를 쓴다 — 서버 재시작·재진입 후에도 답하려면 필수.
에러는 management tools 패턴과 동일하게 {"error": ...}로 표면화한다.
"""

from __future__ import annotations

import uuid
from collections import Counter

from sqlalchemy import text

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


# 목록/검색 공통 SELECT — 이름은 ads.title(시뮬엔 이름 없음), KPI는 집계 LEFT JOIN(미완도 노출).
# org는 raw SQL 격리(ORM import 없이 경계 보존, 스펙 §4.4). CAST로 전역(None) 겸용.
_SIM_LIST_SELECT = """
SELECT s.id, s.status, s.sample_size, s.created_at,
       u.name AS created_by_name, a.title AS ad_title,
       agg.click_intent_rate, agg.ci_low, agg.ci_high,
       agg.purchase_intent_avg, agg.trust_avg, agg.effective_n
FROM simulations s
LEFT JOIN users u ON u.id = s.created_by
LEFT JOIN ads a ON a.id = s.ad_id
LEFT JOIN simulation_aggregates agg ON agg.simulation_id = s.id
WHERE s.deleted_at IS NULL
  AND (CAST(:org AS uuid) IS NULL OR s.organization_id = CAST(:org AS uuid))
"""


def _sim_row(r) -> dict:
    """SQL 행 → 목록 항목. KPI는 집계 존재(완료) 시에만, Numeric→float·datetime→isoformat."""
    kpi = None
    if r.click_intent_rate is not None:
        kpi = {
            "click_intent_rate": float(r.click_intent_rate),
            "ci_low": float(r.ci_low) if r.ci_low is not None else None,
            "ci_high": float(r.ci_high) if r.ci_high is not None else None,
            "purchase_intent": float(r.purchase_intent_avg)
            if r.purchase_intent_avg is not None
            else None,
            "trust_avg": float(r.trust_avg) if r.trust_avg is not None else None,
            "effective_n": float(r.effective_n) if r.effective_n is not None else None,
        }
    return {
        "simulation_id": str(r.id),
        "ad_title": r.ad_title,
        "status": r.status,
        "sample_size": r.sample_size,
        "created_at": r.created_at.isoformat() if r.created_at is not None else None,
        "created_by_name": r.created_by_name,
        "kpi": kpi,
    }


async def sim_list(limit: int = 10, org_id: str | None = None, status: str | None = None) -> dict:
    """내 조직 시뮬레이션 현황 목록(시뮬ID·제목·상태·완료 시 KPI). org_id=None이면 전역."""
    try:
        oid = uuid.UUID(org_id) if org_id else None
    except ValueError:
        return {"error": "invalid_organization_id"}
    sql = _SIM_LIST_SELECT + (
        "  AND (CAST(:status AS text) IS NULL OR s.status = CAST(:status AS text))\n"
        "ORDER BY s.created_at DESC\nLIMIT :limit"
    )
    try:
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    text(sql),
                    {"org": str(oid) if oid else None, "status": status, "limit": limit},
                )
            ).all()
    except Exception as e:  # noqa: BLE001 — 조회 오류 표면화
        return {"error": "lookup_failed", "detail": str(e)}
    sims = [_sim_row(r) for r in rows]
    return {"simulations": sims, "count": len(sims)}


async def sim_find_by_name(name: str, org_id: str | None = None, limit: int = 10) -> dict:
    """광고 제목 부분일치(ILIKE)로 시뮬 검색 — 후보 목록 반환. org_id=None이면 전역."""
    if not name or not name.strip():
        return {"error": "need_name"}
    try:
        oid = uuid.UUID(org_id) if org_id else None
    except ValueError:
        return {"error": "invalid_organization_id"}
    sql = _SIM_LIST_SELECT + (
        "  AND a.title ILIKE :pattern\nORDER BY s.created_at DESC\nLIMIT :limit"
    )
    try:
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    text(sql),
                    {
                        "org": str(oid) if oid else None,
                        "pattern": f"%{name.strip()}%",
                        "limit": limit,
                    },
                )
            ).all()
    except Exception as e:  # noqa: BLE001
        return {"error": "lookup_failed", "detail": str(e)}
    sims = [_sim_row(r) for r in rows]
    return {"simulations": sims, "count": len(sims), "query": name.strip()}


# ── 페르소나 토론(debate) — 시뮬과 별개 산출물(별도 테이블).
# 시뮬 도메인 무수정, 크로스도메인 read.


async def sim_debate_list(simulation_id: str) -> dict:
    """시뮬레이션의 토론 목록(주제·상태·결론 요약). 없으면 빈 목록."""
    if not simulation_id:
        return {"error": "need_simulation_id"}
    from domain.simulation.repositories.debate_repository import DebateRepository

    try:
        debates = await DebateRepository(AsyncSessionLocal).list_by_simulation(simulation_id)
    except Exception as e:  # noqa: BLE001 — 조회 오류 표면화(read 계약)
        return {"error": "lookup_failed", "detail": str(e)}
    return {"debates": debates, "count": len(debates), "simulation_id": simulation_id}


async def sim_debate_detail(debate_id: str) -> dict:
    """토론 1건 상세 — 참가자·라운드별 발언·판정. 없으면 {"error":...}."""
    if not debate_id:
        return {"error": "need_debate_id"}
    from domain.simulation.repositories.debate_repository import DebateRepository

    try:
        detail = await DebateRepository(AsyncSessionLocal).get_detail(debate_id)
    except Exception as e:  # noqa: BLE001
        return {"error": "lookup_failed", "detail": str(e)}
    if detail is None:
        return {"error": "not_found", "debate_id": debate_id}
    return detail


async def start_debate(simulation_id: str) -> dict:
    """완료된 시뮬레이션의 반응으로 페르소나 토론을 백그라운드 실행(트리거).

    토론은 시뮬과 별개 산출물 — 반응이 영속된 완료 시뮬이 있어야 한다.
    완료 후 sim_debate_list로 조회.
    """
    if not simulation_id:
        return {"error": "need_simulation_id"}
    from core.config import settings
    from domain.simulation.contracts.schemas import (
        AdInterpretation,
        ObjectiveFit,
        Persona,
        PersonaReaction,
        RubricScore,
    )
    from domain.simulation.wiring import build_debate_service

    try:
        full = await _full_result(simulation_id)
    except ValueError:
        return {"error": "invalid_simulation_id"}
    except Exception as e:  # noqa: BLE001
        return {"error": "lookup_failed", "detail": str(e)}
    if not full or not full.get("reactions"):
        return {
            "error": "sim_not_ready",
            "message": "완료된 시뮬이 없어요 — 시뮬을 먼저 완료해야 토론을 돌릴 수 있어요.",
        }
    try:
        reactions = [PersonaReaction.model_validate(r) for r in full["reactions"]]
        ad_analysis = (
            AdInterpretation.model_validate(full["ad_analysis"])
            if full.get("ad_analysis")
            else None
        )
        personas = [Persona.model_validate(p) for p in full.get("personas", [])]
        rubric = [RubricScore.model_validate(s) for s in full.get("rubric_scores", [])]
        objective_fit = (
            ObjectiveFit.model_validate(full["objective_fit"])
            if full.get("objective_fit")
            else None
        )
        svc = build_debate_service(settings)
        run_id = await svc.start(
            reactions,
            ad_analysis,
            simulation_id=simulation_id,
            personas=personas,
            rubric=rubric,
            objective_fit=objective_fit,
        )
    except Exception as e:  # noqa: BLE001 — 엔진·키 오류 등 표면화
        return {"error": "start_failed", "detail": str(e)}
    return {"run_id": run_id, "simulation_id": simulation_id}
