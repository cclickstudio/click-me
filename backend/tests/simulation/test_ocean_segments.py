# OCEAN 성향별 반응 분해 단위 테스트 — 주동인 식별·가중·엣지(빈/단일밴드/소표본)
from __future__ import annotations

from domain.simulation.contracts.schemas import Aisas, Persona, PersonaReaction
from domain.simulation.tools.aggregation.ocean_segments import ocean_segment_breakdown

_DIMS = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")


def _pair(pid: str, dim_z: dict, action: bool, weight: float = 1.0, qa: bool = True):
    """합성 (persona, reaction) 한 쌍 — dim_z로 특정 차원만 높/낮게 세팅(나머지 0)."""
    ocean = dict.fromkeys(_DIMS, 0.0)
    ocean.update(dim_z)
    persona = Persona(persona_id=pid, age=30, gender="M", region="서울", ocean=ocean, weight=weight)
    reaction = PersonaReaction(
        persona_id=pid,
        weight=weight,
        aisas=Aisas(attention=action, interest=action, action=action),
        purchase_intent=3,
        trust=3,
        qa_passed=qa,
    )
    return persona, reaction


def _build(specs):
    personas, reactions = [], []
    for pid, dim_z, action, *rest in specs:
        weight = rest[0] if rest else 1.0
        p, r = _pair(pid, dim_z, action, weight=weight)
        personas.append(p)
        reactions.append(r)
    return personas, reactions


def test_top_driver_identifies_discriminating_dimension() -> None:
    specs = [(f"H{i}", {"openness": 1.0}, True) for i in range(40)]
    specs += [(f"L{i}", {"openness": -1.0}, False) for i in range(40)]
    out = ocean_segment_breakdown(*_build(specs))

    td = out["top_driver"]
    assert td is not None
    assert td["dimension"] == "openness"
    assert td["click_gap"] > 0
    assert td["direction"] == "높을수록 반응 높음"

    o = next(e for e in out["by_dimension"] if e["dimension"] == "openness")
    assert o["high"]["click_intent_rate"] == 1.0
    assert o["low"]["click_intent_rate"] == 0.0
    assert o["low_confidence"] is False

    # z=0인 다른 차원은 양쪽 밴드가 비어 주동인 후보가 아니다.
    c = next(e for e in out["by_dimension"] if e["dimension"] == "conscientiousness")
    assert c["click_gap"] is None
    assert c["low_confidence"] is True


def test_weighted_kpi() -> None:
    specs = [
        ("h1", {"openness": 1.0}, True, 3.0),  # 가중 3
        ("h2", {"openness": 1.0}, False, 1.0),
        ("l1", {"openness": -1.0}, False, 1.0),
    ]
    out = ocean_segment_breakdown(*_build(specs))
    o = next(e for e in out["by_dimension"] if e["dimension"] == "openness")
    assert o["high"]["click_intent_rate"] == 0.75  # (1*3 + 0*1) / 4


def test_empty_reactions() -> None:
    assert ocean_segment_breakdown([], []) == {"by_dimension": [], "top_driver": None}


def test_all_qa_failed_is_empty() -> None:
    p, r = _pair("x", {"openness": 1.0}, action=True, qa=False)
    assert ocean_segment_breakdown([p], [r]) == {"by_dimension": [], "top_driver": None}


def test_single_band_has_no_gap_or_driver() -> None:
    specs = [(f"H{i}", {"openness": 1.0}, True) for i in range(40)]
    out = ocean_segment_breakdown(*_build(specs))
    assert out["top_driver"] is None
    o = next(e for e in out["by_dimension"] if e["dimension"] == "openness")
    assert o["click_gap"] is None
    assert o["low_confidence"] is True
    assert o["high"]["n"] == 40
    assert o["low"] is None


def test_small_sample_excluded_from_driver() -> None:
    specs = [(f"H{i}", {"openness": 1.0}, True) for i in range(5)]
    specs += [(f"L{i}", {"openness": -1.0}, False) for i in range(5)]
    out = ocean_segment_breakdown(*_build(specs))
    o = next(e for e in out["by_dimension"] if e["dimension"] == "openness")
    assert o["low_confidence"] is True  # 유효표본 5 < 30
    assert out["top_driver"] is None
