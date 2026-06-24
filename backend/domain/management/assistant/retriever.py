# 매니지먼트 KB 벡터 검색 — pgvector 코사인 top-k (RAG retrieval)
"""쿼리를 임베딩해 management_kb_chunks에서 코사인 유사 청크를 가져온다.

임베딩은 EmbeddingProvider(기본 BGE-M3 1024) — KB·LTM 동일 차원(spec §6.1/§9).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from core.db import AsyncSessionLocal
from core.models import ManagementKbChunk

if TYPE_CHECKING:
    # 타입 주석 전용 — management→chat 런타임 import 결합 회피(annotations future로 문자열화).
    from domain.chat.contracts.ports import EmbeddingProvider


class KbRetriever:
    """pgvector 코사인 검색 리트리버 — EmbeddingProvider·세션 팩토리 주입(테스트)."""

    def __init__(self, embedder: EmbeddingProvider, session_factory=AsyncSessionLocal) -> None:
        self._embedder = embedder
        self._sf = session_factory

    async def embed(self, text: str) -> list[float]:
        out = await self._embedder.embed([text])
        return out[0]

    async def search(self, query: str, k: int = 4) -> list[dict]:
        emb = await self.embed(query)
        dist = ManagementKbChunk.embedding.cosine_distance(emb).label("dist")
        async with self._sf() as db:
            rows = (await db.execute(select(ManagementKbChunk, dist).order_by(dist).limit(k))).all()
        return [
            {
                "source": r.ManagementKbChunk.source,
                "title": r.ManagementKbChunk.title,
                "chunk": r.ManagementKbChunk.chunk,
                "score": round(1.0 - float(r.dist), 3),
            }
            for r in rows
        ]
