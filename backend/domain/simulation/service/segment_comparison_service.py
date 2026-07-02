# Persona Set(3-모드 UX §A-1) — 같은 광고를 여러 타깃 세그먼트로 나눠 나란히 비교
#
# 광고 해석·루브릭은 세그먼트 수와 무관하게 1회만(비용·일관성). 세그먼트마다 패널 부분집합
# 로드 → 반응 fan-out → 집계만 반복한다. 그래프(LangGraph) 재사용 없이 서비스 레이어에서
# 기존 컴포넌트(interpreter·rubric·panel·reaction_graph·aggregator)를 직접 조립한다.
from __future__ import annotations

import asyncio
import logging

from domain.simulation.contracts.schemas import (
    PanelSpec,
    PersonaReaction,
    SegmentSpec,
    SimulationRunRequest,
)
from domain.simulation.graph.reaction_graph import run_reaction
from domain.simulation.graph.run_graph import interpret_and_score

logger = logging.getLogger("clickme")


class SegmentComparisonService:
    """Persona Set 비교 — wiring.py가 조립한 컴포넌트를 주입받는다(덕타이핑, run_graph와 동일)."""

    def __init__(self, *, interpreter, rubric, panel, reaction_graph, aggregator) -> None:
        self._interpreter = interpreter
        self._rubric = rubric
        self._panel = panel
        self._reaction_graph = reaction_graph
        self._aggregator = aggregator

    async def _run_segment_reactions(self, personas, ad) -> list[PersonaReaction]:
        async def _one(persona) -> PersonaReaction | None:
            try:
                reaction = await run_reaction(self._reaction_graph, persona, ad)
            except Exception as exc:  # 한 명 실패는 건너뜀(run_graph.react와 동일 정책)
                logger.warning("세그먼트 페르소나 %s 반응 실패: %s", persona.persona_id, exc)
                return None
            return reaction.model_copy(update={"weight": persona.weight})

        results = await asyncio.gather(*(_one(p) for p in personas))
        return [r for r in results if r is not None]

    async def run(self, request: SimulationRunRequest, segments: list[SegmentSpec]) -> dict:
        ad, rubric_scores = await interpret_and_score(self._interpreter, self._rubric, request)

        segment_results = []
        for seg in segments:
            spec = PanelSpec(
                size=seg.sample_size, target_filter=seg.target_filter, allocation=request.allocation
            )
            panel_version, personas = await self._panel.get_or_build(spec)
            reactions = await self._run_segment_reactions(personas, ad)
            aggregate = self._aggregator.aggregate(reactions)
            segment_results.append(
                {
                    "label": seg.label,
                    "target_filter": seg.target_filter,
                    "panel_version": panel_version,
                    "sample_size": len(personas),
                    "personas": personas,
                    "reactions": reactions,
                    "aggregate": aggregate,
                }
            )

        return {"ad": ad, "rubric_scores": rubric_scores, "segments": segment_results}
