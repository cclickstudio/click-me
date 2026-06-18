# 의도 교차검증(§3.5-3) — 정합 채점 + 불일치 파생 단위·통합 테스트(Mock, 무API)
from __future__ import annotations

from domain.simulation.adapters.mock_engine import MockAdInterpreter, MockRubricEvaluator
from domain.simulation.contracts.schemas import RubricScore, SimulationRunRequest
from domain.simulation.graph.run_graph import _derive_intent
from domain.simulation.wiring import build_simulation_service


def _score(dim: str, score: int, **ev: object) -> RubricScore:
    return RubricScore(dimension=dim, score=score, evidence=ev)


def test_derive_intent_flags_low_alignment() -> None:
    scores = [
        _score("category_alignment", 40, declared="에너지드링크", detected="beverage"),
        _score("objective_alignment", 90, declared="awareness", detected="awareness"),
    ]
    mismatch, detail = _derive_intent(scores)
    assert mismatch is True
    assert detail["category"]["match"] is False
    assert detail["objective"]["match"] is True


def test_derive_intent_empty_when_no_dims() -> None:
    # 선언 입력 없는 차원(어댑터가 스킵) → 비교 불가, 불일치 아님.
    assert _derive_intent([]) == (False, None)


async def test_mock_rubric_scores_only_declared_dims() -> None:
    ad = await MockAdInterpreter().interpret(SimulationRunRequest(ad_id="A"))
    # 감지 beverage와 불일치하는 선언 카테고리만 입력 → category 차원만 채점.
    req = SimulationRunRequest(ad_id="A", product_category="에너지드링크")
    scores = await MockRubricEvaluator().evaluate(ad, req)
    assert {s.dimension for s in scores} == {"category_alignment"}
    assert scores[0].score == 40  # 불일치 → 低


async def _drain(service, run_id: str) -> list[str]:
    return [chunk async for chunk in service.stream_events(run_id)]


async def test_intent_mismatch_surfaces_in_result() -> None:
    service = build_simulation_service()
    req = SimulationRunRequest(
        ad_id="AD-X",
        sample_size=5,
        product_category="에너지드링크",  # mock 감지 beverage와 불일치
        ad_objective="awareness",  # mock 감지와 일치
    )
    run_id = await service.start(req)
    await _drain(service, run_id)

    result = service.get_result(run_id)
    ad = result["ad_analysis"]
    assert ad["intent_mismatch"] is True
    assert ad["mismatch_detail"]["category"]["match"] is False
    assert ad["mismatch_detail"]["objective"]["match"] is True
    dims = {s["dimension"] for s in result["rubric_scores"]}
    assert dims == {"category_alignment", "objective_alignment"}
