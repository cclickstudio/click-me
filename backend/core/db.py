from collections.abc import AsyncGenerator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import settings


def _normalize_database_url(url: str) -> str:
    """Neon 원본 URL(postgresql://...?sslmode=...)을 asyncpg 호환 형태로 정규화.

    asyncpg는 sslmode/channel_binding 쿼리 파라미터를 지원하지 않는다 (ssl로 대체).
    """
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if "+asyncpg" not in url:
        return url
    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query):
        if key == "sslmode":
            query.append(("ssl", value))
        elif key == "channel_binding":
            continue
        else:
            query.append((key, value))
    return urlunsplit(parts._replace(query=urlencode(query)))


# statement_cache_size=0: DATABASE_URL이 Neon pooler(PgBouncer)를 가리킬 때
# asyncpg prepared-statement가 transaction 모드 커넥션 재사용에서 충돌("prepared
# statement already exists/does not exist")하는 것을 회피. 챗 게이트 테스트 엔진
# (tests/chat/conftest.py)·체크포인터(prepare_threshold=None)와 동일한 대응으로 운영
# 엔진을 정합. direct 엔드포인트면 무해(캐시만 비활성).
engine = create_async_engine(
    _normalize_database_url(settings.database_url),
    pool_pre_ping=True,
    pool_size=10,
    connect_args={"statement_cache_size": 0},
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
