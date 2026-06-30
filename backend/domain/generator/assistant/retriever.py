# 광고 생성 KB 벡터 검색 — pgvector 코사인 top-k (RAG retrieval)
"""쿼리를 임베딩해 generator_kb_chunks에서 코사인 유사 청크를 가져온다.

수치(특정 생성 결과)가 아니라 '카피 전략·원칙·톤' 근거용. 결과엔 출처(source·title)를
담아 답변에 인용한다. 임베딩은 OpenAI text-embedding-3-small(1536) — Vector(1536)와 일치.
"""

from __future__ import annotations

from openai import AsyncOpenAI
from sqlalchemy import select

from core.db import AsyncSessionLocal
from core.models import GeneratorKbChunk

EMBEDDING_MODEL = "text-embedding-3-small"  # 1536차원 — Vector(1536)와 일치


class GenKbRetriever:
    """pgvector 코사인 검색 리트리버 — 세션 팩토리·임베딩 클라이언트 주입 가능(테스트)."""

    def __init__(self, api_key: str | None = None, session_factory=AsyncSessionLocal) -> None:
        self._client = AsyncOpenAI(api_key=api_key) if api_key else AsyncOpenAI()
        self._sf = session_factory

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.embeddings.create(model=EMBEDDING_MODEL, input=[text])
        return resp.data[0].embedding

    async def search(self, query: str, k: int = 4) -> list[dict]:
        emb = await self.embed(query)
        dist = GeneratorKbChunk.embedding.cosine_distance(emb).label("dist")
        async with self._sf() as db:
            rows = (await db.execute(select(GeneratorKbChunk, dist).order_by(dist).limit(k))).all()
        return [
            {
                "source": r.GeneratorKbChunk.source,
                "title": r.GeneratorKbChunk.title,
                "chunk": r.GeneratorKbChunk.chunk,
                "score": round(1.0 - float(r.dist), 3),  # 코사인 유사도(1=동일)
            }
            for r in rows
        ]
