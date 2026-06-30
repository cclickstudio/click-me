import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from alembic import context

load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

db_url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
if db_url and db_url.startswith("postgresql+asyncpg"):
    db_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)
config.set_main_option("sqlalchemy.url", db_url or "")

# autogenerate(=alembic check) 비교 기준. baseline은 create_all 기반이라 ORM 메타데이터가
# 곧 진실 — CoreBase·SimBase 두 MetaData를 함께 넘겨 ORM과 마이그레이션 정합을 검증한다.
from core.models import Base as _CoreBase  # noqa: E402
from domain.simulation.models import SimBase as _SimBase  # noqa: E402

target_metadata = [_CoreBase.metadata, _SimBase.metadata]


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
