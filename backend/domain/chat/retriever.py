# CLIO KB 벡터 검색 — pgvector 코사인 top-k (RAG retrieval)
"""쿼리를 임베딩해 clio_kb_chunks에서 코사인 유사 청크를 가져온다.

CLIO의 광고 일반 지식 답변에만 쓰며, 시뮬·제너·매니지 도메인 KB와 섞지 않는다.
"""

from __future__ import annotations

from openai import AsyncOpenAI
from sqlalchemy import select

from core.db import AsyncSessionLocal
from core.models import ClioKbChunk
from domain.chat.kb_ingest import EMBEDDING_MODEL


class ClioKbRetriever:
    """pgvector 코사인 검색 리트리버 — 세션 팩토리·임베딩 클라이언트 주입 가능."""

    def __init__(self, api_key: str | None = None, session_factory=AsyncSessionLocal) -> None:
        self._client = AsyncOpenAI(api_key=api_key) if api_key else AsyncOpenAI()
        self._sf = session_factory

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.embeddings.create(model=EMBEDDING_MODEL, input=[text])
        return resp.data[0].embedding

    async def search(self, query: str, k: int = 4) -> list[dict]:
        emb = await self.embed(query)
        dist = ClioKbChunk.embedding.cosine_distance(emb).label("dist")
        async with self._sf() as db:
            rows = (await db.execute(select(ClioKbChunk, dist).order_by(dist).limit(k))).all()
        return [
            {
                "source": r.ClioKbChunk.source,
                "title": r.ClioKbChunk.title,
                "chunk": r.ClioKbChunk.chunk,
                "score": round(1.0 - float(r.dist), 3),
            }
            for r in rows
        ]
