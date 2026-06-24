# Composition Root — 어댑터를 골라 SimulationService에 주입하는 유일한 지점
#
# 시뮬레이션 경로는 항상 실 LLM(gpt-4o-mini, mock 폴백 없음). 토론은 use_mock 유지.
from __future__ import annotations

import os
from pathlib import Path

from domain.simulation.adapters.memory_store import InMemorySimulationStore
from domain.simulation.graph.reaction_graph import build_reaction_graph
from domain.simulation.graph.run_graph import build_run_graph
from domain.simulation.service.debate_service import DebateService
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
    Meta 전용 — 표본을 인구×소셜도달 비율로 추출(§Tier1). 고정 패널도 같은 옵션으로 빌드해야 정합.
    """
    if _DEFAULT_PANEL.exists():
        return CachedPanelProvider(_DEFAULT_PANEL)
    # Meta 플랫폼(instagram/facebook) 지정 시 그 도달 분포로 추출 — 실데이터 없으면 통합 reach 폴백.
    platform = getattr(settings, "meta_platform", None) if settings is not None else None
    return PersonaSampler(reachability_sampling=True, platform=platform)


def _resolve_use_mock(settings, use_mock) -> bool:
    if use_mock is not None:
        return use_mock
    return getattr(settings, "use_mock", True) if settings is not None else True


def build_reaction_subgraph(settings=None, *, use_llm_qa=None):
    """반응+QA 재시도 서브그래프(컴파일본). 항상 실 LLM(gpt-4o-mini) 반응 + QA(§P4, mock 폴백 없음).

    QA 기본은 규칙(무콜). use_llm_qa=True(또는 settings.use_llm_qa)면 GeminiQaGate(콜 2배, opt-in).
    """
    _ensure_env("OPENAI_API_KEY")
    from domain.simulation.adapters.gemini import (
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
    settings=None, *, session_factory=None, use_llm_qa=None
) -> SimulationService:
    """Composition Root. 광고해석·반응·루브릭을 실 LLM(gpt-4o-mini)로 연결(§P4, mock 없음).

    OPENAI_API_KEY 미설정 시 어댑터 생성 단계에서 RuntimeError(폴백 대신 오류).
    use_llm_qa=True면 반응 QA를 LLM(GeminiQaGate)로(콜 2배, opt-in). 기본은 규칙 QA.
    """
    _ensure_env("OPENAI_API_KEY")
    from domain.simulation.adapters.gemini import (
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
        reaction_graph=build_reaction_subgraph(settings, use_llm_qa=use_llm_qa),
    )
    return SimulationService(
        graph=graph,
        store=InMemorySimulationStore(),
        persistence=build_persistence(settings, session_factory),
    )


def build_debate_persistence(settings=None, session_factory=None):
    """토론 영속화 어댑터(DebateRepository). DB 미구성이면 None → service는 인메모리만(저장 생략).

    simulation_id FK(NOT NULL) 때문에 실제 simulations 행이 있는 운영 경로에서만 저장된다.
    """
    if session_factory is None:
        if settings is None or not getattr(settings, "database_url", None):
            return None
        from core.db import AsyncSessionLocal

        session_factory = AsyncSessionLocal
    from domain.simulation.repositories.debate_repository import DebateRepository

    return DebateRepository(session_factory)


def _resolve_session_factory(settings=None, session_factory=None) -> object | None:
    """DB 세션 팩토리 결정 — 명시 주입 우선, 없으면 settings.database_url에서 파생(미구성이면 None).

    report_view 재조립(get_saved_report)은 시뮬 결과를 같은 세션 팩토리로 재조회한다.
    """
    if session_factory is not None:
        return session_factory
    if settings is None or not getattr(settings, "database_url", None):
        return None
    from core.db import AsyncSessionLocal

    return AsyncSessionLocal


def build_debate_service(
    settings=None, *, store=None, use_mock=None, session_factory=None
) -> DebateService:
    """토론 파이프라인 Composition Root. use_mock=True면 mock 토론 엔진 주입(재현·무비용).

    실 LLM 엔진(Haiku/GPT/Gemini 토론자 + Sonnet Judge)은 use_mock=False 분기로 연결.
    엔진 미주입이면 결정론 파이프라인(8~9·10-a·10-b·11)만 돌고 10-c는 placeholder.
    """
    store = store or InMemorySimulationStore()
    sim_session_factory = _resolve_session_factory(settings, session_factory)
    persistence = build_debate_persistence(settings, session_factory)
    if _resolve_use_mock(settings, use_mock):
        from domain.simulation.adapters.mock_debate import MockDebater, MockJudge

        return DebateService(
            store=store,
            debater_factory=lambda reactions: MockDebater(reactions),
            judge=MockJudge(),
            persistence=persistence,
            sim_session_factory=sim_session_factory,
        )

    # 토론자 Haiku/GPT + Judge Sonnet (Gemini 제거 — 응답 실패 잦음)
    _ensure_env("ANTHROPIC_API_KEY", "OPENAI_API_KEY")
    from domain.simulation.adapters.llm_debate import LLMDebater, LLMJudge, _Clients
    from domain.simulation.adapters.llm_selector import LLMSelector

    # 토론자·Judge가 _Clients를 공유 → 토론 1회 토큰을 한곳에 누적(usage_clients로 서비스에 노출).
    shared_clients = _Clients()

    # 일반인 선발(10-a) 동점 시 LLM 재랭킹(Sonnet 다수결) — 실 LLM 경로에서만 켠다.
    return DebateService(
        store=store,
        debater_factory=lambda reactions: LLMDebater(reactions, clients=shared_clients),
        judge=LLMJudge(clients=shared_clients),
        persistence=persistence,
        sim_session_factory=sim_session_factory,
        selector_rerank_fn=LLMSelector().choose,
        usage_clients=shared_clients,
    )
