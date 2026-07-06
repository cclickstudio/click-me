# 시뮬레이션 outer 그래프 — 선형 supervisor DAG + Send fan-out(map-reduce)
#
# 토폴로지: interpret_ad(감지+교차검증) → load_panel → Send×N react(서브그래프) → aggregate
# interpret_ad가 VLM 감지 + 의도 정합 채점(루브릭)을 묶어 ad·rubric_scores를 함께 산출(§3.5-3).
# 값싼 preamble은 직렬(불균등 깊이 join 회피 — defer는 구버전 langgraph에 없어 CI 위험).
# 비싼 N개 반응만 fan-out 병렬. reactions 는 operator.add 리듀서로 fan-in 수집.
# 어댑터는 덕타이핑 주입(wiring.py).
from __future__ import annotations

import logging
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from domain.simulation.contracts.schemas import (
    AdInterpretation,
    PanelSpec,
    Persona,
    PersonaReaction,
    RubricScore,
    SimulationAggregate,
    SimulationRunRequest,
)
from domain.simulation.graph.reaction_graph import run_reaction
from domain.simulation.tools.aggregation.kobaco_reference import lookup_kobaco_reference
from domain.simulation.tools.brand_awareness import lookup_brand_awareness

logger = logging.getLogger("clickme")

# 정합 점수 → 의도 불일치 파생(§3.5-3). score 임계 미만이면 그 차원 불일치.
_ALIGN_THRESHOLD = 60
_ALIGN_TO_DIM = {
    "category_alignment": "category",
    "objective_alignment": "objective",
    "message_alignment": "message",
}


def _derive_intent(scores: list[RubricScore]) -> tuple[bool, dict | None]:
    """정합 점수(루브릭)에서 intent_mismatch·mismatch_detail 파생 — 하나의 비교, 두 출력.

    선언 입력 있는 차원만 들어오므로(어댑터가 스킵), 비교 차원이 없으면 (False, None).
    """
    detail: dict[str, dict] = {}
    for s in scores:
        dim = _ALIGN_TO_DIM.get(s.dimension)
        if dim is None:
            continue
        ev = s.evidence or {}
        match = s.score >= _ALIGN_THRESHOLD
        detail[dim] = {
            "declared": ev.get("declared"),
            "detected": ev.get("detected"),
            "match": match,
            "note": ev.get("note", ""),
            "score": s.score,
        }
    if not detail:
        return False, None
    mismatch = any(not d["match"] for d in detail.values())
    return mismatch, detail


class RunState(TypedDict, total=False):
    """outer 그래프 상태. reactions 는 Send map 의 fan-in 리듀서로 누적."""

    request: SimulationRunRequest
    ad: AdInterpretation | None
    panel_version: str | None
    personas: list[Persona]
    rubric_scores: list[RubricScore]
    reactions: Annotated[list[PersonaReaction], operator.add]
    aggregate: SimulationAggregate | None


async def interpret_and_score(
    interpreter, rubric, request: SimulationRunRequest
) -> tuple[AdInterpretation, list[RubricScore]]:
    """광고 해석 + 의도 정합 채점(§3.5-3) — outer 그래프의 interpret_ad 노드와 세그먼트 비교
    서비스(Persona Set, 3-모드 UX)가 공유한다. 광고당 1회만 호출(세그먼트 수만큼 반복 금지).

    ① VLM 감지(선언 의도 미주입, 앵커링 방지) → ② 교차검증(정합 점수) → 불일치 파생
    ③ Tier3 브랜드 인지율 — 광고 텍스트에 수록 브랜드 있으면 1회 부착(없으면 폴백).
    """
    ad = await interpreter.interpret(request)
    scores = await rubric.evaluate(ad, request)
    mismatch, detail = _derive_intent(scores)
    update: dict = {"intent_mismatch": mismatch, "mismatch_detail": detail}
    brand_hint = " ".join(
        x for x in (request.ad_title, request.ad_content, ad.detected_message) if x
    )
    awareness = lookup_brand_awareness(brand_hint)
    if awareness:
        update["structured_analysis"] = {**ad.structured_analysis, **awareness}
    return ad.model_copy(update=update), scores


def build_run_graph(*, interpreter, panel, rubric, aggregator, reaction_graph):
    """outer 그래프를 컴파일한다.

    기대 어댑터(덕타이핑):
      interpreter.interpret(request)    -> AdInterpretation (감지, 선언 모름)
      rubric.evaluate(ad, request)      -> [RubricScore] (의도 정합 점수, 선언↔감지 비교)
      panel.get_or_build(spec)          -> (panel_version, [Persona])
      aggregator.aggregate([reaction])  -> SimulationAggregate
      reaction_graph                    -> P5 반응 서브그래프(컴파일본)
    """

    async def interpret_ad(state: RunState) -> dict:
        ad, scores = await interpret_and_score(interpreter, rubric, state["request"])
        return {"ad": ad, "rubric_scores": scores}

    async def load_panel(state: RunState) -> dict:
        req = state["request"]
        spec = PanelSpec(
            size=req.sample_size, target_filter=req.target_filter, allocation=req.allocation
        )
        version, personas = await panel.get_or_build(spec)
        return {"panel_version": version, "personas": personas}

    def fan_out(state: RunState) -> list[Send]:
        ad = state["ad"]
        return [Send("react", {"persona": p, "ad": ad}) for p in state["personas"]]

    async def react(payload: dict) -> dict:
        persona = payload["persona"]
        try:
            reaction = await run_reaction(reaction_graph, persona, payload["ad"])
        except Exception as exc:  # 한 명 실패는 건너뜀 (전체 진행 유지)
            logger.warning("페르소나 %s 반응 실패: %s", persona.persona_id, exc)
            return {"reactions": []}
        # 페르소나 가중치를 반응에 사본으로 전달(§3.7) — 집계가 가중 평균에 사용. 어댑터 무관.
        reaction = reaction.model_copy(update={"weight": persona.weight})
        return {"reactions": [reaction]}

    async def aggregate(state: RunState) -> dict:
        agg = aggregator.aggregate(state.get("reactions", []))
        # KOBACO(2019 MCR) 참고치 — 조회만, 집계 엔진 산출값과 병합·환산하지 않는다.
        kobaco = lookup_kobaco_reference(state["request"].product_category)
        if kobaco:
            agg = agg.model_copy(update={"payload": {**agg.payload, "kobaco_reference": kobaco}})
        return {"aggregate": agg}

    graph = StateGraph(RunState)
    graph.add_node("interpret_ad", interpret_ad)
    graph.add_node("load_panel", load_panel)
    graph.add_node("react", react)
    graph.add_node("aggregate", aggregate)

    graph.add_edge(START, "interpret_ad")
    graph.add_edge("interpret_ad", "load_panel")
    # 단일 입력 노드(load_panel)에서 fan-out → react map 은 한 번만 디스패치된다.
    graph.add_conditional_edges("load_panel", fan_out, ["react"])
    graph.add_edge("react", "aggregate")
    graph.add_edge("aggregate", END)
    return graph.compile()
