"""initial schema v2.0

Revision ID: 001
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE user_role AS ENUM ('admin', 'user');
            CREATE TYPE project_status AS ENUM ('active', 'archived');
            CREATE TYPE ad_input_type AS ENUM ('image', 'text', 'video', 'url');
            CREATE TYPE ad_status AS ENUM ('pending', 'analyzing', 'completed', 'failed');
            CREATE TYPE simulation_type AS ENUM ('ad_reaction');
            CREATE TYPE simulation_status AS ENUM ('pending', 'running', 'completed', 'failed');
            CREATE TYPE chat_role AS ENUM ('user', 'assistant');
            CREATE TYPE plan_type AS ENUM ('free', 'professional', 'enterprise');
            CREATE TYPE campaign_objective AS ENUM ('awareness', 'conversion');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS organizations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(200) NOT NULL,
            plan_type plan_type NOT NULL DEFAULT 'free',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255),
            name VARCHAR(100) NOT NULL,
            role user_role NOT NULL DEFAULT 'user',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            last_login_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            created_by UUID NOT NULL REFERENCES users(id),
            name VARCHAR(200) NOT NULL,
            description TEXT,
            status project_status NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS ads (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            created_by UUID NOT NULL REFERENCES users(id),
            name VARCHAR(200) NOT NULL,
            input_type ad_input_type NOT NULL,
            storage_path TEXT,
            storage_url TEXT,
            text_content JSONB,
            source_url TEXT,
            analysis_status ad_status NOT NULL DEFAULT 'pending',
            analysis_result JSONB,
            analysis_confidence FLOAT CHECK (analysis_confidence >= 0.0 AND analysis_confidence <= 1.0),
            analysis_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS simulations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            ad_id UUID NOT NULL REFERENCES ads(id) ON DELETE CASCADE,
            created_by UUID NOT NULL REFERENCES users(id),
            simulation_type simulation_type NOT NULL DEFAULT 'ad_reaction',
            objective campaign_objective NOT NULL DEFAULT 'conversion',
            status simulation_status NOT NULL DEFAULT 'pending',
            persona_count INTEGER NOT NULL DEFAULT 20,
            persona_config JSONB,
            results_summary JSONB,
            llm_cost_usd FLOAT DEFAULT 0.0,
            sqs_message_id VARCHAR(100),
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS persona_responses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            simulation_id UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
            persona_id VARCHAR(50) NOT NULL,
            producer_id VARCHAR(100),
            segment VARCHAR(100),
            ocean JSONB,
            persona_attributes JSONB,
            free_text_reaction TEXT,
            exposure_output JSONB,
            deliberation_output JSONB,
            signals JSONB NOT NULL,
            confidence FLOAT CHECK (confidence >= 0.0 AND confidence <= 1.0),
            is_outlier BOOLEAN NOT NULL DEFAULT FALSE,
            anchor_version VARCHAR(20) DEFAULT 'v1.0',
            embedding_model VARCHAR(50) DEFAULT 'text-embedding-3-small',
            response_time_ms INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            simulation_id UUID NOT NULL UNIQUE REFERENCES simulations(id) ON DELETE CASCADE,
            report_data JSONB NOT NULL,
            pdf_url TEXT,
            disclaimer TEXT NOT NULL DEFAULT '본 결과는 AI 시뮬레이션 기반 예측입니다. 실제 광고 성과와 ±20~30% 오차가 있을 수 있습니다.',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS inquiries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            title VARCHAR(300) NOT NULL,
            content TEXT NOT NULL,
            contact_email VARCHAR(255),
            is_resolved BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
            title VARCHAR(200) NOT NULL DEFAULT '새 채팅',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
            role chat_role NOT NULL,
            content TEXT NOT NULL,
            metadata JSONB,
            tokens_used INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            theme VARCHAR(10) NOT NULL DEFAULT 'light',
            notifications JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            action VARCHAR(100) NOT NULL,
            resource VARCHAR(50),
            resource_id UUID,
            metadata JSONB,
            ip_address VARCHAR(45),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    for table in ["audit_logs", "user_settings", "chat_messages", "chat_sessions",
                  "inquiries", "reports", "persona_responses", "simulations",
                  "ads", "projects", "users", "organizations"]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
