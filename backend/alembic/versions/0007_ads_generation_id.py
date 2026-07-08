# ads에 generation_id 컬럼 추가 — '생성한 광고로 시뮬' 진입 시 생성 출처를 기록
"""채팅 개선모드가 simulation → ads.generation_id → 상품 누끼(product_cutout) 키를 역추적해
재사용하기 위한 느슨한 참조(cross-base라 FK 없음). 기존 행은 NULL(개선 시 누끼 없이 폴백).
"""

from alembic import op

revision = "0007_ads_generation_id"
down_revision = "0006_management_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ads ADD COLUMN IF NOT EXISTS generation_id UUID")


def downgrade() -> None:
    op.execute("ALTER TABLE ads DROP COLUMN IF EXISTS generation_id")
