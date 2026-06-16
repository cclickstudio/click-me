# 더미 반응 데이터 로더 — 7번(반응 출력) 산출물 JSON을 도메인 DTO로 파싱(검증·개발용)
#
# 더미 5개(reaction-dummy1~5.json)는 reactions[]+aggregate까지 끝난 상태.
# 조각 8~9 검증의 입력원으로만 쓴다(운영 경로 아님).
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from domain.simulation.contracts.schemas import (
    AdInterpretation,
    PersonaReaction,
    RubricScore,
    SimulationAggregate,
)

# 이 파일 기준 더미 디렉토리: backend/domain/simulation/dummy/
_DUMMY_DIR = Path(__file__).resolve().parents[2] / "dummy"


@dataclass(frozen=True)
class DummyReactionSet:
    """더미 한 건(7번 반응 출력) — 분석(8)·집계검증(9) 입력 묶음."""

    name: str
    run_id: str
    reactions: list[PersonaReaction]
    ad_analysis: AdInterpretation | None
    rubric_scores: list[RubricScore]
    aggregate: SimulationAggregate | None  # 더미에 박힌 7번 집계(9 재계산 일치 검증용)


def load_dummy(path: str | Path) -> DummyReactionSet:
    """더미 JSON 한 개를 DummyReactionSet으로 파싱."""
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))

    reactions = [PersonaReaction.model_validate(r) for r in raw.get("reactions", [])]
    ad = raw.get("ad_analysis")
    rubric = [RubricScore.model_validate(s) for s in raw.get("rubric_scores", [])]
    agg = raw.get("aggregate")

    return DummyReactionSet(
        name=p.stem,
        run_id=raw.get("run_id", ""),
        reactions=reactions,
        ad_analysis=AdInterpretation.model_validate(ad) if ad else None,
        rubric_scores=rubric,
        aggregate=SimulationAggregate.model_validate(agg) if agg else None,
    )


def load_all_dummies(dummy_dir: str | Path | None = None) -> list[DummyReactionSet]:
    """reaction-dummy*.json 전부 이름순으로 로드."""
    d = Path(dummy_dir) if dummy_dir else _DUMMY_DIR
    files = sorted(d.glob("reaction-dummy*.json"))
    return [load_dummy(f) for f in files]


def load_dummy_by_name(name: str) -> DummyReactionSet:
    """이름(예: reaction-dummy1)으로 더미 로드 — 라우터/데모용. 없으면 FileNotFoundError."""
    p = _DUMMY_DIR / f"{name}.json"
    if not p.exists():
        raise FileNotFoundError(f"더미를 찾을 수 없음: {name}")
    return load_dummy(p)
