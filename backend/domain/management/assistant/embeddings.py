# 매니지먼트 RAG 임베딩 — provider(mock|bge_m3_local|openai|tei)별 EmbeddingProvider 구현·빌더.
"""KB·LTM 공유 임베딩. 기본 TEI(/embed, BGE-M3 1024). USE_MOCK/키부재 시 Mock."""

from __future__ import annotations

import hashlib
import struct
from typing import TYPE_CHECKING, Protocol

import httpx

from core.config import settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class EmbeddingProvider(Protocol):
    """텍스트 → 임베딩 벡터. KB·LTM이 동일 구현(동일 모델·차원)을 공유한다."""

    @property
    def dim(self) -> int: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


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

    async def aclose(self) -> None:
        """앱 종료 시 내부 생성 클라이언트 정리(주입 클라이언트는 호출측 소유)."""
        await self._client.aclose()


class LocalBgeEmbeddingProvider:
    """인프로세스 BGE-M3(sentence-transformers) — TEI 서버 없이 로컬 임베딩(1024, CPU/GPU 자동).

    provider=bge_m3_local 일 때 사용. 모델은 프로세스당 1회 로드(클래스 캐시) — 최초 호출 시 ~2.3GB
    다운로드 + 로드 지연. 적재(kb_ingest)와 런타임(retriever)이 동일 임베딩 공간을 공유한다.
    """

    _model = None  # 프로세스 공유 — 1회만 로드

    def __init__(self, *, model_name: str = "BAAI/bge-m3", dim: int = 1024) -> None:
        self._model_name = model_name
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def _get_model(self) -> SentenceTransformer:
        if LocalBgeEmbeddingProvider._model is None:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415

            LocalBgeEmbeddingProvider._model = SentenceTransformer(self._model_name)
        return LocalBgeEmbeddingProvider._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import asyncio  # noqa: PLC0415

        model = self._get_model()
        # 정규화(코사인 검색용) — TEI BGE-M3 dense 출력과 동일 공간.
        vecs = await asyncio.to_thread(
            lambda: model.encode(texts, normalize_embeddings=True, batch_size=8)
        )
        return [list(map(float, v)) for v in vecs]


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


def build_embedding_provider(s=settings) -> EmbeddingProvider:
    """USE_MOCK/mock → Mock. bge_m3 → TEI. bge_m3_local → 인프로세스 BGE-M3. openai → 1536 폴백."""
    provider = getattr(s, "embedding_provider", "bge_m3")
    dim = getattr(s, "embedding_dim", 1024)

    if getattr(s, "use_mock", True) or provider == "mock":
        return MockEmbeddingProvider(dim=dim)
    if provider == "bge_m3_local":  # TEI 서버 없이 sentence-transformers로 인프로세스 임베딩(1024)
        return LocalBgeEmbeddingProvider(dim=dim)
    if provider == "openai":
        return OpenAIEmbeddingProvider(
            api_key=s.openai_api_key, model=s.openai_embedding_model, dim=dim
        )
    return TeiEmbeddingProvider(base_url=s.embedding_base_url, dim=dim)
