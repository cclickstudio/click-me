# 임베딩 어댑터 — Mock(결정론)·TEI(BGE-M3 로컬)·OpenAI(폴백). EmbeddingProvider 구현.
"""KB·LTM 공유 임베딩. 기본 TEI(/embed, BGE-M3 1024). USE_MOCK/키부재 시 Mock."""

from __future__ import annotations

import hashlib
import struct

import httpx


class MockEmbeddingProvider:
    """결정론 mock — 텍스트 해시 시드로 단위벡터 생성(테스트·USE_MOCK)."""

    def __init__(self, dim: int = 1024) -> None:
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


class TeiEmbeddingProvider:
    """text-embeddings-inference /embed — BGE-M3(1024). Ollama는 base_url·경로만 교체."""

    def __init__(
        self, base_url: str, *, dim: int = 1024, client: httpx.AsyncClient | None = None
    ) -> None:
        self._base = base_url.rstrip("/")
        self._dim = dim
        self._client = client or httpx.AsyncClient(base_url=self._base, timeout=30.0)

    @property
    def dim(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.post("/embed", json={"inputs": texts})
        resp.raise_for_status()
        return resp.json()  # TEI: list[list[float]]


class OpenAIEmbeddingProvider:
    """OpenAI 폴백 — text-embedding-3-small(1536). provider=openai 시 embedding_dim=1536 필요."""

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
