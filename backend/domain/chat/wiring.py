# 챗 Composition Root — 어댑터를 포트에 꽂는 유일한 지점(mock↔실연동 전환).
"""build_embedding_provider만 우선. chat_repo·memory_store·checkpointer는 후속 Task에서 추가."""

from __future__ import annotations

from core.config import settings
from domain.chat.contracts.ports import EmbeddingProvider


def build_embedding_provider(s=settings) -> EmbeddingProvider:
    """USE_MOCK/mock → Mock. bge_m3 → TEI. openai → OpenAI 폴백(1536)."""
    provider = getattr(s, "embedding_provider", "bge_m3")
    dim = getattr(s, "embedding_dim", 1024)

    if getattr(s, "use_mock", True) or provider == "mock":
        from domain.chat.adapters.embeddings import MockEmbeddingProvider

        return MockEmbeddingProvider(dim=dim)

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
