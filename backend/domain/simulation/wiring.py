# Composition Root — 어댑터를 골라 SimulationService에 주입하는 유일한 지점
#
# 현재는 Mock 어댑터만 연결. 실제 LLM 어댑터(tools/ 이전 후)는 use_mock=False 분기로 추가.
from __future__ import annotations

from domain.simulation.adapters.memory_store import InMemorySimulationStore
from domain.simulation.adapters.mock_engine import (
    MockAdInterpreter,
    MockPanelProvider,
    MockReactionEngine,
    MockRubricEvaluator,
)
from domain.simulation.aggregation.aggregator import BasicAggregator
from domain.simulation.service.simulation_service import SimulationService


def build_simulation_service(settings=None) -> SimulationService:
    use_mock = getattr(settings, "use_mock", True) if settings is not None else True
    if not use_mock:
        # TODO(추후): LLM 어댑터(vision/exposure/deliberation/ssr) + DB SimulationStore 연결
        raise NotImplementedError("실 LLM 어댑터는 tools/ 이전 후 연결 예정")

    return SimulationService(
        interpreter=MockAdInterpreter(),
        panel=MockPanelProvider(),
        reactor=MockReactionEngine(),
        rubric=MockRubricEvaluator(),
        aggregator=BasicAggregator(),
        store=InMemorySimulationStore(),
    )
