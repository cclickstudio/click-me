# Meta 연결 리포지토리 — 암호화 저장/복호화 로드 왕복·평문 미저장·org당 1건 (SQLite 인메모리)
import uuid
from types import SimpleNamespace

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from core.models import MetaConnection
from domain.management.adapters.meta.connection_repository import MetaConnectionRepository
from domain.management.adapters.meta.token_crypto import TokenCipher, generate_key


async def _session() -> AsyncSession:
    # core Base 전체는 pgvector 컬럼이 있어 SQLite 생성 불가 → 이 테이블만 생성
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(MetaConnection.__table__.create)
    return AsyncSession(engine)


def _cipher() -> TokenCipher:
    return TokenCipher.from_base64_key(generate_key())


async def test_upsert_then_load_roundtrip():
    async with await _session() as session:
        repo = MetaConnectionRepository(session, _cipher())
        org = uuid.uuid4()
        await repo.upsert(org, access_token="long-tok", ad_account_id="act_9", scopes=["ads_read"])
        assert await repo.load_token(org) == "long-tok"


async def test_token_stored_encrypted_not_plaintext():
    async with await _session() as session:
        cipher = _cipher()
        repo = MetaConnectionRepository(session, cipher)
        org = uuid.uuid4()
        await repo.upsert(org, access_token="secret-token-xyz")
        row = await session.scalar(
            select(MetaConnection).where(MetaConnection.organization_id == org)
        )
        assert "secret-token-xyz" not in row.access_token_enc
        assert cipher.decrypt(row.access_token_enc) == "secret-token-xyz"


async def test_upsert_updates_existing_no_duplicate():
    async with await _session() as session:
        repo = MetaConnectionRepository(session, _cipher())
        org = uuid.uuid4()
        await repo.upsert(org, access_token="tok-1")
        await repo.upsert(org, access_token="tok-2", ad_account_id="act_x")
        assert await repo.load_token(org) == "tok-2"
        count = await session.scalar(select(func.count()).select_from(MetaConnection))
        assert count == 1


async def test_load_missing_returns_none():
    async with await _session() as session:
        repo = MetaConnectionRepository(session, _cipher())
        assert await repo.load_token(uuid.uuid4()) is None


async def test_load_credentials_drops_into_meta_client():
    async with await _session() as session:
        repo = MetaConnectionRepository(session, _cipher())
        org = uuid.uuid4()
        await repo.upsert(org, access_token="org-tok", ad_account_id="act_777")
        settings = SimpleNamespace(
            meta_graph_api_version="v23.0", meta_app_id="app1", meta_app_secret="sec1"
        )
        creds = await repo.load_credentials(org, settings)
        assert creds.meta_access_token == "org-tok"
        assert creds.meta_ad_account_id == "act_777"
        assert creds.meta_app_id == "app1"
