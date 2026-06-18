"""add ad_analyses.detected_objective column

Revision ID: 006
Revises: 005
Create Date: 2026-06-15

의도 교차검증(ANALYSIS §3.5-3) — objective 차원 비교를 위해 감지 캠페인 목표 컬럼 추가.
시뮬레이터 소유 테이블(ad_analyses)에 additive(IF NOT EXISTS, 비파괴)로만 변경.

참고: ERD의 광고(ads) 테이블 service_class·description은 core 소유 + 라이브 스키마 미반영이라
이 마이그레이션 범위 밖. 선언 입력은 요청(SimulationRunRequest)으로 전달되어 ads 의존 없음.
"""

from alembic import op

revision = "006_ad_analysis"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ad_analyses ADD COLUMN IF NOT EXISTS detected_objective VARCHAR(50)")


def downgrade() -> None:
    op.execute("ALTER TABLE ad_analyses DROP COLUMN IF EXISTS detected_objective")
