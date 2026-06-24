# 매니지먼트 KB 하이브리드 검색 — pgvector 코사인 + GIN 키워드(tsvector), RRF 융합
"""쿼리를 임베딩(의미)해 코사인 검색하고, 동시에 키워드(GIN)로 정확 용어를 잡아 RRF로 합친다.

벡터만 쓰면 ROAS·PENDING_REVIEW·BID_LOSS 같은 정확 토큰을 놓칠 수 있어, 키워드 검색을 더해
재현율을 높인다. 숫자가 아니라 '판단·가이드'(정책·플레이북·KPI 규칙) 근거용 — 출처(source·title)로
답변에 인용한다. 임베딩은 OpenAI text-embedding-3-small(1536).
"""

from __future__ import annotations

from openai import AsyncOpenAI
from sqlalchemy import select, text

from core.db import AsyncSessionLocal
from core.models import ManagementKbChunk

EMBEDDING_MODEL = "text-embedding-3-small"  # 1536차원 — Vector(1536)와 일치
_RRF_K = 60  # Reciprocal Rank Fusion 상수 (랭킹 합산 — 점수 스케일 정규화 불필요)

# 키워드 검색(GIN). websearch_to_tsquery는 빈/특수문자 쿼리에도 안전.
_KW_SQL = text(
    "SELECT id, source, title, chunk,"
    " ts_rank(search_vector, websearch_to_tsquery('simple', :q)) AS rank"
    " FROM management_kb_chunks"
    " WHERE search_vector @@ websearch_to_tsquery('simple', :q)"
    " ORDER BY rank DESC LIMIT :lim"
)


class KbRetriever:
    """하이브리드(벡터+키워드) 리트리버 — 세션 팩토리·임베딩 클라이언트 주입 가능(테스트)."""

    def __init__(self, api_key: str | None = None, session_factory=AsyncSessionLocal) -> None:
        self._client = AsyncOpenAI(api_key=api_key) if api_key else AsyncOpenAI()
        self._sf = session_factory

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.embeddings.create(model=EMBEDDING_MODEL, input=[text])
        return resp.data[0].embedding

    async def search(self, query: str, k: int = 4) -> list[dict]:
        emb = await self.embed(query)
        pool = max(k * 3, 8)  # 융합 전 각 채널에서 넉넉히 가져온다
        dist = ManagementKbChunk.embedding.cosine_distance(emb).label("dist")
        async with self._sf() as db:
            vec = (
                await db.execute(
                    select(
                        ManagementKbChunk.id,
                        ManagementKbChunk.source,
                        ManagementKbChunk.title,
                        ManagementKbChunk.chunk,
                        dist,
                    )
                    .order_by(dist)
                    .limit(pool)
                )
            ).all()
            kw = (await db.execute(_KW_SQL, {"q": query, "lim": pool})).all()
        return self._fuse(vec, kw, k)

    @staticmethod
    def _fuse(vec: list, kw: list, k: int) -> list[dict]:
        """RRF — 두 랭킹의 (1/(K+순위)) 합으로 재정렬. 두 채널에 다 잡힌 청크가 상위로."""
        fused: dict[str, dict] = {}
        for rank, r in enumerate(vec):
            fused.setdefault(str(r.id), {"r": r, "s": 0.0})["s"] += 1.0 / (_RRF_K + rank + 1)
        for rank, r in enumerate(kw):
            key = str(r.id)
            entry = fused.setdefault(key, {"r": r, "s": 0.0})
            entry["s"] += 1.0 / (_RRF_K + rank + 1)
        top = sorted(fused.values(), key=lambda x: x["s"], reverse=True)[:k]
        return [
            {
                "source": x["r"].source,
                "title": x["r"].title,
                "chunk": x["r"].chunk,
                "score": round(x["s"], 4),  # RRF 융합 점수(상대 랭킹용)
            }
            for x in top
        ]
