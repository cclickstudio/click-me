# OCEAN 성향별 반응 분해 — z-score를 차원별 높음/낮음으로 갈라 가중 KPI 재집계(LLM 아님).
#
# 연령×성별 세그먼트(분석팀)와 별개로 "어떤 성향이 반응을 가르나"를 시뮬레이터 집계로 산출.
# 유형 라벨이 페르소나에 저장 안 되므로 z-score에서 밴드를 파생한다(DB 변경 없음).
from __future__ import annotations

from domain.simulation.tools.aggregation.aggregator import _effective_n, _wmean

# 성향 밴드 임계 — reaction.py `_ocean_level`의 ±0.4(높음/낮음)와 동일하게 맞춘다.
_BAND_HI = 0.4
_BAND_LO = -0.4
# 유효표본 이 미만이면 해당 차원 격차를 신뢰 낮음으로 표기 + 주동인 후보에서 제외.
_MIN_EFFECTIVE_N = 30.0
# 클릭의향 격차가 이 미만이면 "반응을 가른다"고 보지 않음(주동인 없음).
_MIN_DRIVER_GAP = 0.05

_DIMS = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")
_KO = {
    "openness": "개방성",
    "conscientiousness": "성실성",
    "extraversion": "외향성",
    "agreeableness": "친화성",
    "neuroticism": "신경증",
}


def _band_kpis(reactions: list) -> dict:
    """한 밴드(반응 묶음)의 가중 KPI — 집계 엔진과 동일 가중 평균 사용."""
    weights = [float(r.weight) for r in reactions]
    return {
        "n": len(reactions),
        "effective_n": round(_effective_n(weights), 1),
        "click_intent_rate": round(_wmean([float(r.aisas.action) for r in reactions], weights), 4),
        "purchase_intent": round(_wmean([float(r.purchase_intent) for r in reactions], weights), 2),
        "trust_avg": round(_wmean([float(r.trust) for r in reactions], weights), 2),
        "rejection_rate": round(_wmean([float(r.rejected) for r in reactions], weights), 4),
    }


def ocean_segment_breakdown(personas: list, reactions: list) -> dict:
    """OCEAN 5차원 성향별 반응 분해 — 차원별 높음/낮음 KPI + 반응을 가장 가르는 주동인.

    반환: {"by_dimension": [...], "top_driver": {...} | None}. 빈 입력이면 빈 구조.
    QA 통과분만 집계(집계 엔진과 동일 기준).
    """
    passed = [r for r in reactions if getattr(r, "qa_passed", True)]
    if not passed:
        return {"by_dimension": [], "top_driver": None}

    persona_by_id = {p.persona_id: p for p in personas}
    by_dimension: list[dict] = []
    candidates: list[dict] = []

    for dim in _DIMS:
        high: list = []
        low: list = []
        for r in passed:
            p = persona_by_id.get(r.persona_id)
            if p is None:
                continue
            z = p.ocean.get(dim)
            if z is None:
                continue
            if z >= _BAND_HI:
                high.append(r)
            elif z <= _BAND_LO:
                low.append(r)

        # 한쪽 밴드가 비면 격차 산출 불가 → 신뢰 낮음으로 기록만.
        if not high or not low:
            by_dimension.append(
                {
                    "dimension": dim,
                    "dimension_ko": _KO[dim],
                    "high": _band_kpis(high) if high else None,
                    "low": _band_kpis(low) if low else None,
                    "click_gap": None,
                    "low_confidence": True,
                }
            )
            continue

        hk, lk = _band_kpis(high), _band_kpis(low)
        gap = round(hk["click_intent_rate"] - lk["click_intent_rate"], 4)
        low_conf = hk["effective_n"] < _MIN_EFFECTIVE_N or lk["effective_n"] < _MIN_EFFECTIVE_N
        entry = {
            "dimension": dim,
            "dimension_ko": _KO[dim],
            "high": hk,
            "low": lk,
            "click_gap": gap,
            "low_confidence": low_conf,
        }
        by_dimension.append(entry)
        if not low_conf and abs(gap) >= _MIN_DRIVER_GAP:
            candidates.append(entry)

    top = max(candidates, key=lambda e: abs(e["click_gap"]), default=None)
    top_driver = None
    if top is not None:
        top_driver = {
            "dimension": top["dimension"],
            "dimension_ko": top["dimension_ko"],
            "direction": "높을수록 반응 높음" if top["click_gap"] > 0 else "낮을수록 반응 높음",
            "click_gap": top["click_gap"],
        }
    return {"by_dimension": by_dimension, "top_driver": top_driver}
