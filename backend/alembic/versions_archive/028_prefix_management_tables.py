"""prefix management-only tables — management_ 접두사 일괄 적용

Revision ID: 028
Revises: 027
Create Date: 2026-06-26

management 도메인 전용인데 접두사가 없던 6종에 management_ 접두사를 붙인다(소유 명확화).
모든 접근이 ORM 클래스 경유(__tablename__)라 코드 변경은 models.py·테스트 1곳뿐. 데이터는
ALTER TABLE RENAME으로 보존된다(인덱스·제약명은 기존 유지 — 기능 무관).

대상: audit_events·idempotency_keys·regeneration_jobs·meta_connections·
      campaign_kpi_overrides·created_campaigns

⚠️ 🤝 DB 스키마 변경 — down_revision(head=027) 합의 필요(CLAUDE.md 협업 규칙).
"""

from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None

_RENAMES = [
    ("audit_events", "management_audit_events"),
    ("idempotency_keys", "management_idempotency_keys"),
    ("regeneration_jobs", "management_regeneration_jobs"),
    ("meta_connections", "management_meta_connections"),
    ("campaign_kpi_overrides", "management_campaign_kpi_overrides"),
    ("created_campaigns", "management_created_campaigns"),
]


def upgrade() -> None:
    for old, new in _RENAMES:
        op.execute(f"ALTER TABLE IF EXISTS {old} RENAME TO {new}")


def downgrade() -> None:
    for old, new in _RENAMES:
        op.execute(f"ALTER TABLE IF EXISTS {new} RENAME TO {old}")
