# PgMemoryStore — chat_long_term_memory 적재·임베딩 top-k 회상(MemoryStore 포트).
"""write: 텍스트(content) 임베딩 후 적재. recall: 임베딩 코사인 top-k + 고salience always-load."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from core.db import AsyncSessionLocal
from domain.chat.contracts.schemas import MemoryHit, MemoryItem
from domain.chat.models import ChatLongTermMemory

if TYPE_CHECKING:
    from domain.chat.contracts.ports import EmbeddingProvider

# always-load 상한 — 고salience 행이 누적돼도 매 턴 회상 비용을 bounded로 유지.
_ALWAYS_LOAD_CAP = 20


class PgMemoryStore:
    def __init__(self, embedder: EmbeddingProvider, session_factory=AsyncSessionLocal) -> None:
        self._embedder = embedder
        self._sf = session_factory

    @staticmethod
    def _text(content: dict) -> str:
        text = content.get("text")  # 빈 문자열도 명시 텍스트로 존중(폴백은 키 부재 시만).
        return text if text is not None else " ".join(str(v) for v in content.values())

    async def write(self, item: MemoryItem) -> uuid.UUID:
        vec = (await self._embedder.embed([self._text(item.content)]))[0]
        row = ChatLongTermMemory(
            project_id=item.project_id,
            user_id=item.user_id,
            memory_type=item.memory_type,
            content=item.content,
            embedding=vec,
            salience=item.salience,
            source_session_id=item.source_session_id,
        )
        async with self._sf() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
        return row.id

    async def recall(
        self, *, query: str, project_id, user_id, k: int = 5, salience_floor: float = 0.9
    ) -> list[MemoryHit]:
        qvec = (await self._embedder.embed([query]))[0]
        dist = ChatLongTermMemory.embedding.cosine_distance(qvec).label("dist")

        def _scope(stmt: Any) -> Any:
            if project_id is not None:
                stmt = stmt.where(ChatLongTermMemory.project_id == project_id)
            if user_id is not None:
                stmt = stmt.where(ChatLongTermMemory.user_id == user_id)
            return stmt

        topk_stmt = _scope(
            select(ChatLongTermMemory, dist)
            .where(ChatLongTermMemory.embedding.is_not(None))
            .order_by(dist)
            .limit(k)
        )
        always_stmt = _scope(
            select(ChatLongTermMemory)
            .where(ChatLongTermMemory.salience >= salience_floor)
            .order_by(ChatLongTermMemory.salience.desc(), ChatLongTermMemory.created_at.desc())
            .limit(_ALWAYS_LOAD_CAP)
        )

        async with self._sf() as db:
            top_rows = (await db.execute(topk_stmt)).all()
            always_rows = (await db.execute(always_stmt)).scalars().all()
        # TODO: 회상된 hit의 last_used_at = now() 갱신(eviction·recency 로직 활성화 시).

        hits: dict[uuid.UUID, MemoryHit] = {}
        for m in always_rows:
            hits[m.id] = MemoryHit(
                id=m.id,
                memory_type=m.memory_type,
                content=m.content,
                salience=m.salience,
                score=1.0,
            )
        for r in top_rows:
            m = r.ChatLongTermMemory
            if m.id not in hits:
                hits[m.id] = MemoryHit(
                    id=m.id,
                    memory_type=m.memory_type,
                    content=m.content,
                    salience=m.salience,
                    score=max(0.0, round(1.0 - float(r.dist), 3)),  # 반대 벡터 음수 클램프 → [0,1]
                )
        return sorted(hits.values(), key=lambda h: h.score, reverse=True)
