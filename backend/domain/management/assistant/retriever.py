# 매니지먼트 KB 하이브리드 검색 — pgvector 코사인 + GIN 키워드(tsvector), RRF 융합
"""쿼리를 임베딩(의미)해 코사인 검색하고, 동시에 키워드(GIN)로 정확 용어를 잡아 RRF로 합친다.

벡터만 쓰면 ROAS·PENDING_REVIEW·BID_LOSS 같은 정확 토큰을 놓칠 수 있어, 키워드 검색을 더해
재현율을 높인다. 숫자가 아니라 '판단·가이드'(정책·플레이북·KPI 규칙) 근거용 — 출처(source·title)로
답변에 인용한다. 임베딩은 OpenAI text-embedding-3-small(1536).
"""

from __future__ import annotations

from openai import AsyncOpenAI
from sqlalchemy import TextClause, select, text

from core.db import AsyncSessionLocal
from core.models import ManagementKbChunk, ManagementKbDocument

EMBEDDING_MODEL = "text-embedding-3-small"  # 1536차원 — Vector(1536)와 일치
_RRF_K = 60  # Reciprocal Rank Fusion 상수 (랭킹 합산 — 점수 스케일 정규화 불필요)

# source_type 스코프 — ADVISE(일반지식)와 MANAGE(특화) 검색 풀을 분리해 상호 오염을 막는다.
# general_knowledge는 ADVISE 전용. management 검색(search_kb·eval)은 아래 특화 타입만 본다.
# (kb_ingest._SOURCE_META의 source_type과 일치 — 신규 management 타입 추가 시 여기 갱신.)
GENERAL_SOURCE_TYPE = "general_knowledge"
MANAGEMENT_SOURCE_TYPES = frozenset({"meta_official", "playbook", "benchmark", "internal_policy"})


def _kw_sql(has_type_filter: bool) -> TextClause:
    """키워드 검색(GIN) SQL — source_type 필터 유무에 따라 동적 생성.

    websearch_to_tsquery는 빈/특수문자 쿼리에도 안전. 문서 LEFT JOIN으로 출처·신뢰도(trust)를
    함께 가져온다 — 벡터 채널과 alias·순서를 동일하게 맞춰 _fuse가 양쪽 row를 같게 읽게 한다.
    """
    sql = (
        "SELECT c.id, c.source, c.title, c.chunk,"
        " d.source_type, d.source_url, d.effective_from, d.metadata AS doc_metadata,"
        " ts_rank(c.search_vector, websearch_to_tsquery('simple', :q)) AS rank"
        " FROM management_kb_chunks c"
        " LEFT JOIN management_kb_documents d ON c.document_id = d.id"
        " WHERE c.search_vector @@ websearch_to_tsquery('simple', :q)"
        " AND d.status = 'active'"
    )
    if has_type_filter:
        sql += " AND d.source_type = ANY(:types)"  # 양 채널 동일 필터(융합 전 범위 일치)
    sql += " ORDER BY rank DESC LIMIT :lim"
    return text(sql)


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

    async def keyword_search(
        self, query: str, k: int = 4, source_types: frozenset[str] | None = None
    ) -> list[dict]:
        """임베딩 없는 키워드(GIN) 전용 검색 — 키 없는 폴백·데모 재현용(게이트 #9).

        벡터 채널을 못 쓰는 환경에서 정확 토큰(CPM·CTR·BID_LOSS 등)으로 KB 근거를 잡는다.
        source_types로 검색 풀 한정(예: management 특화만, 또는 general_knowledge만).
        """
        types = list(source_types) if source_types else None
        params: dict = {"q": query, "lim": max(k * 3, 8)}
        if types:
            params["types"] = types
        async with self._sf() as db:
            kw = (await db.execute(_kw_sql(bool(types)), params)).all()
        return [self._to_hit(r, 1.0 / (i + 1)) for i, r in enumerate(kw[:k])]

    async def search(
        self, query: str, k: int = 4, source_types: frozenset[str] | None = None
    ) -> list[dict]:
        """하이브리드 검색. source_types로 검색 풀 한정(None=전체).

        ADVISE는 general_knowledge만, MANAGE(search_kb·eval)는 MANAGEMENT_SOURCE_TYPES만 넘겨
        일반지식↔특화 상호 오염을 막는다(양 채널 동일 필터 → 융합 전 범위 일치).
        """
        emb = await self.embed(query)
        pool = max(k * 3, 8)  # 융합 전 각 채널에서 넉넉히 가져온다
        types = list(source_types) if source_types else None
        dist = ManagementKbChunk.embedding.cosine_distance(emb).label("dist")
        async with self._sf() as db:
            vq = (
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
                .where(ManagementKbDocument.status == "active")
            )
            if types:
                vq = vq.where(ManagementKbDocument.source_type.in_(types))
            vec = (await db.execute(vq.order_by(dist).limit(pool))).all()
            kw_params: dict = {"q": query, "lim": pool}
            if types:
                kw_params["types"] = types
            kw = (await db.execute(_kw_sql(bool(types)), kw_params)).all()
        return self._fuse(vec, kw, k)

    @staticmethod
    def _fuse(vec: list, kw: list, k: int) -> list[dict]:
        """RRF — 두 랭킹의 (1/(K+순위)) 합으로 재정렬. 두 채널에 다 잡힌 청크가 상위로."""
        fused: dict[str, dict] = {}
        for rank, r in enumerate(vec):
            entry = fused.setdefault(str(r.id), {"r": r, "s": 0.0, "cos": None})
            entry["s"] += 1.0 / (_RRF_K + rank + 1)
            # cosine_distance → cosine_similarity (1 - dist). KB 게이트 threshold 판단용.
            entry["cos"] = round(1.0 - float(r.dist), 4)
        for rank, r in enumerate(kw):
            key = str(r.id)
            entry = fused.setdefault(key, {"r": r, "s": 0.0, "cos": None})
            entry["s"] += 1.0 / (_RRF_K + rank + 1)
        top = sorted(fused.values(), key=lambda x: x["s"], reverse=True)[:k]
        return [KbRetriever._to_hit(x["r"], x["s"], x["cos"]) for x in top]

    @staticmethod
    def _to_hit(r, score: float, cosine_score: float | None = None) -> dict:
        """검색 row → 답변 인용용 dict. 문서 신뢰도(trust)·출처·시점을 함께 싣는다."""
        meta = getattr(r, "doc_metadata", None) or {}
        return {
            "source": r.source,
            "title": r.title,
            "chunk": r.chunk,
            "score": round(score, 4),  # RRF 융합 점수(상대 랭킹용)
            "cosine_score": cosine_score,  # 코사인 유사도(KB 게이트 threshold 판단용, 벡터 채널만)
            # trust: system_backed(단정) | advisory(참고·단서) | reference(구성만)
            "trust": meta.get("trust", "system_backed"),
            "source_url": getattr(r, "source_url", None),
            "as_of": meta.get("as_of"),
            "source_type": getattr(r, "source_type", None),
        }
