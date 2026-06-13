# Composition Root — 어댑터를 골라 SimulationService에 주입하는 유일한 지점
#
# 현재는 Mock 어댑터만 연결. 실제 LLM 어댑터(tools/ 이전 후)는 use_mock=False 분기로 추가.
from __future__ import annotations

from pathlib import Path

from domain.simulation.adapters.memory_store import InMemorySimulationStore
from domain.simulation.adapters.mock_engine import (
    MockAdInterpreter,
    MockQaGate,
    MockReactionEngine,
    MockRubricEvaluator,
)
from domain.simulation.graph.reaction_graph import build_reaction_graph
from domain.simulation.graph.run_graph import build_run_graph
from domain.simulation.service.simulation_service import SimulationService
from domain.simulation.tools.aggregation.aggregator import BasicAggregator
from domain.simulation.tools.panel.builder import CachedPanelProvider
from domain.simulation.tools.sampling.persona_sampler import PersonaSampler

_DEFAULT_PANEL = Path(__file__).resolve().parent / "data" / "panels" / "panel-v1.json"


def build_panel_provider(settings=None):
    """패널 공급자 — 빌드된 고정 패널(§3.6)이 있으면 로드, 없으면 실 인구 grounding 샘플러.

    샘플러는 행안부 인구·OCEAN·소비가치 분포에서 통계 샘플링(LLM✗). 서사는 빈 채(반응 mock 무관).
    """
    if _DEFAULT_PANEL.exists():
        return CachedPanelProvider(_DEFAULT_PANEL)
    return PersonaSampler()


def build_reaction_subgraph(settings=None):
    """반응+QA 재시도 서브그래프(컴파일본)를 빌드한다. 현재는 Mock 어댑터만 연결.

    P6에서 바깥 fan-out(Send) 그래프가 이 서브그래프를 페르소나별로 호출한다.
    """
    use_mock = getattr(settings, "use_mock", True) if settings is not None else True
    if not use_mock:
        raise NotImplementedError("실 LLM 반응 어댑터 + QA 어댑터는 tools/ 이전 후 연결 예정")
    return build_reaction_graph(reactor=MockReactionEngine(), qa=MockQaGate())


def build_simulation_service(settings=None) -> SimulationService:
    use_mock = getattr(settings, "use_mock", True) if settings is not None else True
    if not use_mock:
        # TODO(추후): LLM 어댑터(vision/exposure/deliberation/ssr) + DB SimulationStore 연결
        raise NotImplementedError("실 LLM 어댑터는 tools/ 이전 후 연결 예정")

    graph = build_run_graph(
        interpreter=MockAdInterpreter(),
        panel=build_panel_provider(settings),  # 실 인구 grounding 샘플러(또는 고정 패널)
        rubric=MockRubricEvaluator(),
        aggregator=BasicAggregator(),
        reaction_graph=build_reaction_subgraph(settings),
    )
    return SimulationService(graph=graph, store=InMemorySimulationStore())
