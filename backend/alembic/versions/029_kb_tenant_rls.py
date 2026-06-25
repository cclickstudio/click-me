"""KB 테넌트 행수준 보안(RLS) — kb_documents·kb_chunks 고객별 격리

Revision ID: 029
Revises: 028
Create Date: 2026-06-23
재번호(2026-06-25): dev 병합 시 rev 020 충돌 → 028(management_knowledge) 뒤로 이동.

벡터/키워드 검색에서 다른 테넌트 문서가 섞이지 않게 RLS를 건다. 현재 데이터는 전부
global(tenant_id NULL)이라 "NULL은 항상 보임" 정책으로 기존 동작은 유지된다(검증: chunks 17 그대로).
관측용 chat/agent 테이블은 tenant_id가 없어 제외(후속).

[중요 — 현재는 정책만 준비, 실제 격리는 비활성] 접속 역할 neondb_owner가 BYPASSRLS=true라
이 역할로는 RLS가 우회된다(GUC는 정상 동작 확인). 격리를 실제 켜려면:
  1) BYPASSRLS 없는 앱 전용 롤 생성 + 테이블 GRANT,
  2) DATABASE_URL을 그 롤로 교체,
  3) 요청마다 커넥션에서 `SET app.current_tenant = '<tenant>'`.
멀티테넌트 도입 시점에 위 3단계만 하면 코드 변경 없이 격리가 켜진다. 그 전까지 무해(무영향).
"""

from alembic import op

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None

_TABLES = ("management_kb_documents", "management_kb_chunks")
_POLICY = "tenant_isolation"


def upgrade() -> None:
    for t in _TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON {t}")
        # global(NULL) 행은 항상 보이고, 테넌트 행은 세션 GUC(app.current_tenant)와 일치할 때만.
        # GUC 미설정 시 current_setting(...,true)=NULL → NULL 행만 보임(현재 전부 NULL → 무영향).
        op.execute(
            f"CREATE POLICY {_POLICY} ON {t} "
            "USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant', true)) "
            "WITH CHECK (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant', true))"
        )


def downgrade() -> None:
    for t in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON {t}")
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
