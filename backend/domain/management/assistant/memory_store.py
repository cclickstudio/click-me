# 세션 넘는 장기기억 — (tenant, user) 네임스페이스 cross-session 메모리
"""thread당 체크포인터(단기) 위에 세션을 넘는 장기기억을 둔다.

- 테스트/데모(use_mock): langgraph InMemoryStore(프로세스 수명, hermetic).
- 실행(use_mock=false): SqlMemoryStore — SQLAlchemy(asyncpg)로 Neon에 영속(재시작 후에도 유지,
  Windows에서도 동작). 둘 다 같은 인터페이스(aput/asearch)라 ManagementMemory는 그대로 쓴다.
식별자(tenant_id·user_id)는 호출자가 준다 — 비로그인은 데모 네임스페이스(global/anon).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable


class _MemHit:
    """asearch 결과 항목 — langgraph Store의 Item처럼 .value를 노출."""

    __slots__ = ("value",)

    def __init__(self, value: dict) -> None:
        self.value = value


class SqlMemoryStore:
    """SQLAlchemy(asyncpg) 백엔드 — Neon 영속. langgraph Store 인터페이스(aput/asearch) 호환."""

    async def aput(
        self, namespace: tuple, key: str, value: dict, embedding: list[float] | None = None
    ) -> None:
        from sqlalchemy import select  # noqa: PLC0415

        from core.db import AsyncSessionLocal  # noqa: PLC0415
        from core.models import ManagementUserMemory  # noqa: PLC0415

        _, tenant, user = namespace
        async with AsyncSessionLocal() as db:
            # upsert — 같은 (tenant,user,key)면 갱신(M2 dedup_key 동작). uuid 키는 항상 신규.
            existing = (
                (
                    await db.execute(
                        select(ManagementUserMemory).where(
                            ManagementUserMemory.tenant_id == tenant,
                            ManagementUserMemory.user_id == user,
                            ManagementUserMemory.mem_key == key,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if existing is not None:
                existing.content = value
                if embedding is not None:
                    existing.embedding = embedding
            else:
                db.add(
                    ManagementUserMemory(
                        tenant_id=tenant,
                        user_id=user,
                        mem_key=key,
                        content=value,
                        embedding=embedding,
                    )
                )
            await db.commit()

    async def asearch(
        self,
        namespace: tuple,
        *,
        limit: int = 10,
        query_embedding: list[float] | None = None,
        **_: object,
    ) -> list[_MemHit]:
        """query_embedding 있으면 시맨틱 top-k(M6), 없거나 임베딩 행 없으면 recency 폴백."""
        from sqlalchemy import select  # noqa: PLC0415

        from core.db import AsyncSessionLocal  # noqa: PLC0415
        from core.models import ManagementUserMemory  # noqa: PLC0415

        _, tenant, user = namespace
        async with AsyncSessionLocal() as db:
            if query_embedding is not None:
                dist = ManagementUserMemory.embedding.cosine_distance(query_embedding)
                rows = (
                    (
                        await db.execute(
                            select(ManagementUserMemory.content)
                            .where(
                                ManagementUserMemory.tenant_id == tenant,
                                ManagementUserMemory.user_id == user,
                                ManagementUserMemory.embedding.isnot(None),
                            )
                            .order_by(dist)
                            .limit(limit)
                        )
                    )
                    .scalars()
                    .all()
                )
                if rows:  # 임베딩 행이 있으면 시맨틱 결과
                    return [_MemHit(r) for r in rows]
            # 폴백 — recency(임베딩 없는 기존 행·query 없음)
            rows = (
                (
                    await db.execute(
                        select(ManagementUserMemory.content)
                        .where(
                            ManagementUserMemory.tenant_id == tenant,
                            ManagementUserMemory.user_id == user,
                        )
                        .order_by(ManagementUserMemory.created_at.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        return [_MemHit(r) for r in rows]


class ManagementMemory:
    """(tenant, user) 네임스페이스 cross-session 메모리. remember 적재 · recall 회수.

    embedder(있으면, SqlMemoryStore 한정)로 fact를 임베딩해 저장하고, recall은 query를 임베딩해
    시맨틱 top-k 회수(M6, 도연 패턴). embedder 없으면(mock·InMemoryStore) recency 회수.
    """

    def __init__(self, store=None, embedder=None) -> None:
        if store is None:
            from langgraph.store.memory import InMemoryStore  # noqa: PLC0415

            store = InMemoryStore()
        self._store = store
        self._embedder = embedder
        self._semantic = embedder is not None and isinstance(store, SqlMemoryStore)

    @staticmethod
    def _ns(tenant_id: str | None, user_id: str | None) -> tuple[str, str, str]:
        return ("mgmt_memory", tenant_id or "global", user_id or "anon")

    async def remember(
        self, tenant_id: str | None, user_id: str | None, key: str, value: dict
    ) -> None:
        """장기기억 1건 적재(선호·반복 관심·과거 결정 요약 등). 시맨틱이면 fact 임베딩 함께 저장."""
        ns = self._ns(tenant_id, user_id)
        if self._semantic:
            emb = await self._embedder(value.get("fact") or value.get("note") or "")
            await self._store.aput(ns, key, value, embedding=emb)
        else:
            await self._store.aput(ns, key, value)

    async def recall(
        self,
        tenant_id: str | None,
        user_id: str | None,
        query: str | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """장기기억 회수 — query 있고 시맨틱이면 의미적 top-k, 아니면 recency."""
        ns = self._ns(tenant_id, user_id)
        if self._semantic and query:
            qemb = await self._embedder(query)
            items = await self._store.asearch(ns, limit=limit, query_embedding=qemb)
        else:
            items = await self._store.asearch(ns, limit=limit)
        return [dict(it.value) for it in items]


def _build_embedder(settings) -> Callable[[str], Awaitable[list[float] | None]] | None:
    """OpenAI text-embedding-3-small 임베더(text→vec) 클로저. 키 없으면 None(recency 폴백)."""
    api_key = getattr(settings, "openai_api_key", None)
    if not api_key:
        return None
    from openai import AsyncOpenAI  # noqa: PLC0415

    client = AsyncOpenAI(api_key=api_key)

    async def embed(text: str) -> list[float] | None:
        if not text:
            return None
        try:
            r = await client.embeddings.create(model="text-embedding-3-small", input=[text])
            return r.data[0].embedding
        except Exception:  # noqa: BLE001 — 임베딩 실패는 None(recency 폴백)
            return None

    return embed


def build_memory_store(settings) -> ManagementMemory:
    """장기기억 빌더 — mock은 InMemory(recency), 실행은 SqlMemoryStore(Neon)+시맨틱 임베더."""
    if getattr(settings, "use_mock", True):
        return ManagementMemory()  # InMemoryStore — hermetic, recency
    return ManagementMemory(store=SqlMemoryStore(), embedder=_build_embedder(settings))
