# 시뮬레이션 outer 그래프 — 선형 supervisor DAG + Send fan-out(map-reduce)
#
# 토폴로지: interpret_ad → load_panel → rubric_eval → Send×N react(서브그래프) → aggregate
# 값싼 preamble 3콜은 직렬(불균등 깊이 join 회피 — defer는 구버전 langgraph에 없어 CI 위험).
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

logger = logging.getLogger("clickme")


class RunState(TypedDict, total=False):
    """outer 그래프 상태. reactions 는 Send map 의 fan-in 리듀서로 누적."""

    request: SimulationRunRequest
    ad: AdInterpretation | None
    panel_version: str | None
    personas: list[Persona]
    rubric_scores: list[RubricScore]
    reactions: Annotated[list[PersonaReaction], operator.add]
    aggregate: SimulationAggregate | None


def build_run_graph(*, interpreter, panel, rubric, aggregator, reaction_graph):
    """outer 그래프를 컴파일한다.

    기대 어댑터(덕타이핑):
      interpreter.interpret(request)  -> AdInterpretation
      panel.get_or_build(spec)        -> (panel_version, [Persona])
      rubric.evaluate(ad)             -> [RubricScore]
      aggregator.aggregate([reaction])-> SimulationAggregate
      reaction_graph                  -> P5 반응 서브그래프(컴파일본)
    """

    async def interpret_ad(state: RunState) -> dict:
        return {"ad": await interpreter.interpret(state["request"])}

    async def load_panel(state: RunState) -> dict:
        req = state["request"]
        spec = PanelSpec(size=req.sample_size, target_filter=req.target_filter)
        version, personas = await panel.get_or_build(spec)
        return {"panel_version": version, "personas": personas}

    async def rubric_eval(state: RunState) -> dict:
        return {"rubric_scores": await rubric.evaluate(state["ad"])}

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
        return {"reactions": [reaction]}

    async def aggregate(state: RunState) -> dict:
        return {"aggregate": aggregator.aggregate(state.get("reactions", []))}

    graph = StateGraph(RunState)
    graph.add_node("interpret_ad", interpret_ad)
    graph.add_node("load_panel", load_panel)
    graph.add_node("rubric_eval", rubric_eval)
    graph.add_node("react", react)
    graph.add_node("aggregate", aggregate)

    graph.add_edge(START, "interpret_ad")
    graph.add_edge("interpret_ad", "load_panel")
    graph.add_edge("load_panel", "rubric_eval")
    # 단일 입력 노드(rubric_eval)에서 fan-out → react map 은 한 번만 디스패치된다.
    graph.add_conditional_edges("rubric_eval", fan_out, ["react"])
    graph.add_edge("react", "aggregate")
    graph.add_edge("aggregate", END)
    return graph.compile()
