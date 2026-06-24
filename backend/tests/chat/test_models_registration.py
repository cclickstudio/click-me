# 챗 ORM이 core Base에 등록되고 목표 컬럼을 선언하는지 hermetic 검증.
from core.db import Base
from domain.chat import models as chat_models  # noqa: F401  매핑 등록


def _cols(table_name: str) -> set[str]:
    return set(Base.metadata.tables[table_name].columns.keys())


def test_chat_tables_registered():
    for t in ("chat_sessions", "chat_messages", "chat_long_term_memory", "chat_brand_profiles"):
        assert t in Base.metadata.tables, f"{t} 미등록"


def test_chat_sessions_columns():
    cols = _cols("chat_sessions")
    assert {
        "id",
        "project_id",
        "user_id",
        "organization_id",
        "title",
        "summary",
        "created_at",
        "updated_at",
    } <= cols
    assert "messages" not in cols  # jsonb 이중화 제거


def test_chat_messages_columns():
    cols = _cols("chat_messages")
    # 컬럼명은 metadata(파이썬 속성은 meta) — 매핑 회귀 가드.
    assert {"id", "session_id", "role", "content", "route", "metadata", "created_at"} <= cols
    assert "meta" not in cols


def test_chat_brand_profile_columns():
    cols = _cols("chat_brand_profiles")
    assert {
        "id",
        "project_id",
        "brand_name",
        "tone",
        "target_audience",
        "product_category",
        "keywords",
        "updated_at",
    } <= cols


def test_chat_ltm_columns():
    cols = _cols("chat_long_term_memory")
    assert {
        "id",
        "project_id",
        "user_id",
        "memory_type",
        "content",
        "embedding",
        "salience",
        "last_used_at",
        "source_session_id",
        "created_at",
    } <= cols
