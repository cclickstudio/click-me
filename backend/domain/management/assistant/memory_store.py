# 세션 넘는 장기기억 — (tenant, user) 네임스페이스 cross-session 메모리
"""thread당 체크포인터(단기) 위에 세션을 넘는 장기기억을 둔다.

- 테스트/데모(use_mock): langgraph InMemoryStore(프로세스 수명, hermetic).
- 실행(use_mock=false): SqlMemoryStore — SQLAlchemy(asyncpg)로 Neon에 영속(재시작 후에도 유지,
  Windows에서도 동작). 둘 다 같은 인터페이스(aput/asearch)라 ManagementMemory는 그대로 쓴다.
식별자(tenant_id·user_id)는 호출자가 준다 — 비로그인은 데모 네임스페이스(global/anon).
"""

from __future__ import annotations


class _MemHit:
    """asearch 결과 항목 — langgraph Store의 Item처럼 .value를 노출."""

    __slots__ = ("value",)

    def __init__(self, value: dict) -> None:
        self.value = value


class SqlMemoryStore:
    """SQLAlchemy(asyncpg) 백엔드 — Neon 영속. langgraph Store 인터페이스(aput/asearch) 호환."""

    async def aput(self, namespace: tuple, key: str, value: dict) -> None:
        from core.db import AsyncSessionLocal  # noqa: PLC0415
        from core.models import ManagementUserMemory  # noqa: PLC0415

        _, tenant, user = namespace
        async with AsyncSessionLocal() as db:
            db.add(ManagementUserMemory(tenant_id=tenant, user_id=user, mem_key=key, content=value))
            await db.commit()

    async def asearch(self, namespace: tuple, *, limit: int = 10, **_: object) -> list[_MemHit]:
        from sqlalchemy import select  # noqa: PLC0415

        from core.db import AsyncSessionLocal  # noqa: PLC0415
        from core.models import ManagementUserMemory  # noqa: PLC0415

        _, tenant, user = namespace
        async with AsyncSessionLocal() as db:
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
    """(tenant, user) 네임스페이스 cross-session 메모리. remember 적재 · recall 회수."""

    def __init__(self, store=None) -> None:
        if store is None:
            from langgraph.store.memory import InMemoryStore  # noqa: PLC0415

            store = InMemoryStore()
        self._store = store

    @staticmethod
    def _ns(tenant_id: str | None, user_id: str | None) -> tuple[str, str, str]:
        return ("mgmt_memory", tenant_id or "global", user_id or "anon")

    async def remember(
        self, tenant_id: str | None, user_id: str | None, key: str, value: dict
    ) -> None:
        """장기기억 1건 적재(선호·반복 관심·과거 결정 요약 등)."""
        await self._store.aput(self._ns(tenant_id, user_id), key, value)

    async def recall(
        self, tenant_id: str | None, user_id: str | None, limit: int = 5
    ) -> list[dict]:
        """이 (tenant, user)의 최근 장기기억 회수 — 신규 세션 컨텍스트 주입용."""
        items = await self._store.asearch(self._ns(tenant_id, user_id), limit=limit)
        return [dict(it.value) for it in items]


def build_memory_store(settings) -> ManagementMemory:
    """장기기억 빌더 — 테스트/데모(use_mock)는 InMemory, 실행은 SqlMemoryStore(Neon 영속)."""
    if getattr(settings, "use_mock", True):
        return ManagementMemory()  # InMemoryStore — hermetic
    return ManagementMemory(store=SqlMemoryStore())  # asyncpg 영속(Neon)
