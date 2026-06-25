# 세션 넘는 장기기억 — (tenant, user) 네임스페이스 cross-session 메모리 (langgraph Store)
"""thread당 체크포인터(단기) 위에 세션을 넘는 장기기억을 둔다.

기본은 InMemoryStore(프로세스 수명 — 단일 EC2에서 세션 간 유지). 영속은 AsyncPostgresStore로
교체한다(체크포인터와 같은 seam). 식별자(tenant_id·user_id)는 호출자가 준다 — 채팅 인증(auth)이
도입되면 거기서 흐른다. 인증 전엔 데모 네임스페이스로 동작한다.
"""

from __future__ import annotations


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
    """장기기억 빌더 — 기본 InMemory. 영속(AsyncPostgresStore) 분기는 후속(seam)."""
    return ManagementMemory()
