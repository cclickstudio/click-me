# 챗 도메인 포트 — 외부 의존 없는 Protocol 계약(adapters가 구현, wiring이 주입).
"""EmbeddingProvider(KB·LTM 공유 임베딩) · ChatRepo(세션·메시지 영속) · MemoryStore(LTM)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from domain.chat.contracts.agent_io import SubAgentRequest, SubAgentResult
    from domain.chat.contracts.schemas import MemoryHit, MemoryItem, MessageDTO, SessionDTO


class EmbeddingProvider(Protocol):
    """텍스트 → 임베딩 벡터. KB·LTM이 동일 구현(동일 모델·차원)을 공유한다."""

    @property
    def dim(self) -> int: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class ChatRepo(Protocol):
    """세션·메시지 영속(정규화 행)."""

    async def create_session(
        self,
        *,
        session_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        organization_id: uuid.UUID | None,
        title: str,
    ) -> SessionDTO: ...

    async def get_session(self, session_id: uuid.UUID) -> SessionDTO | None: ...

    async def list_sessions(self, *, user_id: uuid.UUID | None, limit: int) -> list[SessionDTO]: ...

    async def append_message(
        self,
        *,
        session_id: uuid.UUID,
        role: str,
        content: str,
        route: str | None,
        meta: dict | None,
    ) -> MessageDTO: ...

    async def get_messages(self, session_id: uuid.UUID, *, limit: int) -> list[MessageDTO]: ...

    async def update_summary(self, session_id: uuid.UUID, summary: str) -> None: ...


class MemoryStore(Protocol):
    """롱텀 메모리 — 적재(임베딩 포함)·임베딩 top-k 회상·고salience always-load."""

    async def write(self, item: MemoryItem) -> uuid.UUID: ...

    async def recall(
        self,
        *,
        query: str,
        project_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        k: int,
        salience_floor: float,
    ) -> list[MemoryHit]: ...


class SubAgent(Protocol):
    """도메인 서브에이전트 — 슈퍼바이저가 위임하는 단일 진입점."""

    route: str

    async def run(self, req: SubAgentRequest) -> SubAgentResult: ...
