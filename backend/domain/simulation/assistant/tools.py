# 시뮬레이션 어시스턴트 결과조회 도구 — 저장된 시뮬 결과를 4대 KPI 요약으로
"""숫자는 여기(저장된 실측 결과)서만 가져온다. 정의·해석은 KB(retriever)로 분리."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import text

from core.db import AsyncSessionLocal
from domain.simulation.repositories.simulation_repository import SimulationRepository

if TYPE_CHECKING:
    from domain.simulation.service.simulation_service import SimulationService

# 거부율이 이 값 이상이면 "약한 결과"로 본다(패턴 학습·요약 공용).
_WEAK_REJECTION = 0.3
_WEAK_PI = 3.5

# KOBACO 벤치마크 데이터 파일(카테고리별 평균 KPI). 첫 호출에 1회 로드.
_KOBACO_PATH = Path(__file__).resolve().parents[3] / "data" / "kobaco_benchmarks.json"
_kobaco_cache: dict | None = None


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


async def list_simulations(project_id: str, limit: int = 10) -> list[dict]:
    """프로젝트의 최근 시뮬 목록(id·제목·표본수·상태·시각). 이름/최근으로 특정할 때 쓴다."""
    if not project_id:
        return []
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            text("""
                SELECT s.id, s.status, s.sample_size, s.created_at, a.title AS ad_title
                FROM simulations s
                JOIN ads a ON a.id = s.ad_id
                WHERE a.project_id = :pid AND s.deleted_at IS NULL
                ORDER BY s.created_at DESC
                LIMIT :limit
            """),
            {"pid": project_id, "limit": max(1, min(limit, 50))},
        )
    return [
        {
            "id": str(r.id),
            "title": r.ad_title or "제목 없음",
            "sample_size": r.sample_size,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


async def fetch_project_sim_patterns(project_id: str, limit: int = 20) -> dict:
    """프로젝트 최근 시뮬들에서 약한 결과(거부율>=30% 또는 구매의도<3.5)의 공통 패턴을 추출.

    카테고리·목표·카피 길이 같은 공통점을 집계해 "왜 약했나"의 단서를 제공한다(T07).
    """
    sims = await list_simulations(project_id, limit=limit)
    if not sims:
        return {"total": 0, "weak": 0, "patterns": [], "note": "시뮬 내역이 없어요."}
    weak: list[dict] = []
    for s in sims:
        ev = await fetch_simulation_result(s["id"])
        if ev.get("error"):
            continue
        rej = ev.get("rejection_rate")
        pi = ev.get("purchase_intent")
        is_weak = (rej is not None and rej >= _WEAK_REJECTION) or (pi is not None and pi < _WEAK_PI)
        if is_weak:
            weak.append({"title": s.get("title"), "rejection_rate": rej, "purchase_intent": pi})
    # 약한 결과 제목 길이 평균(카피 길이 대용) — 공통 패턴 단서.
    patterns: list[str] = []
    if weak:
        avg_rej = sum(w["rejection_rate"] or 0 for w in weak) / len(weak)
        avg_title_len = sum(len(w["title"] or "") for w in weak) / len(weak)
        patterns.append(f"약한 시뮬 {len(weak)}건 평균 거부율 {avg_rej * 100:.0f}%")
        patterns.append(f"약한 시뮬 평균 제목 길이 {avg_title_len:.0f}자")
    return {
        "total": len(sims),
        "weak": len(weak),
        "weak_titles": [w["title"] for w in weak][:10],
        "patterns": patterns,
    }


async def fetch_project_summary(project_id: str, period: str = "month") -> dict:
    """기간 내 프로젝트 시뮬 집계 — 평균 KPI·최고/최저 결과·표본(T09). period는 month|all.

    실측 KPI는 저장된 시뮬 결과에서만 인용한다. 생성(gen)은 목록 수만 집계.
    """
    sims = await list_simulations(project_id, limit=50)
    rows: list[dict] = []
    for s in sims:
        ev = await fetch_simulation_result(s["id"])
        if ev.get("error") or ev.get("purchase_intent") is None:
            continue
        rows.append(
            {
                "title": s.get("title"),
                "purchase_intent": ev.get("purchase_intent"),
                "rejection_rate": ev.get("rejection_rate"),
                "click_intent_rate": ev.get("click_intent_rate"),
            }
        )
    if not rows:
        return {"count": 0, "note": "집계할 시뮬 결과가 없어요."}
    avg_pi = sum(r["purchase_intent"] for r in rows) / len(rows)
    best = max(rows, key=lambda r: r["purchase_intent"])
    worst = min(rows, key=lambda r: r["purchase_intent"])
    return {
        "count": len(rows),
        "avg_purchase_intent": round(avg_pi, 2),
        "best": {"title": best["title"], "purchase_intent": best["purchase_intent"]},
        "worst": {"title": worst["title"], "purchase_intent": worst["purchase_intent"]},
    }


def fetch_kobaco_benchmark(category: str | None) -> dict:
    """카테고리별 KOBACO 평균 KPI를 반환(T08). 미상 카테고리는 '기타'로 폴백."""
    global _kobaco_cache
    if _kobaco_cache is None:
        try:
            _kobaco_cache = json.loads(_KOBACO_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 파일 없으면 빈 벤치마크로 진행
            _kobaco_cache = {}
    cat = (category or "").strip() or "기타"
    bench = _kobaco_cache.get(cat) or _kobaco_cache.get("기타")
    if not bench:
        return {"category": cat, "found": False}
    return {"category": cat, "found": True, **bench}


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
