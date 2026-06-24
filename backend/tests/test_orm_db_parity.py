# ORM 선언 컬럼이 실 DB에 모두 존재하는지 검증(드리프트 회귀 방지). PARITY_DB_URL 있을 때만 실행.
import os

import psycopg2
import pytest

import core.models  # noqa: F401  매핑 등록
import domain.chat.models  # noqa: F401  챗 ORM 등록(chat_sessions·messages·ltm·brand)
from core.db import Base
from domain.simulation.models import SimBase  # 시뮬은 별도 metadata(SimBase)

pytestmark = pytest.mark.skipif(not os.environ.get("PARITY_DB_URL"), reason="PARITY_DB_URL 미설정")


def _db_columns(url: str, table: str) -> set[str]:
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute(
        "select column_name from information_schema.columns "
        "where table_schema='public' and table_name=%s",
        (table,),
    )
    cols = {r[0] for r in cur.fetchall()}
    cur.close()
    conn.close()
    return cols


def test_orm_columns_exist_in_db():
    url = os.environ["PARITY_DB_URL"]
    mismatches = []
    all_tables = {**Base.metadata.tables, **SimBase.metadata.tables}
    for table, tbl in all_tables.items():
        db_cols = _db_columns(url, table)
        if not db_cols:
            continue  # 실 DB에 없는 테이블은 스킵
        for col in tbl.columns:
            if col.name not in db_cols:
                mismatches.append(f"{table}.{col.name} (ORM엔 있으나 DB에 없음)")
    assert not mismatches, "ORM↔DB 드리프트:\n" + "\n".join(mismatches)
