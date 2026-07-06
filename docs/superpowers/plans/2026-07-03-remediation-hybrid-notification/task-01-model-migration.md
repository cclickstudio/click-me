# Task 1: ManagementNotification 모델 + Alembic 0005

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-03-remediation-hybrid-notification.md` · 스펙: `docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md` §1
> **실행 규칙**: 백엔드 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 파일 첫 줄 한국어 헤더 주석 · 🅰 소유 파일 수정 금지.
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.
> ⚠ `core/models.py`는 공통부 — 이 태스크는 단독 커밋으로 분리하고 사전 공지(Task 0 ①) 확인 후 진행.

---

**Files:**
- Modify: `backend/core/models.py` (파일 끝 CreditLedger 클래스 뒤에 추가)
- Create: `backend/alembic/versions/0005_management_notifications.py`
- Modify: `docs/db-schema.md`

- [ ] **Step 1: 모델 추가**

`backend/core/models.py` 맨 끝에 추가 (`JSON`·`Index`·`desc`는 이미 임포트돼 있음 — `text`가 없으면 `from sqlalchemy import text` 추가):

```python
# ──────────────────────────────────────────────
# Management — 운영 알림 (이상 감지 C안, 스펙 2026-07-03)
# ──────────────────────────────────────────────


class ManagementNotification(Base):
    """운영 알림 — 이상 감지 consult 결과를 채팅과 분리 저장. kind는 도메인 프리픽스."""

    __tablename__ = "management_notifications"
    __table_args__ = (
        # 미해결 알림은 (org, kind, dedup_key)당 1행 — 멀티워커 dedup의 DB 백스톱.
        Index(
            "uq_mgmt_notif_open_dedup",
            "organization_id",
            "kind",
            "dedup_key",
            unique=True,
            postgresql_where=text("resolved_at IS NULL"),
            sqlite_where=text("resolved_at IS NULL"),
        ),
        Index("ix_mgmt_notif_org_recent", "organization_id", desc("last_notified_at")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # remediation만 필수
    kind: Mapped[str] = mapped_column(String(60), nullable=False)  # "management.remediation_consult"
    dedup_key: Mapped[str] = mapped_column(String(200), nullable=False)  # f"{campaign_id}:{anomaly}"
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)  # ignored|actioned|auto_normal
    consult_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    last_notified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    followup_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 2: 마이그레이션 0005 작성**

`backend/alembic/versions/0005_management_notifications.py` 신규 (0003·0004처럼 raw DDL·멱등):

```python
# 운영 알림 테이블(management_notifications) 신설 — 이상 감지 C안(하이브리드) 배달 채널
"""add management_notifications table + partial unique dedup index

Revision ID: 0005_management_notifications
Revises: 0004_generator_kb_search_vector
Create Date: 2026-07-03

스펙: docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md §1.
부분 유니크(resolved_at IS NULL)로 미해결 알림을 dedup_key당 1행으로 강제(멀티워커 백스톱).
전부 멱등 — 재실행 안전.
"""

from alembic import op

revision = "0005_management_notifications"
down_revision = "0004_generator_kb_search_vector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS management_notifications (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            campaign_id VARCHAR(100),
            kind VARCHAR(60) NOT NULL,
            dedup_key VARCHAR(200) NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            read_at TIMESTAMPTZ,
            resolved_at TIMESTAMPTZ,
            resolution VARCHAR(20),
            consult_session_id UUID,
            last_notified_at TIMESTAMPTZ NOT NULL,
            followup_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mgmt_notif_open_dedup "
        "ON management_notifications (organization_id, kind, dedup_key) "
        "WHERE resolved_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mgmt_notif_org_recent "
        "ON management_notifications (organization_id, last_notified_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS management_notifications")
```

- [ ] **Step 3: 문서 갱신**

`docs/db-schema.md`에 테이블 정의를 다른 테이블과 같은 형식으로 추가(파일을 열어 기존 형식 확인 후 동일하게).

- [ ] **Step 4: 임포트 검증**

```bash
cd backend && uv run python -c "from core.models import ManagementNotification; print('ok')"
```
Expected: `ok`

- [ ] **Step 5: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix && cd ..
git add backend/core/models.py backend/alembic/versions/0005_management_notifications.py docs/db-schema.md
git commit -m "add: management_notifications 테이블(0005) — 운영 알림 저장 + 부분 유니크 dedup"
```
