"""drop unused/legacy tables — Phase ② 정리 (docs/db-cleanup.md)

미사용·레거시·대체된 테이블 19개를 제거한다. 참조 코드(projects.py/admin.py purge·상세쿼리,
ORM SimulationResult/AdEmbedding)는 같은 커밋에서 제거됨. refresh_tokens·brand_kits(저확신)와
챗 관련(management_chat_*/agent_runs→Phase ③ 수렴)은 제외.

Revision ID: 025
Revises: 024
"""

from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None

_TABLES = [
    "generated_ads",
    "ad_templates",
    "generator_kb_chunks",
    "rag_chunks",
    "simulation_kb_chunks",
    "persona_templates",
    "project_members",
    "user_settings",
    "subscription_plans",
    "benchmarks",
    "calibration_data",
    "audit_logs",
    "simulation_comparisons",
    "organization_subscriptions",
    "recommendations",
    "diagnoses",
    "reports",
    "simulation_results",
    "ad_embeddings",
]


def upgrade() -> None:
    for t in _TABLES:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")


def downgrade() -> None:
    # 정리 마이그레이션 — 복원은 백업/이력 필요. no-op.
    pass
