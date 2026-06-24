# 의도 교차검증(§3.5-3) — 정합 점수에서 불일치 파생하는 순수 함수 단위 테스트(무API)
from __future__ import annotations

from domain.simulation.contracts.schemas import RubricScore
from domain.simulation.graph.run_graph import _derive_intent


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
