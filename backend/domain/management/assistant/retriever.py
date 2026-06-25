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
from core.models import ManagementKbChunk, ManagementKbDocument

EMBEDDING_MODEL = "text-embedding-3-small"  # 1536차원 — Vector(1536)와 일치
_RRF_K = 60  # Reciprocal Rank Fusion 상수 (랭킹 합산 — 점수 스케일 정규화 불필요)

# 키워드 검색(GIN). websearch_to_tsquery는 빈/특수문자 쿼리에도 안전.
# 문서(management_kb_documents) LEFT JOIN으로 출처·신뢰도(trust)를 함께 가져온다 — 벡터 채널과
# alias·순서를 동일하게 맞춰 _fuse가 양쪽 row를 같은 속성으로 읽게 한다.
_KW_SQL = text(
    "SELECT c.id, c.source, c.title, c.chunk,"
    " d.source_type, d.source_url, d.effective_from, d.metadata AS doc_metadata,"
    " ts_rank(c.search_vector, websearch_to_tsquery('simple', :q)) AS rank"
    " FROM management_kb_chunks c"
    " LEFT JOIN management_kb_documents d ON c.document_id = d.id"
    " WHERE c.search_vector @@ websearch_to_tsquery('simple', :q)"
    " ORDER BY rank DESC LIMIT :lim"
)


class KbRetriever:
    """하이브리드(벡터+키워드) 리트리버 — 세션 팩토리·임베딩 클라이언트 주입 가능(테스트)."""

    def __init__(self, api_key: str | None = None, session_factory=AsyncSessionLocal) -> None:
        # 클라이언트 지연 생성 — keyword_search는 임베딩이 없어 키 없이도 동작한다.
        self._api_key = api_key
        self._client_obj: AsyncOpenAI | None = None
        self._sf = session_factory

    @property
    def _client(self) -> AsyncOpenAI:
        if self._client_obj is None:
            self._client_obj = (
                AsyncOpenAI(api_key=self._api_key) if self._api_key else AsyncOpenAI()
            )
        return self._client_obj

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.embeddings.create(model=EMBEDDING_MODEL, input=[text])
        return resp.data[0].embedding

    async def keyword_search(self, query: str, k: int = 4) -> list[dict]:
        """임베딩 없는 키워드(GIN) 전용 검색 — 키 없는 폴백·데모 재현용(게이트 #9).

        벡터 채널을 못 쓰는 환경에서 정확 토큰(CPM·CTR·BID_LOSS 등)으로 KB 근거를 잡는다.
        """
        async with self._sf() as db:
            kw = (await db.execute(_KW_SQL, {"q": query, "lim": max(k * 3, 8)})).all()
        return [self._to_hit(r, 1.0 / (i + 1)) for i, r in enumerate(kw[:k])]

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
                        ManagementKbDocument.source_type,
                        ManagementKbDocument.source_url,
                        ManagementKbDocument.effective_from,
                        ManagementKbDocument.doc_metadata,
                        dist,
                    )
                    .join(
                        ManagementKbDocument,
                        ManagementKbChunk.document_id == ManagementKbDocument.id,
                        isouter=True,
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
        return [KbRetriever._to_hit(x["r"], x["s"]) for x in top]

    @staticmethod
    def _to_hit(r, score: float) -> dict:
        """검색 row → 답변 인용용 dict. 문서 신뢰도(trust)·출처·시점을 함께 싣는다."""
        meta = getattr(r, "doc_metadata", None) or {}
        return {
            "source": r.source,
            "title": r.title,
            "chunk": r.chunk,
            "score": round(score, 4),  # RRF 융합 점수(상대 랭킹용)
            # trust: system_backed(단정) | advisory(참고·단서) | reference(구성만)
            "trust": meta.get("trust", "system_backed"),
            "source_url": getattr(r, "source_url", None),
            "as_of": meta.get("as_of"),
            "source_type": getattr(r, "source_type", None),
        }
