"""add generator tables

Revision ID: 003
Revises: 002
Create Date: 2026-06-12
"""

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 광고 생성 요청 단위 (생성모드 파이프라인 1회 실행)
    op.execute("""
        CREATE TABLE IF NOT EXISTS ad_generations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending | running | completed | failed
            input JSONB NOT NULL,
            product_analysis JSONB,
            strategies JSONB,
            selected_candidate_id UUID,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # 생성된 광고 후보 (생성 1회당 3종)
    op.execute("""
        CREATE TABLE IF NOT EXISTS ad_generation_candidates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            generation_id UUID NOT NULL REFERENCES ad_generations(id) ON DELETE CASCADE,
            idx SMALLINT NOT NULL,
            strategy JSONB,
            template_id VARCHAR(10),
            copy JSONB,
            image_prompt TEXT,
            s3_key VARCHAR(512),
            qa_result JSONB,
            qa_passed BOOLEAN,
            explanation JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ad_generation_candidates_generation
            ON ad_generation_candidates (generation_id)
    """)

    # 게시 이력 (광고 업로드 정책: 업로드 이력·실행 결과·로그 저장)
    op.execute("""
        CREATE TABLE IF NOT EXISTS ad_publish_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            generation_id UUID REFERENCES ad_generations(id) ON DELETE SET NULL,
            candidate_id UUID REFERENCES ad_generation_candidates(id) ON DELETE SET NULL,
            platform VARCHAR(20) NOT NULL DEFAULT 'instagram',
            status VARCHAR(20) NOT NULL,  -- published | failed | mocked
            ig_container_id VARCHAR(100),
            ig_media_id VARCHAR(100),
            caption TEXT,
            request_payload JSONB,
            response_payload JSONB,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ad_publish_logs")
    op.execute("DROP TABLE IF EXISTS ad_generation_candidates")
    op.execute("DROP TABLE IF EXISTS ad_generations")
