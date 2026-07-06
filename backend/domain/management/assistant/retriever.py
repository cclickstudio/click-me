# 매니지먼트 KB 하이브리드 검색 — pgvector 코사인 + GIN 키워드(tsvector), RRF 융합
"""쿼리를 임베딩(의미)해 코사인 검색하고, 동시에 키워드(GIN)로 정확 용어를 잡아 RRF로 합친다.

벡터만 쓰면 ROAS·PENDING_REVIEW·BID_LOSS 같은 정확 토큰을 놓칠 수 있어, 키워드 검색을 더해
재현율을 높인다. 숫자가 아니라 '판단·가이드'(정책·플레이북·KPI 규칙) 근거용 — 출처(source·title)로
답변에 인용한다. 임베딩은 EmbeddingProvider(1536) — KB·LTM 동일 모델·차원(spec §6.1/§9).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import bindparam, select, text

from core.db import AsyncSessionLocal
from core.models import ManagementKbChunk, ManagementKbDocument

if TYPE_CHECKING:
    from domain.management.assistant.embeddings import EmbeddingProvider

_RRF_K = 60  # Reciprocal Rank Fusion 상수 (랭킹 합산 — 점수 스케일 정규화 불필요)

# source_type 스코프 — 매니지먼트 어시스턴트 검색 풀(정책·플레이북·KPI·벤치마크·근거).
# 시뮬레이션 도메인 지식(persona_methodology·simulation_trust·platform_guide)은 제외해
# 운영 질문에 엉뚱한 방법론 문서가 섞이는 걸 막는다. kb_ingest._SOURCE_META와 일치시킨다.
MANAGEMENT_SOURCE_TYPES = frozenset(
    {
        "meta_official",
        "playbook",
        "internal_policy",
        "meta_reference",
        "kobaco_baseline",
        "evidence",
    }
)

# ADVISE(일반 광고지식) 게이트 검색 풀 — 일반지식 + 큐레이션 레퍼런스(Meta 공식·벤치마크).
# 운영 특화(playbook·internal_policy)는 제외: 사용자 캠페인 맥락이 아닌 일반 질문이므로.
GENERAL_SOURCE_TYPE = "general_knowledge"
ADVISE_SOURCE_TYPES = frozenset(
    {GENERAL_SOURCE_TYPE, "meta_official", "kobaco_baseline", "meta_reference"}
)

# 키워드 검색(GIN). websearch_to_tsquery는 빈/특수문자 쿼리에도 안전.
_KW_SQL = text(
    "SELECT id, source, title, chunk,"
    " ts_rank(search_vector, websearch_to_tsquery('simple', :q)) AS rank"
    " FROM management_kb_chunks"
    " WHERE search_vector @@ websearch_to_tsquery('simple', :q)"
    " ORDER BY rank DESC LIMIT :lim"
)

# 네임스페이스(source_type) 필터 버전 — documents 조인. 청크는 document_id로 연결됨.
_KW_SQL_TYPED = text(
    "SELECT c.id, c.source, c.title, c.chunk,"
    " ts_rank(c.search_vector, websearch_to_tsquery('simple', :q)) AS rank"
    " FROM management_kb_chunks c"
    " JOIN management_kb_documents d ON c.document_id = d.id"
    " WHERE c.search_vector @@ websearch_to_tsquery('simple', :q)"
    " AND d.source_type IN :types"
    " ORDER BY rank DESC LIMIT :lim"
).bindparams(bindparam("types", expanding=True))


class KbRetriever:
    """하이브리드(벡터+키워드) 리트리버 — EmbeddingProvider·세션 팩토리 주입(테스트)."""

    def __init__(self, embedder: EmbeddingProvider, session_factory=AsyncSessionLocal) -> None:
        self._embedder = embedder
        self._sf = session_factory

    async def embed(self, text: str) -> list[float]:
        out = await self._embedder.embed([text])
        return out[0]

    async def search(
        self, query: str, k: int = 4, source_types: list[str] | None = None
    ) -> list[dict]:
        """하이브리드 검색. source_types를 주면 해당 네임스페이스로만 한정(기본 None=전체).

        source_types는 management_kb_documents.source_type 값
        (예: platform_guide·persona_methodology·simulation_trust·meta_reference·kobaco_baseline).
        """
        # expanding bindparam은 인덱싱 가능한 시퀀스만 받음(frozenset 불가) → list 변환.
        types = list(source_types) if source_types else None
        emb = await self.embed(query)
        pool = max(k * 3, 8)  # 융합 전 각 채널에서 넉넉히 가져온다
        dist = ManagementKbChunk.embedding.cosine_distance(emb).label("dist")
        vec_stmt = select(
            ManagementKbChunk.id,
            ManagementKbChunk.source,
            ManagementKbChunk.title,
            ManagementKbChunk.chunk,
            dist,
        )
        if types:
            vec_stmt = vec_stmt.join(
                ManagementKbDocument,
                ManagementKbChunk.document_id == ManagementKbDocument.id,
            ).where(ManagementKbDocument.source_type.in_(types))
        vec_stmt = vec_stmt.order_by(dist).limit(pool)

        if types:
            kw_sql, kw_params = _KW_SQL_TYPED, {"q": query, "lim": pool, "types": types}
        else:
            kw_sql, kw_params = _KW_SQL, {"q": query, "lim": pool}

        async with self._sf() as db:
            vec = (await db.execute(vec_stmt)).all()
            kw = (await db.execute(kw_sql, kw_params)).all()
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
        out: list[dict] = []
        for x in top:
            r = x["r"]
            # 코사인 점수(1-거리) — 벡터 채널 청크만 보유. 키워드-only 청크는 None(거리 없음).
            # ADVISE 게이트가 절대 유사도 임계(_ADVISE_THRESHOLD)로 게이팅할 때 쓴다.
            dist = getattr(r, "dist", None)
            out.append(
                {
                    "source": r.source,
                    "title": r.title,
                    "chunk": r.chunk,
                    "score": round(x["s"], 4),  # RRF 융합 점수(상대 랭킹용)
                    "cosine_score": (1.0 - dist) if dist is not None else None,
                }
            )
        return out
