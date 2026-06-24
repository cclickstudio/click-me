# KbRetriever가 주입된 EmbeddingProvider로 임베딩하는지(1024) hermetic 검증.
import pytest

from domain.chat.adapters.embeddings import MockEmbeddingProvider
from domain.management.assistant.retriever import KbRetriever


@pytest.mark.asyncio
async def test_retriever_uses_injected_provider():
    provider = MockEmbeddingProvider(dim=1024)
    r = KbRetriever(embedder=provider, session_factory=None)
    emb = await r.embed("캠페인 예산 가이드")
    assert len(emb) == 1024
