# PgMemoryStore 적재·임베딩 top-k 회상 — 개인 Postgres 게이트.
import pytest
from sqlalchemy import delete

from domain.chat.adapters.embeddings import MockEmbeddingProvider
from domain.chat.adapters.pg_memory_store import PgMemoryStore
from domain.chat.contracts.schemas import MemoryItem
from domain.chat.models import ChatLongTermMemory
from tests.chat.conftest import pg_only


@pg_only
@pytest.mark.asyncio
async def test_write_then_recall_nearest(pg_session_factory):
    store = PgMemoryStore(
        embedder=MockEmbeddingProvider(dim=1024), session_factory=pg_session_factory
    )
    ids = []
    try:
        ids.append(
            await store.write(
                MemoryItem(
                    memory_type="fact",
                    content={"text": "브랜드 톤은 친근하고 활기차다"},
                    salience=0.6,
                )
            )
        )
        ids.append(
            await store.write(
                MemoryItem(
                    memory_type="fact",
                    content={"text": "예산은 분기당 천만원"},
                    salience=0.4,
                )
            )
        )
        hits = await store.recall(
            query="브랜드 톤은 친근하고 활기차다",
            project_id=None,
            user_id=None,
            k=2,
            salience_floor=2.0,  # always-load 제외(2.0 초과 없음)
        )
        # exact-match(거리 0, score 1.0)가 1위, 다른 메모리가 2위 — top-k 정렬 검증.
        assert len(hits) >= 2
        assert hits[0].content["text"].startswith("브랜드 톤")
        assert hits[0].score == 1.0
        assert hits[0].score >= hits[1].score
    finally:
        async with pg_session_factory() as db:
            for i in ids:
                await db.execute(delete(ChatLongTermMemory).where(ChatLongTermMemory.id == i))
            await db.commit()


@pg_only
@pytest.mark.asyncio
async def test_high_salience_always_loaded(pg_session_factory):
    store = PgMemoryStore(
        embedder=MockEmbeddingProvider(dim=1024), session_factory=pg_session_factory
    )
    mid = await store.write(
        MemoryItem(
            memory_type="preference",
            content={"text": "항상 한국어로 답하라"},
            salience=0.95,
        )
    )
    try:
        hits = await store.recall(
            query="전혀 무관한 질문",
            project_id=None,
            user_id=None,
            k=1,
            salience_floor=0.9,
        )
        assert any(h.id == mid and h.score == 1.0 for h in hits)
    finally:
        async with pg_session_factory() as db:
            await db.execute(delete(ChatLongTermMemory).where(ChatLongTermMemory.id == mid))
            await db.commit()
