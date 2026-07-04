# 매니지먼트 RAG 임베딩 — provider(mock|openai)별 EmbeddingProvider 구현·빌더.
"""KB·LTM 공유 임베딩. 기본 OpenAI text-embedding-3-small(1536). USE_MOCK 시 Mock."""

from __future__ import annotations

import hashlib
import struct
from typing import Protocol

from core.config import settings


class EmbeddingProvider(Protocol):
    """텍스트 → 임베딩 벡터. KB·LTM이 동일 구현(동일 모델·차원)을 공유한다."""

    @property
    def dim(self) -> int: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class MockEmbeddingProvider:
    """결정론 mock — 텍스트 해시 시드로 단위벡터 생성(테스트·USE_MOCK)."""

    def __init__(self, dim: int = 1536) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def _vec(self, text: str) -> list[float]:
        out: list[float] = []
        i = 0
        while len(out) < self._dim:
            h = hashlib.sha256(f"{text}:{i}".encode()).digest()
            for j in range(0, len(h), 4):
                if len(out) >= self._dim:
                    break
                out.append(struct.unpack("<I", h[j : j + 4])[0] / 2**32)
            i += 1
        norm = sum(x * x for x in out) ** 0.5 or 1.0
        return [x / norm for x in out]


class OpenAIEmbeddingProvider:
    """OpenAI text-embedding-3-small(1536) — Vector(1536) 컬럼과 동일 차원."""

    def __init__(
        self, *, api_key: str, model: str = "text-embedding-3-small", dim: int = 1536
    ) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in resp.data]


def build_embedding_provider(s=settings) -> EmbeddingProvider:
    """USE_MOCK/mock → Mock. 그 외 → OpenAI(text-embedding-3-small, 1536)."""
    provider = getattr(s, "embedding_provider", "openai")
    dim = getattr(s, "embedding_dim", 1536)

    if getattr(s, "use_mock", True) or provider == "mock":
        return MockEmbeddingProvider(dim=dim)
    return OpenAIEmbeddingProvider(api_key=s.openai_api_key, model=s.embedding_model, dim=dim)
