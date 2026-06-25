# 챗 Composition Root — 어댑터를 포트에 꽂는 유일한 지점(mock↔실연동 전환).
"""임베딩·repo·memory·checkpointer·subagents·graph·orchestrator 빌더의 단일 조립 지점."""

from __future__ import annotations

from core.config import settings
from domain.chat.contracts.ports import EmbeddingProvider


def build_embedding_provider(s=settings) -> EmbeddingProvider:
    """USE_MOCK/mock → Mock. bge_m3 → TEI. bge_m3_local → 인프로세스 BGE-M3. openai → 1536 폴백."""
    provider = getattr(s, "embedding_provider", "bge_m3")
    dim = getattr(s, "embedding_dim", 1024)

    if getattr(s, "use_mock", True) or provider == "mock":
        from domain.chat.adapters.embeddings import MockEmbeddingProvider

        return MockEmbeddingProvider(dim=dim)

    if provider == "bge_m3_local":  # TEI 서버 없이 sentence-transformers로 인프로세스 임베딩(1024)
        from domain.chat.adapters.embeddings import LocalBgeEmbeddingProvider

        return LocalBgeEmbeddingProvider(dim=dim)

    if provider == "openai":
        from domain.chat.adapters.embeddings import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider(
            api_key=s.openai_api_key, model=s.openai_embedding_model, dim=dim
        )

    from domain.chat.adapters.embeddings import TeiEmbeddingProvider

    return TeiEmbeddingProvider(base_url=s.embedding_base_url, dim=dim)


def build_chat_repo(s=settings):  # s: 향후 커넥션 설정 주입 예정. 현재 PgChatRepo는 미사용.
    """세션·메시지 영속 — 단일 구현(PgChatRepo). 세션 팩토리는 core 기본."""
    from domain.chat.adapters.pg_chat_repo import PgChatRepo

    return PgChatRepo()


def build_memory_store(s=settings):
    """롱텀 메모리 — EmbeddingProvider 주입(KB와 동일 구현)."""
    from domain.chat.adapters.pg_memory_store import PgMemoryStore

    return PgMemoryStore(embedder=build_embedding_provider(s))


async def build_checkpointer(s=settings):
    """그래프 체크포인터 — USE_MOCK/테스트는 MemorySaver, 실연동은 AsyncPostgresSaver.

    awaitable — 반드시 await. AsyncPostgresSaver는 풀 정리가 필요하므로 (saver, close)를 반환한다.
    """
    if getattr(s, "use_mock", True):
        from langgraph.checkpoint.memory import MemorySaver

        async def _noop() -> None:
            """MemorySaver는 정리 불필요 — close 계약을 맞추는 no-op."""

        return MemorySaver(), _noop

    from domain.chat.checkpointer import build_async_checkpointer

    return await build_async_checkpointer(s.database_url)


def build_subagents(s=settings) -> dict:
    """라우트 값 → SubAgent. general은 서브에이전트 없음(synthesize 직행)."""
    from domain.chat.adapters.generator_subagent import GeneratorSubAgent
    from domain.chat.adapters.management_subagent import ManagementSubAgent
    from domain.chat.adapters.simulation_subagent import SimulationSubAgent
    from domain.chat.contracts.agent_io import Route

    return {
        Route.MANAGEMENT.value: ManagementSubAgent(settings=s),
        Route.SIMULATION.value: SimulationSubAgent(),
        Route.GENERATION.value: GeneratorSubAgent(),
    }


async def build_orchestrator(s=settings):
    """ChatOrchestratorService 조립 — llm·repo·memory·subagents·executor·checkpointer 주입.

    체크포인터 close 콜백은 서비스에 주입해 `service.aclose()`로 노출한다 — 라우터가
    싱글톤을 보관하고 FastAPI lifespan 종료 단계에서 aclose()를 호출(풀 누수 방지).
    use_mock 경로는 noop 콜백이라 aclose()도 무해하게 통과한다.
    """
    from domain.chat.adapters.clio import build_clio
    from domain.chat.adapters.llm_factory import build_supervisor_llm
    from domain.chat.graph.builder import ChatGraphDeps, build_chat_graph
    from domain.chat.service.orchestrator import ChatOrchestratorService
    from domain.management.wiring import build_executor

    saver, close = await build_checkpointer(s)
    repo = build_chat_repo(s)
    deps = ChatGraphDeps(
        llm=build_supervisor_llm(s),
        repo=repo,
        memory=build_memory_store(s),
        subagents=build_subagents(s),
        executor=build_executor(s),
        settings=s,
        clio=build_clio(s),
    )
    graph = build_chat_graph(deps, checkpointer=saver)
    return ChatOrchestratorService(graph=graph, repo=repo, settings=s, checkpointer_close=close)
