# Composition Root — 어댑터를 골라 SimulationService에 주입하는 유일한 지점
#
# 현재는 Mock 어댑터만 연결. 실제 LLM 어댑터(tools/ 이전 후)는 use_mock=False 분기로 추가.
from __future__ import annotations

import os
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

_DEFAULT_PANEL = (
    Path(__file__).resolve().parent / "data" / "simulation" / "panels" / "panel-v1.json"
)
# 프로젝트 루트·backend의 .env (config.py가 backend/.env만 보고 필수키 부재로 깨지므로 직접 적재)
_ENV_FILES = (
    Path(__file__).resolve().parents[3] / ".env",
    Path(__file__).resolve().parents[2] / ".env",
)


def _ensure_env(*keys: str) -> None:
    """필요한 키가 os.environ에 없으면 .env 파일에서 읽어 채운다(실 LLM 어댑터용)."""
    missing = [k for k in keys if not os.environ.get(k)]
    if not missing:
        return
    for env_file in _ENV_FILES:
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k in missing and v and not os.environ.get(k):
                os.environ[k] = v


def build_panel_provider(settings=None):
    """패널 공급자 — 빌드된 고정 패널(§3.6)이 있으면 로드, 없으면 실 인구 grounding 샘플러.

    샘플러는 행안부 인구·OCEAN·소비가치 분포에서 통계 샘플링(LLM✗). 서사는 빈 채(반응 mock 무관).
    """
    if _DEFAULT_PANEL.exists():
        return CachedPanelProvider(_DEFAULT_PANEL)
    return PersonaSampler()


def _resolve_use_mock(settings, use_mock) -> bool:
    if use_mock is not None:
        return use_mock
    return getattr(settings, "use_mock", True) if settings is not None else True


def build_reaction_subgraph(settings=None, *, use_mock=None, use_llm_qa=None):
    """반응+QA 재시도 서브그래프(컴파일본). use_mock=False면 Gemini 반응 + QA(§P4).

    QA 기본은 규칙(무콜). use_llm_qa=True(또는 settings.use_llm_qa)면 GeminiQaGate(콜 2배, opt-in).
    """
    if _resolve_use_mock(settings, use_mock):
        return build_reaction_graph(reactor=MockReactionEngine(), qa=MockQaGate())
    _ensure_env("GEMINI_API_KEY")
    from domain.simulation.adapters.gemini_engine import (
        GeminiQaGate,
        GeminiReactionEngine,
        RuleQaGate,
    )

    if use_llm_qa is None:
        use_llm_qa = getattr(settings, "use_llm_qa", False) if settings is not None else False
    qa = GeminiQaGate() if use_llm_qa else RuleQaGate()
    return build_reaction_graph(reactor=GeminiReactionEngine(), qa=qa)


def build_persistence(settings=None, session_factory=None):
    """완료 런 DB 영속화 어댑터. session_factory 우선, 없으면 settings.database_url에서 파생.

    DB가 구성돼 있지 않으면(개발/.env 미설정·테스트) None → service는 인메모리 결과만 유지.
    core.db 는 함수 안에서만 import (모듈 로드 시 settings 강제 평가를 피함).
    """
    if session_factory is None:
        if settings is None or not getattr(settings, "database_url", None):
            return None
        from core.db import AsyncSessionLocal  # settings 구성된 경우에만 안전하게 로드

        session_factory = AsyncSessionLocal
    from domain.simulation.repositories.persistence import SimulationPersistence

    return SimulationPersistence(session_factory)


def build_simulation_service(
    settings=None, *, session_factory=None, use_mock=None, use_llm_qa=None
) -> SimulationService:
    """Composition Root. use_mock=False면 광고해석·반응·루브릭을 실 Gemini로 연결(§P4).

    use_llm_qa=True면 반응 QA를 LLM(GeminiQaGate)로(콜 2배, opt-in). 기본은 규칙 QA.
    """
    if _resolve_use_mock(settings, use_mock):
        interpreter = MockAdInterpreter()
        rubric = MockRubricEvaluator()
    else:
        _ensure_env("GEMINI_API_KEY")
        from domain.simulation.adapters.gemini_engine import (
            GeminiAdInterpreter,
            GeminiRubricEvaluator,
        )

        interpreter = GeminiAdInterpreter()
        rubric = GeminiRubricEvaluator()

    graph = build_run_graph(
        interpreter=interpreter,
        panel=build_panel_provider(settings),  # 실 인구 grounding 샘플러(또는 고정 패널)
        rubric=rubric,
        aggregator=BasicAggregator(),
        reaction_graph=build_reaction_subgraph(settings, use_mock=use_mock, use_llm_qa=use_llm_qa),
    )
    return SimulationService(
        graph=graph,
        store=InMemorySimulationStore(),
        persistence=build_persistence(settings, session_factory),
    )
