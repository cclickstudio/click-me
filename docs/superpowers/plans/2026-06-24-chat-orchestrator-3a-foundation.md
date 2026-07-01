# 챗 오케스트레이터 Phase ③-A 기반 정합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 챗 오케스트레이터(Phase ③-B/C)가 올라설 영속·임베딩·체크포인터 기반을 정합한다 — `domain/chat/` ORM·스키마 수렴 마이그레이션·BGE-M3(1024) `EmbeddingProvider` 포트·`PgChatRepo`·`PgMemoryStore`·`AsyncPostgresSaver` 체크포인터.

**Architecture:** 새 바운디드 컨텍스트 `backend/domain/chat/`를 `domain/simulation/` 구조(contracts·adapters·service·wiring)를 미러링해 만든다. 챗 ORM은 `core.db.Base`에 등록(FK가 projects/users 참조), 임베딩은 KB·LTM이 **동일 모델·차원(BGE-M3 1024)** 을 공유하도록 `EmbeddingProvider` 포트로 추상화한다. 체크포인터는 LangGraph `AsyncPostgresSaver`로 전환하되 `checkpoints*` 테이블은 라이브러리 `.setup()`이 소유(Alembic 비관리).

**Tech Stack:** FastAPI · SQLAlchemy 2.x async(asyncpg) · Alembic(수동 SQL) · pgvector `Vector(1024)` · psycopg3 + psycopg_pool(체크포인터) · langgraph-checkpoint-postgres · httpx(TEI 임베딩 클라이언트) · pytest + pytest-asyncio.

**개발 환경 (핸드오프 메모리 기준)**
- `.env`는 이미 **개인 NeonDB 복제본**(pooled)을 지목 — 공용 DB 미접촉.
- uv 파이썬 = `miniforge3\envs\aiproject`. psql/pg_dump = `miniforge3\envs\pgtools\Library\bin`(PowerShell은 `cd backend` 후 실행).
- 백엔드 .py 수정 후 커밋 전 Ruff: `cd backend && uv run ruff format . && uv run ruff check . --fix`.
- 마이그레이션/파리티는 개인 DB에서만 검증. 공용 DB 적용·푸시는 팀 합의 후 별도(이 계획 범위 밖).

**교차팀 주의 (CLAUDE.md 협업 규칙)**
- Task 3·5는 `core/models.py`의 `ManagementKbChunk`와 매니지먼트 소유 파일(`assistant/retriever.py`·`kb_ingest.py`)을 임베딩 차원 1536→1024로 바꾼다. 이는 KB·LTM 동일 차원 불변식(spec §6.1·§9) 때문이며 **사전 공지 후** 진행. 개인 DB에서만 적용한다.

---

## File Structure

**신규 생성**
- `backend/domain/chat/__init__.py` — 패키지 마커(빈 파일).
- `backend/domain/chat/models.py` — 챗 ORM 4종(`ChatSession`·`ChatMessage`·`ChatLongTermMemory`·`ChatBrandProfile`), `core.db.Base` 사용, `Vector(1024)`.
- `backend/domain/chat/contracts/__init__.py`
- `backend/domain/chat/contracts/ports.py` — `EmbeddingProvider`·`ChatRepo`·`MemoryStore` Protocol 포트(외부 의존 없음).
- `backend/domain/chat/contracts/schemas.py` — DTO(`SessionDTO`·`MessageDTO`·`MemoryItem`·`MemoryHit`) Pydantic.
- `backend/domain/chat/adapters/__init__.py`
- `backend/domain/chat/adapters/embeddings.py` — `MockEmbeddingProvider`·`TeiEmbeddingProvider`(BGE-M3)·`OpenAIEmbeddingProvider`(폴백).
- `backend/domain/chat/adapters/pg_chat_repo.py` — `PgChatRepo`(세션·메시지 영속).
- `backend/domain/chat/adapters/pg_memory_store.py` — `PgMemoryStore`(LTM 적재·임베딩 top-k 회상·salience).
- `backend/domain/chat/wiring.py` — Composition Root: `build_embedding_provider`·`build_chat_repo`·`build_memory_store`·`build_checkpointer`.
- `backend/domain/chat/checkpointer.py` — `AsyncPostgresSaver` 생성·`setup()`·URL 변환 헬퍼.
- `backend/alembic/versions/026_chat_schema_convergence.py` — 스키마 수렴 마이그레이션.
- `backend/tests/chat/__init__.py`
- `backend/tests/chat/conftest.py` — Postgres 게이트 픽스처(`CHAT_TEST_DB_URL`).
- `backend/tests/chat/test_models_registration.py` — ORM 등록·컬럼 hermetic 검증.
- `backend/tests/chat/test_embeddings.py` — mock 결정성 + TEI 어댑터(httpx MockTransport).
- `backend/tests/chat/test_pg_chat_repo.py` — 세션·메시지 CRUD(Postgres 게이트).
- `backend/tests/chat/test_pg_memory_store.py` — LTM 회상(Postgres 게이트).
- `backend/tests/chat/test_checkpointer.py` — `AsyncPostgresSaver` setup·roundtrip(Postgres 게이트).

**수정**
- `backend/pyproject.toml` — `langgraph-checkpoint-postgres`·`psycopg[binary,pool]` 의존성 추가.
- `backend/core/config.py` — 임베딩·챗 오케스트레이터 설정 키 추가.
- `backend/core/models.py` — `ChatSession` 제거(→ `domain/chat/models.py`로 이동), `ManagementKbChunk.embedding` `Vector(1536)`→`Vector(1024)`.
- `backend/api/routers/admin.py` — `ChatSession` import 출처 변경(`core.models`→`domain.chat.models`).
- `backend/domain/management/assistant/retriever.py` — 하드코딩 OpenAI 임베딩 → `EmbeddingProvider` 주입(1024).
- `backend/domain/management/assistant/kb_ingest.py` — `EmbeddingProvider`로 재적재.
- `backend/tests/test_orm_db_parity.py` — `domain.chat.models` import 추가(새 테이블 등록).

---

## 테스트 전략 (hermetic vs Postgres 게이트)

- **Hermetic(기본)** — 순수 로직(임베딩 mock 결정성, TEI 어댑터 httpx 스텁, ORM 등록·DTO, URL 변환)은 USE_MOCK 환경에서 DB 없이 실행. CI에서 항상 돈다.
- **Postgres 게이트** — `JSONB`·`pgvector`·`AsyncPostgresSaver`는 SQLite로 재현 불가. `CHAT_TEST_DB_URL`(개인 NeonDB) 설정 시에만 실행하고 미설정이면 skip. 기존 `test_orm_db_parity.py`(PARITY_DB_URL)·`test_ssr_scorer.py`(OPENAI_API_KEY) 게이트 패턴과 동형. 각 테스트는 자체 트랜잭션을 롤백하거나 생성 행을 정리해 멱등.

> 핸드오프 메모의 "PgChatRepo(sqlite)"는 `chat_messages.metadata`(JSONB)·LTM(Vector) 때문에 SQLite 불가로 판단, Postgres 게이트로 대체한다. 근거는 위와 같다.

---

### Task 1: 의존성 + 설정 키

**Files:**
- Modify: `backend/pyproject.toml:6-52` (dependencies 블록)
- Modify: `backend/core/config.py:108`(Generator 블록 위에 임베딩/챗 섹션 삽입)
- Test: `backend/tests/chat/test_config_keys.py` (신규)

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/chat/__init__.py`를 빈 파일로 생성하고 `backend/tests/chat/test_config_keys.py` 작성.

```python
# 챗/임베딩 설정 키가 기본값과 함께 존재하는지 검증(hermetic).
from core.config import settings


def test_embedding_settings_defaults():
    assert settings.embedding_provider == "bge_m3"
    assert settings.embedding_dim == 1024
    assert settings.embedding_model == "bge-m3"


def test_chat_orchestrator_settings_defaults():
    assert settings.chat_orchestrator_provider == "anthropic"
    assert settings.chat_orchestrator_model == "claude-sonnet-4-6"
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/chat/test_config_keys.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'embedding_provider'`

- [ ] **Step 3: 설정 키 추가**

`backend/core/config.py`에서 `# Generator (광고 생성)` 주석(라인 109) **바로 위**에 삽입.

```python
    # Embedding (KB·LTM 공유 — 동일 모델·차원 필수. spec §6.1/§9)
    # provider=bge_m3(기본): TEI/Ollama 로컬 서빙 1024차원. provider=openai: 1536(별도 마이그레이션 필요).
    # USE_MOCK 또는 키 부재 시 wiring이 MockEmbeddingProvider(embedding_dim 차원) 반환.
    embedding_provider: str = "bge_m3"  # bge_m3 | openai | mock
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024
    embedding_base_url: str = "http://localhost:8080"  # TEI /embed 엔드포인트
    openai_embedding_model: str = "text-embedding-3-small"  # provider=openai 폴백(1536)

    # Chat orchestrator (Phase ③-B에서 사용 — 기반 단계는 설정만 선반영)
    chat_orchestrator_provider: str = "anthropic"  # anthropic | openai | google_genai
    chat_orchestrator_model: str = "claude-sonnet-4-6"
    chat_orchestrator_temperature: float = 0.3
```

- [ ] **Step 4: 의존성 추가**

`backend/pyproject.toml`의 `# Database` 블록(라인 23-28) 끝, `"alembic>=1.13.0",` 다음 줄에 추가.

```toml
    # LangGraph 체크포인터(Postgres) — HITL thread 영속(checkpoints* 테이블)
    "langgraph-checkpoint-postgres>=2.0.0",
    "psycopg[binary,pool]>=3.2.0",
```

- [ ] **Step 5: 동기화 + 테스트 통과 확인**

Run: `cd backend && uv sync && uv run pytest tests/chat/test_config_keys.py -v`
Expected: PASS (2 passed). `uv sync`는 `langgraph-checkpoint-postgres`·`psycopg`를 설치한다.

- [ ] **Step 6: import 헬스 확인**

Run: `cd backend && uv run python -c "from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver; from psycopg_pool import AsyncConnectionPool; print('ok')"`
Expected: `ok` (패키지 해석 확인)

- [ ] **Step 7: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/pyproject.toml backend/uv.lock backend/core/config.py backend/tests/chat/
git commit -m "add: 챗 기반 — 임베딩·오케스트레이터 설정 키 + Postgres 체크포인터 의존성"
```

---

### Task 2: 챗 ORM 모델 (`domain/chat/models.py`)

**Files:**
- Create: `backend/domain/chat/__init__.py`
- Create: `backend/domain/chat/models.py`
- Modify: `backend/core/models.py:166-173` (`ChatSession` 제거)
- Modify: `backend/api/routers/admin.py:491` (import 출처 변경)
- Test: `backend/tests/chat/test_models_registration.py` (신규)

ORM은 마이그레이션 026(Task 3)이 만들 **목표 스키마**를 선언한다. 파리티 테스트(Task 9)가 ORM↔DB 일치를 보증한다.

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/chat/test_models_registration.py`.

```python
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
    assert {"id", "project_id", "user_id", "organization_id", "title", "summary",
            "created_at", "updated_at"} <= cols
    assert "messages" not in cols  # jsonb 이중화 제거


def test_chat_messages_columns():
    cols = _cols("chat_messages")
    assert {"id", "session_id", "role", "content", "route", "created_at"} <= cols


def test_chat_ltm_columns():
    cols = _cols("chat_long_term_memory")
    assert {"id", "project_id", "user_id", "memory_type", "content", "embedding",
            "salience", "last_used_at", "source_session_id", "created_at"} <= cols
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/chat/test_models_registration.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.chat'`

- [ ] **Step 3: 패키지 + 모델 작성**

`backend/domain/chat/__init__.py`를 빈 파일로 생성. `backend/domain/chat/models.py`:

```python
# 챗 오케스트레이터 ORM — 단일 chat_* 스키마. core Base에 등록(FK는 projects/users 참조).
"""대화 영속(세션·메시지)·롱텀 메모리(임베딩 회상)·브랜드 프로필.

임베딩 차원은 settings.embedding_dim(기본 1024, BGE-M3)과 일치해야 한다(KB와 공유).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.config import settings
from core.db import Base

_DIM = settings.embedding_dim  # 1024 (BGE-M3) — Vector 차원·LTM 적재 차원과 동일해야 함


class ChatSession(Base):
    """대화 세션 — 정본. messages jsonb 제거(chat_messages 행으로 정규화)."""

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String(200), server_default="새 채팅")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # 롤링 요약(토큰 윈도우 압축)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class ChatMessage(Base):
    """대화 메시지 — 정본. route로 어느 서브에이전트가 답했는지 태깅."""

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16))  # user | assistant | system | tool
    content: Mapped[str] = mapped_column(Text)
    route: Mapped[str | None] = mapped_column(String(16), nullable=True)  # general|management|simulation|generation
    meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)  # 컬럼명 metadata(예약어 회피 매핑)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ChatLongTermMemory(Base):
    """롱텀 메모리 — 세션 넘는 사실·선호·결정. 임베딩 top-k + 고salience always-load."""

    __tablename__ = "chat_long_term_memory"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    memory_type: Mapped[str] = mapped_column(String(32))  # fact | preference | decision ...
    content: Mapped[dict] = mapped_column(JSONB)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(_DIM), nullable=True)
    salience: Mapped[float] = mapped_column(server_default="0.5")  # 0~1, 항상로드 임계 이상
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    source_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ChatBrandProfile(Base):
    """구조화 브랜드 프로필 — synthesize always-load 입력(project당 1행)."""

    __tablename__ = "chat_brand_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), unique=True, nullable=False)
    brand_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String(200), nullable=True)
    product_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    keywords: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
```

> 주의 — `ChatMessage.meta`는 파이썬 속성명, DB 컬럼명은 `metadata`(SQLAlchemy 예약 속성명 `metadata` 충돌 회피). 테스트 컬럼 검사는 DB 컬럼명 `metadata`가 아니라 `Base.metadata.tables[...].columns.keys()`로 보므로 `metadata` 키가 잡힌다.

- [ ] **Step 4: core/models.py에서 ChatSession 제거**

`backend/core/models.py:166-173`의 `class ChatSession(Base): ...` 블록 전체를 삭제(주변 클래스 사이 빈 줄 1개 유지). 이 모델은 `domain/chat/models.py`로 대체됐다.

- [ ] **Step 5: admin.py import 출처 변경**

`backend/api/routers/admin.py:491`:

```python
    from domain.chat.models import ChatSession
```
(기존 `from core.models import ChatSession`에서 변경. `ChatSession.created_at`·`ChatSession.order_by` 사용부는 그대로 유효.)

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/chat/test_models_registration.py -v`
Expected: PASS (4 passed)

- [ ] **Step 7: 회귀 — admin import 깨짐 없는지**

Run: `cd backend && uv run python -c "import api.routers.admin; import domain.chat.models; print('ok')"`
Expected: `ok`

- [ ] **Step 8: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/chat/ backend/core/models.py backend/api/routers/admin.py backend/tests/chat/test_models_registration.py
git commit -m "add: 챗 ORM(domain/chat/models.py) — 세션·메시지·LTM·브랜드, ChatSession 이전"
```

---

### Task 3: 마이그레이션 026 — 스키마 수렴

**Files:**
- Create: `backend/alembic/versions/026_chat_schema_convergence.py`
- Test: 개인 DB 적용 + 파리티(Task 9에서 종합). 본 Task는 적용·검증 단계까지.

스키마 변경(spec §6.2): `chat_sessions`(messages 제거·user_id/org/title/summary/updated_at 추가) · `chat_messages`(route 추가) · `chat_long_term_memory`(embedding 1024·salience·last_used_at·source_session_id 추가) · `management_kb_chunks`(embedding 1536→1024, 재적재 필요).

- [ ] **Step 1: 마이그레이션 작성**

`backend/alembic/versions/026_chat_schema_convergence.py`:

```python
"""chat 스키마 수렴 — Phase ③-A (spec §6.2)

chat_sessions: messages jsonb 제거 + user_id/organization_id/title/summary/updated_at 추가.
chat_messages: route 컬럼 추가.
chat_long_term_memory: embedding vector(1024)/salience/last_used_at/source_session_id 추가.
management_kb_chunks: embedding 1536→1024 (KB·LTM 동일 차원 불변식). 데이터 비우고 재적재 필요.

모두 멱등(IF [NOT] EXISTS). 개인 DB에서만 적용 — 공용 DB는 팀 합의 후.

Revision ID: 026
Revises: 025
"""

from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) chat_sessions — 이중화 messages 제거, 세션 메타 추가, created_at naive→timestamptz 통일.
    #    실 DB는 {id, project_id, created_at(naive), messages}만 보유 → 아래 ADD는 모두 신규.
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS messages")
    op.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS user_id UUID")
    op.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS organization_id UUID")
    op.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS title VARCHAR(200) DEFAULT '새 채팅'")
    op.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS summary TEXT")
    op.execute(
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
    )
    op.execute(
        "ALTER TABLE chat_sessions ALTER COLUMN created_at TYPE TIMESTAMPTZ "
        "USING created_at AT TIME ZONE 'UTC'"
    )

    # 2) chat_messages — route 태깅 + role enum(chat_role)→varchar(asyncpg enum insert 회피) + session_id 인덱스.
    op.execute("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS route VARCHAR(16)")
    op.execute("ALTER TABLE chat_messages ALTER COLUMN role TYPE VARCHAR(16) USING role::text")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chat_messages_session_id ON chat_messages (session_id)"
    )

    # 3) chat_long_term_memory — 의미 회상 컬럼(024가 기본 테이블 생성)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE chat_long_term_memory ADD COLUMN IF NOT EXISTS embedding vector(1024)")
    op.execute(
        "ALTER TABLE chat_long_term_memory ADD COLUMN IF NOT EXISTS salience DOUBLE PRECISION NOT NULL DEFAULT 0.5"
    )
    op.execute("ALTER TABLE chat_long_term_memory ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ")
    op.execute("ALTER TABLE chat_long_term_memory ADD COLUMN IF NOT EXISTS source_session_id UUID")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chat_ltm_salience ON chat_long_term_memory (salience DESC)"
    )

    # 4) management_kb_chunks — 1536→1024 (KB·LTM 동일 차원). 기존 벡터는 차원 불일치라 폐기·재적재.
    #    TRUNCATE 후 컬럼 타입 교체. 재적재: uv run python -m domain.management.assistant.kb_ingest
    op.execute("TRUNCATE TABLE management_kb_chunks")
    op.execute("ALTER TABLE management_kb_chunks ALTER COLUMN embedding TYPE vector(1024)")


def downgrade() -> None:
    op.execute("ALTER TABLE management_kb_chunks ALTER COLUMN embedding TYPE vector(1536)")
    op.execute("DROP INDEX IF EXISTS ix_chat_ltm_salience")
    op.execute("ALTER TABLE chat_long_term_memory DROP COLUMN IF EXISTS source_session_id")
    op.execute("ALTER TABLE chat_long_term_memory DROP COLUMN IF EXISTS last_used_at")
    op.execute("ALTER TABLE chat_long_term_memory DROP COLUMN IF EXISTS salience")
    op.execute("ALTER TABLE chat_long_term_memory DROP COLUMN IF EXISTS embedding")
    op.execute("DROP INDEX IF EXISTS ix_chat_messages_session_id")
    op.execute("ALTER TABLE chat_messages ALTER COLUMN role TYPE chat_role USING role::chat_role")
    op.execute("ALTER TABLE chat_messages DROP COLUMN IF EXISTS route")
    op.execute(
        "ALTER TABLE chat_sessions ALTER COLUMN created_at TYPE TIMESTAMP "
        "USING created_at AT TIME ZONE 'UTC'"
    )
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS summary")
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS title")
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS organization_id")
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS user_id")
    op.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS messages JSONB DEFAULT '[]'::jsonb")
```

> `chat_messages`는 001에서 이미 생성(`metadata` jsonb·`tokens_used` 포함)되고 025에서 드롭되지 않았으므로 `route`만 추가하면 ORM과 일치한다. 적용 전 `\d chat_messages`로 컬럼 존재를 한 번 확인(아래 Step 2).

- [ ] **Step 2: 적용 전 현재 컬럼 스냅샷(개인 DB)**

PowerShell:
```powershell
cd backend
$env:Path = "C:\Users\804\miniforge3\envs\pgtools\Library\bin;$env:Path"
# DATABASE_URL은 .env 기준. psql은 postgresql:// 형식 필요(+asyncpg 제거).
```
`psql "<개인DB DSN>" -c "\d chat_messages"` 로 `metadata`·`tokens_used`·`session_id` 존재 확인. `\d chat_long_term_memory`로 024 기본 컬럼 확인.
Expected: chat_messages에 session_id·role·content·metadata·tokens_used·created_at 존재(route 없음).

- [ ] **Step 3: 마이그레이션 적용(개인 DB)**

Run: `cd backend && uv run alembic upgrade head`
Expected: `Running upgrade 025 -> 026, chat 스키마 수렴` 로그, 에러 없음.

- [ ] **Step 4: 적용 결과 검증**

`psql`:
```
\d chat_sessions   -- messages 없음, user_id/organization_id/title/summary/updated_at 있음
\d chat_messages   -- route 있음
\d chat_long_term_memory  -- embedding vector(1024)/salience/last_used_at/source_session_id 있음
\d management_kb_chunks    -- embedding vector(1024)
```
Expected: 위 4개 모두 ORM 선언과 일치.

- [ ] **Step 5: alembic 정합 확인**

Run: `cd backend && uv run alembic current`
Expected: `026 (head)`

- [ ] **Step 6: 커밋**

```bash
git add backend/alembic/versions/026_chat_schema_convergence.py
git commit -m "add: 마이그레이션 026 — chat 스키마 수렴(세션 메타·route·LTM 임베딩 1024·KB 1024)"
```

---

### Task 4: EmbeddingProvider 포트 + 어댑터 + wiring

**Files:**
- Create: `backend/domain/chat/contracts/__init__.py`
- Create: `backend/domain/chat/contracts/ports.py`
- Create: `backend/domain/chat/adapters/__init__.py`
- Create: `backend/domain/chat/adapters/embeddings.py`
- Create: `backend/domain/chat/wiring.py`
- Test: `backend/tests/chat/test_embeddings.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/chat/test_embeddings.py`:

```python
# 임베딩 어댑터 — mock 결정성 + TEI(BGE-M3) HTTP 계약(hermetic).
import httpx
import pytest

from domain.chat.adapters.embeddings import MockEmbeddingProvider, TeiEmbeddingProvider


@pytest.mark.asyncio
async def test_mock_provider_is_deterministic_and_right_dim():
    p = MockEmbeddingProvider(dim=1024)
    a = await p.embed(["안녕"])
    b = await p.embed(["안녕"])
    assert len(a) == 1 and len(a[0]) == 1024
    assert a == b  # 같은 입력 → 같은 벡터
    c = await p.embed(["다른 문장"])
    assert c[0] != a[0]


@pytest.mark.asyncio
async def test_mock_provider_batch():
    p = MockEmbeddingProvider(dim=1024)
    out = await p.embed(["x", "y", "z"])
    assert len(out) == 3 and all(len(v) == 1024 for v in out)


@pytest.mark.asyncio
async def test_tei_provider_parses_embed_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/embed"
        return httpx.Response(200, json=[[0.1] * 1024, [0.2] * 1024])

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://tei")
    p = TeiEmbeddingProvider(base_url="http://tei", client=client)
    out = await p.embed(["a", "b"])
    assert len(out) == 2 and len(out[0]) == 1024
    assert out[0][0] == pytest.approx(0.1)
    await client.aclose()
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/chat/test_embeddings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.chat.adapters.embeddings'`

- [ ] **Step 3: 포트 작성**

`backend/domain/chat/contracts/__init__.py`(빈 파일), `backend/domain/chat/contracts/ports.py`:

```python
# 챗 도메인 포트 — 외부 의존 없는 Protocol 계약(adapters가 구현, wiring이 주입).
"""EmbeddingProvider(KB·LTM 공유 임베딩) · ChatRepo(세션·메시지 영속) · MemoryStore(LTM)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from domain.chat.contracts.schemas import MemoryHit, MemoryItem, MessageDTO, SessionDTO


class EmbeddingProvider(Protocol):
    """텍스트 → 임베딩 벡터. KB·LTM이 동일 구현(동일 모델·차원)을 공유한다."""

    @property
    def dim(self) -> int: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class ChatRepo(Protocol):
    """세션·메시지 영속(정규화 행)."""

    async def create_session(
        self, *, project_id: uuid.UUID | None, user_id: uuid.UUID | None,
        organization_id: uuid.UUID | None, title: str,
    ) -> SessionDTO: ...

    async def get_session(self, session_id: uuid.UUID) -> SessionDTO | None: ...

    async def list_sessions(self, *, user_id: uuid.UUID | None, limit: int) -> list[SessionDTO]: ...

    async def append_message(
        self, *, session_id: uuid.UUID, role: str, content: str,
        route: str | None, meta: dict | None,
    ) -> MessageDTO: ...

    async def get_messages(self, session_id: uuid.UUID, *, limit: int) -> list[MessageDTO]: ...

    async def update_summary(self, session_id: uuid.UUID, summary: str) -> None: ...


class MemoryStore(Protocol):
    """롱텀 메모리 — 적재(임베딩 포함)·임베딩 top-k 회상·고salience always-load."""

    async def write(self, item: MemoryItem) -> uuid.UUID: ...

    async def recall(
        self, *, query: str, project_id: uuid.UUID | None, user_id: uuid.UUID | None,
        k: int, salience_floor: float,
    ) -> list[MemoryHit]: ...
```

`backend/domain/chat/contracts/schemas.py`:

```python
# 챗 도메인 DTO — 포트 입출력 계약(Pydantic).
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SessionDTO(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    title: str = "새 채팅"
    summary: str | None = None
    created_at: datetime
    updated_at: datetime


class MessageDTO(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    route: str | None = None
    meta: dict = Field(default_factory=dict)
    created_at: datetime


class MemoryItem(BaseModel):
    project_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    memory_type: str
    content: dict
    salience: float = 0.5
    source_session_id: uuid.UUID | None = None


class MemoryHit(BaseModel):
    id: uuid.UUID
    memory_type: str
    content: dict
    salience: float
    score: float  # 코사인 유사도(1=동일); always-load 항목은 1.0
```

- [ ] **Step 4: 임베딩 어댑터 작성**

`backend/domain/chat/adapters/__init__.py`(빈 파일), `backend/domain/chat/adapters/embeddings.py`:

```python
# 임베딩 어댑터 — Mock(결정론)·TEI(BGE-M3 로컬)·OpenAI(폴백). EmbeddingProvider 구현.
"""KB·LTM 공유 임베딩. 기본 TEI(/embed, BGE-M3 1024). USE_MOCK/키부재 시 Mock."""

from __future__ import annotations

import hashlib
import struct

import httpx


class MockEmbeddingProvider:
    """결정론 mock — 텍스트 해시 시드로 단위벡터 생성(테스트·USE_MOCK)."""

    def __init__(self, dim: int = 1024) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def _vec(self, text: str) -> list[float]:
        out: list[float] = []
        i = 0
        while len(out) < self._dim:
            h = hashlib.sha256(f"{text}:{i}".encode()).digest()
            for j in range(0, len(h), 4):
                if len(out) >= self._dim:
                    break
                out.append(struct.unpack("<I", h[j : j + 4])[0] / 2**32)
            i += 1
        norm = sum(x * x for x in out) ** 0.5 or 1.0
        return [x / norm for x in out]


class TeiEmbeddingProvider:
    """text-embeddings-inference /embed — BGE-M3(1024). Ollama는 base_url·경로만 교체."""

    def __init__(self, base_url: str, *, dim: int = 1024, client: httpx.AsyncClient | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._dim = dim
        self._client = client or httpx.AsyncClient(base_url=self._base, timeout=30.0)

    @property
    def dim(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.post("/embed", json={"inputs": texts})
        resp.raise_for_status()
        return resp.json()  # TEI: list[list[float]]


class OpenAIEmbeddingProvider:
    """OpenAI 폴백 — text-embedding-3-small(1536). provider=openai 시 embedding_dim=1536 필요."""

    def __init__(self, *, api_key: str, model: str = "text-embedding-3-small", dim: int = 1536) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in resp.data]
```

- [ ] **Step 5: wiring 작성(임베딩 빌더만 — 나머지는 Task 6~8에서 추가)**

`backend/domain/chat/wiring.py`:

```python
# 챗 Composition Root — 어댑터를 포트에 꽂는 유일한 지점(mock↔실연동 전환).
"""build_embedding_provider만 우선. chat_repo·memory_store·checkpointer는 후속 Task에서 추가."""

from __future__ import annotations

from core.config import settings
from domain.chat.contracts.ports import EmbeddingProvider


def build_embedding_provider(s=settings) -> EmbeddingProvider:
    """USE_MOCK/mock → Mock. bge_m3 → TEI. openai → OpenAI 폴백(1536)."""
    provider = getattr(s, "embedding_provider", "bge_m3")
    dim = getattr(s, "embedding_dim", 1024)

    if getattr(s, "use_mock", True) or provider == "mock":
        from domain.chat.adapters.embeddings import MockEmbeddingProvider

        return MockEmbeddingProvider(dim=dim)

    if provider == "openai":
        from domain.chat.adapters.embeddings import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider(
            api_key=s.openai_api_key, model=s.openai_embedding_model, dim=dim
        )

    from domain.chat.adapters.embeddings import TeiEmbeddingProvider

    return TeiEmbeddingProvider(base_url=s.embedding_base_url, dim=dim)
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/chat/test_embeddings.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: wiring 스모크 + Ruff + 커밋**

Run: `cd backend && USE_MOCK=true uv run python -c "from domain.chat.wiring import build_embedding_provider; p=build_embedding_provider(); print(type(p).__name__, p.dim)"`
Expected: `MockEmbeddingProvider 1024`

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/chat/contracts/ backend/domain/chat/adapters/ backend/domain/chat/wiring.py backend/tests/chat/test_embeddings.py
git commit -m "add: EmbeddingProvider 포트 + Mock·TEI(BGE-M3)·OpenAI 어댑터 + wiring"
```

---

### Task 5: 매니지먼트 KB를 EmbeddingProvider(1024)로 전환  [교차팀]

**Files:**
- Modify: `backend/domain/management/assistant/retriever.py`
- Modify: `backend/domain/management/assistant/kb_ingest.py`
- Test: `backend/tests/chat/test_kb_embed_switch.py` (신규, hermetic)

KB·LTM 동일 차원 불변식을 위해 KB 임베딩을 OpenAI(1536) 하드코딩에서 `EmbeddingProvider`(1024)로 전환한다. 코사인 검색 SQL은 그대로(차원만 변경).

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/chat/test_kb_embed_switch.py`:

```python
# KbRetriever가 주입된 EmbeddingProvider로 임베딩하는지(1024) hermetic 검증.
import pytest

from domain.chat.adapters.embeddings import MockEmbeddingProvider
from domain.management.assistant.retriever import KbRetriever


@pytest.mark.asyncio
async def test_retriever_uses_injected_provider():
    provider = MockEmbeddingProvider(dim=1024)
    r = KbRetriever(embedder=provider, session_factory=None)
    emb = await r.embed("캠페인 예산 가이드")
    assert len(emb) == 1024
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/chat/test_kb_embed_switch.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'embedder'`

- [ ] **Step 3: retriever.py 전환**

`backend/domain/management/assistant/retriever.py` 전체를 교체.

```python
# 매니지먼트 KB 벡터 검색 — pgvector 코사인 top-k (RAG retrieval)
"""쿼리를 임베딩해 management_kb_chunks에서 코사인 유사 청크를 가져온다.

임베딩은 EmbeddingProvider(기본 BGE-M3 1024) — KB·LTM 동일 차원(spec §6.1/§9).
"""

from __future__ import annotations

from sqlalchemy import select

from core.db import AsyncSessionLocal
from core.models import ManagementKbChunk
from domain.chat.contracts.ports import EmbeddingProvider


class KbRetriever:
    """pgvector 코사인 검색 리트리버 — EmbeddingProvider·세션 팩토리 주입(테스트)."""

    def __init__(self, embedder: EmbeddingProvider, session_factory=AsyncSessionLocal) -> None:
        self._embedder = embedder
        self._sf = session_factory

    async def embed(self, text: str) -> list[float]:
        out = await self._embedder.embed([text])
        return out[0]

    async def search(self, query: str, k: int = 4) -> list[dict]:
        emb = await self.embed(query)
        dist = ManagementKbChunk.embedding.cosine_distance(emb).label("dist")
        async with self._sf() as db:
            rows = (await db.execute(select(ManagementKbChunk, dist).order_by(dist).limit(k))).all()
        return [
            {
                "source": r.ManagementKbChunk.source,
                "title": r.ManagementKbChunk.title,
                "chunk": r.ManagementKbChunk.chunk,
                "score": round(1.0 - float(r.dist), 3),
            }
            for r in rows
        ]
```

- [ ] **Step 4: KbRetriever 호출부 갱신**

`backend/domain/management/assistant/agent.py`에서 `KbRetriever(api_key=api_key)` 생성부를 찾아 `EmbeddingProvider` 주입으로 변경.

```python
    from domain.chat.wiring import build_embedding_provider

    retriever = KbRetriever(embedder=build_embedding_provider(settings))
```
(기존 `retriever = KbRetriever(api_key=api_key)` 라인 대체. `agent.py` 상단 import 정리는 Ruff가 처리.)

- [ ] **Step 5: kb_ingest.py 전환**

`backend/domain/management/assistant/kb_ingest.py`의 `ingest()`를 EmbeddingProvider 사용으로 교체.

```python
async def ingest() -> int:
    from domain.chat.wiring import build_embedding_provider

    embedder = build_embedding_provider(settings)
    total = 0
    async with AsyncSessionLocal() as db:
        for md in sorted(_KB_DIR.glob("*.md")):
            source = md.name
            sections = _chunk_markdown(md.read_text(encoding="utf-8"))
            if not sections:
                continue
            vectors = await embedder.embed([c for _, c in sections])
            await db.execute(delete(ManagementKbChunk).where(ManagementKbChunk.source == source))
            for (title, chunk), vec in zip(sections, vectors, strict=True):
                db.add(ManagementKbChunk(source=source, title=title, chunk=chunk, embedding=vec))
            total += len(sections)
            print(f"  {source}: {len(sections)} chunks")
        await db.commit()
    print(f"적재 완료: {total} chunks")
    return total
```
상단의 `from openai import AsyncOpenAI`·`from domain.management.assistant.retriever import EMBEDDING_MODEL` import는 제거(미사용).

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/chat/test_kb_embed_switch.py -v`
Expected: PASS (1 passed)

- [ ] **Step 7: KB 재적재(개인 DB, 실 임베딩)**

> BGE-M3 서빙(TEI/Ollama)이 떠 있고 `EMBEDDING_BASE_URL`이 그것을 가리킬 때 실행. 서빙 미준비면 이 step은 보류하고 Task 마무리(재적재는 서빙 기동 후). USE_MOCK이면 Mock 벡터가 적재되니 실서빙으로 실행.

Run: `cd backend && USE_MOCK=false EMBEDDING_PROVIDER=bge_m3 uv run python -m domain.management.assistant.kb_ingest`
Expected: `적재 완료: N chunks` (management_kb_chunks가 1024 벡터로 재적재)

- [ ] **Step 8: 매니지먼트 어시스턴트 회귀**

Run: `cd backend && uv run pytest tests/management -v -k "assistant or retriev or kb"`
Expected: 통과(또는 사전 동일 수준). 깨지면 KbRetriever 시그니처 변경 영향 — 호출부 추가 수정.

- [ ] **Step 9: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/management/assistant/retriever.py backend/domain/management/assistant/kb_ingest.py backend/domain/management/assistant/agent.py backend/tests/chat/test_kb_embed_switch.py
git commit -m "edit: 매니지먼트 KB 임베딩을 EmbeddingProvider(BGE-M3 1024)로 전환 — KB·LTM 차원 통일"
```

---

### Task 6: PgChatRepo — 세션·메시지 영속

**Files:**
- Create: `backend/domain/chat/adapters/pg_chat_repo.py`
- Modify: `backend/domain/chat/wiring.py` (`build_chat_repo` 추가)
- Test: `backend/tests/chat/conftest.py`(신규), `backend/tests/chat/test_pg_chat_repo.py`

- [ ] **Step 1: Postgres 게이트 conftest 작성**

`backend/tests/chat/__init__.py`는 Task 1에서 생성됨. `backend/tests/chat/conftest.py`:

```python
# 챗 Postgres 게이트 픽스처 — CHAT_TEST_DB_URL(개인 NeonDB) 있을 때만. JSONB/pgvector는 SQLite 불가.
import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.db import _normalize_database_url

_URL = os.environ.get("CHAT_TEST_DB_URL")
pg_only = pytest.mark.skipif(not _URL, reason="CHAT_TEST_DB_URL 미설정 — Postgres 전용 테스트 skip")


@pytest_asyncio.fixture
async def pg_session_factory():
    """개인 DB 세션 팩토리. 테스트는 생성 데이터를 자체 정리(멱등)."""
    engine = create_async_engine(_normalize_database_url(_URL), pool_pre_ping=True)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield sf
    finally:
        await engine.dispose()
```

- [ ] **Step 2: 실패 테스트 작성**

`backend/tests/chat/test_pg_chat_repo.py`:

```python
# PgChatRepo 세션·메시지 CRUD — 개인 Postgres 게이트.
import uuid

import pytest
from sqlalchemy import delete

from domain.chat.adapters.pg_chat_repo import PgChatRepo
from domain.chat.models import ChatMessage, ChatSession
from tests.chat.conftest import pg_only


@pg_only
@pytest.mark.asyncio
async def test_create_append_and_read(pg_session_factory):
    repo = PgChatRepo(session_factory=pg_session_factory)
    s = await repo.create_session(
        project_id=None, user_id=None, organization_id=None, title="테스트 세션"
    )
    try:
        m1 = await repo.append_message(
            session_id=s.id, role="user", content="안녕", route=None, meta=None
        )
        await repo.append_message(
            session_id=s.id, role="assistant", content="네", route="management", meta={"k": 1}
        )
        msgs = await repo.get_messages(s.id, limit=10)
        assert [m.role for m in msgs] == ["user", "assistant"]
        assert msgs[1].route == "management" and msgs[1].meta == {"k": 1}
        assert m1.session_id == s.id

        await repo.update_summary(s.id, "요약본")
        got = await repo.get_session(s.id)
        assert got.summary == "요약본"
    finally:
        async with pg_session_factory() as db:
            await db.execute(delete(ChatMessage).where(ChatMessage.session_id == s.id))
            await db.execute(delete(ChatSession).where(ChatSession.id == s.id))
            await db.commit()
```

- [ ] **Step 3: 실패 확인**

Run: `cd backend && CHAT_TEST_DB_URL="<개인DB DSN>" uv run pytest tests/chat/test_pg_chat_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: ...pg_chat_repo`
(미설정 시 SKIPPED — 그래도 통과로 간주되니 반드시 DSN 주고 실패를 확인.)

- [ ] **Step 4: PgChatRepo 작성**

`backend/domain/chat/adapters/pg_chat_repo.py`:

```python
# PgChatRepo — chat_sessions·chat_messages 영속(ChatRepo 포트 구현).
from __future__ import annotations

import uuid

from sqlalchemy import select, update

from core.db import AsyncSessionLocal
from domain.chat.contracts.schemas import MessageDTO, SessionDTO
from domain.chat.models import ChatMessage, ChatSession


class PgChatRepo:
    """세션·메시지 CRUD. 세션 팩토리 주입(테스트는 개인 DB 팩토리)."""

    def __init__(self, session_factory=AsyncSessionLocal) -> None:
        self._sf = session_factory

    async def create_session(
        self, *, project_id, user_id, organization_id, title="새 채팅"
    ) -> SessionDTO:
        row = ChatSession(
            project_id=project_id, user_id=user_id, organization_id=organization_id, title=title
        )
        async with self._sf() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
        return self._to_session(row)

    async def get_session(self, session_id: uuid.UUID) -> SessionDTO | None:
        async with self._sf() as db:
            row = await db.get(ChatSession, session_id)
        return self._to_session(row) if row else None

    async def list_sessions(self, *, user_id, limit=20) -> list[SessionDTO]:
        stmt = select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(limit)
        if user_id is not None:
            stmt = stmt.where(ChatSession.user_id == user_id)
        async with self._sf() as db:
            rows = (await db.execute(stmt)).scalars().all()
        return [self._to_session(r) for r in rows]

    async def append_message(
        self, *, session_id, role, content, route=None, meta=None
    ) -> MessageDTO:
        row = ChatMessage(
            session_id=session_id, role=role, content=content, route=route, meta=meta or {}
        )
        async with self._sf() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
        return self._to_message(row)

    async def get_messages(self, session_id: uuid.UUID, *, limit=100) -> list[MessageDTO]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
        )
        async with self._sf() as db:
            rows = (await db.execute(stmt)).scalars().all()
        return [self._to_message(r) for r in rows]

    async def update_summary(self, session_id: uuid.UUID, summary: str) -> None:
        async with self._sf() as db:
            await db.execute(
                update(ChatSession).where(ChatSession.id == session_id).values(summary=summary)
            )
            await db.commit()

    @staticmethod
    def _to_session(r: ChatSession) -> SessionDTO:
        return SessionDTO(
            id=r.id, project_id=r.project_id, user_id=r.user_id,
            organization_id=r.organization_id, title=r.title, summary=r.summary,
            created_at=r.created_at, updated_at=r.updated_at,
        )

    @staticmethod
    def _to_message(r: ChatMessage) -> MessageDTO:
        return MessageDTO(
            id=r.id, session_id=r.session_id, role=r.role, content=r.content,
            route=r.route, meta=r.meta or {}, created_at=r.created_at,
        )
```

- [ ] **Step 5: wiring에 build_chat_repo 추가**

`backend/domain/chat/wiring.py` 끝에 추가.

```python
def build_chat_repo(s=settings):
    """세션·메시지 영속 — 단일 구현(PgChatRepo). 세션 팩토리는 core 기본."""
    from domain.chat.adapters.pg_chat_repo import PgChatRepo

    return PgChatRepo()
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd backend && CHAT_TEST_DB_URL="<개인DB DSN>" uv run pytest tests/chat/test_pg_chat_repo.py -v`
Expected: PASS (1 passed)

- [ ] **Step 7: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/chat/adapters/pg_chat_repo.py backend/domain/chat/wiring.py backend/tests/chat/conftest.py backend/tests/chat/test_pg_chat_repo.py
git commit -m "add: PgChatRepo — 세션·메시지 영속(ChatRepo 포트) + Postgres 게이트 테스트"
```

---

### Task 7: PgMemoryStore — LTM 적재·임베딩 회상

**Files:**
- Create: `backend/domain/chat/adapters/pg_memory_store.py`
- Modify: `backend/domain/chat/wiring.py` (`build_memory_store` 추가)
- Test: `backend/tests/chat/test_pg_memory_store.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/chat/test_pg_memory_store.py`:

```python
# PgMemoryStore 적재·임베딩 top-k 회상 — 개인 Postgres 게이트.
import pytest
from sqlalchemy import delete

from domain.chat.adapters.embeddings import MockEmbeddingProvider
from domain.chat.adapters.pg_memory_store import PgMemoryStore
from domain.chat.contracts.schemas import MemoryItem
from domain.chat.models import ChatLongTermMemory
from tests.chat.conftest import pg_only


@pg_only
@pytest.mark.asyncio
async def test_write_then_recall_nearest(pg_session_factory):
    store = PgMemoryStore(embedder=MockEmbeddingProvider(dim=1024), session_factory=pg_session_factory)
    ids = []
    try:
        ids.append(await store.write(MemoryItem(
            memory_type="fact", content={"text": "브랜드 톤은 친근하고 활기차다"}, salience=0.6,
        )))
        ids.append(await store.write(MemoryItem(
            memory_type="fact", content={"text": "예산은 분기당 천만원"}, salience=0.4,
        )))
        hits = await store.recall(
            query="브랜드 톤은 친근하고 활기차다", project_id=None, user_id=None,
            k=1, salience_floor=2.0,  # always-load 제외(2.0 초과 없음)
        )
        assert hits and hits[0].content["text"].startswith("브랜드 톤")
    finally:
        async with pg_session_factory() as db:
            for i in ids:
                await db.execute(delete(ChatLongTermMemory).where(ChatLongTermMemory.id == i))
            await db.commit()


@pg_only
@pytest.mark.asyncio
async def test_high_salience_always_loaded(pg_session_factory):
    store = PgMemoryStore(embedder=MockEmbeddingProvider(dim=1024), session_factory=pg_session_factory)
    mid = await store.write(MemoryItem(
        memory_type="preference", content={"text": "항상 한국어로 답하라"}, salience=0.95,
    ))
    try:
        hits = await store.recall(
            query="전혀 무관한 질문", project_id=None, user_id=None, k=1, salience_floor=0.9,
        )
        assert any(h.id == mid and h.score == 1.0 for h in hits)
    finally:
        async with pg_session_factory() as db:
            await db.execute(delete(ChatLongTermMemory).where(ChatLongTermMemory.id == mid))
            await db.commit()
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && CHAT_TEST_DB_URL="<개인DB DSN>" uv run pytest tests/chat/test_pg_memory_store.py -v`
Expected: FAIL — `ModuleNotFoundError: ...pg_memory_store`

- [ ] **Step 3: PgMemoryStore 작성**

`backend/domain/chat/adapters/pg_memory_store.py`:

```python
# PgMemoryStore — chat_long_term_memory 적재·임베딩 top-k 회상(MemoryStore 포트).
"""write: 텍스트(content) 임베딩 후 적재. recall: 임베딩 코사인 top-k + 고salience always-load."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from core.db import AsyncSessionLocal
from domain.chat.contracts.ports import EmbeddingProvider
from domain.chat.contracts.schemas import MemoryHit, MemoryItem
from domain.chat.models import ChatLongTermMemory


class PgMemoryStore:
    def __init__(self, embedder: EmbeddingProvider, session_factory=AsyncSessionLocal) -> None:
        self._embedder = embedder
        self._sf = session_factory

    @staticmethod
    def _text(content: dict) -> str:
        return content.get("text") or " ".join(str(v) for v in content.values())

    async def write(self, item: MemoryItem) -> uuid.UUID:
        vec = (await self._embedder.embed([self._text(item.content)]))[0]
        row = ChatLongTermMemory(
            project_id=item.project_id, user_id=item.user_id, memory_type=item.memory_type,
            content=item.content, embedding=vec, salience=item.salience,
            source_session_id=item.source_session_id,
        )
        async with self._sf() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
        return row.id

    async def recall(
        self, *, query: str, project_id, user_id, k: int = 5, salience_floor: float = 0.9
    ) -> list[MemoryHit]:
        qvec = (await self._embedder.embed([query]))[0]
        dist = ChatLongTermMemory.embedding.cosine_distance(qvec).label("dist")

        def _scope(stmt):
            if project_id is not None:
                stmt = stmt.where(ChatLongTermMemory.project_id == project_id)
            if user_id is not None:
                stmt = stmt.where(ChatLongTermMemory.user_id == user_id)
            return stmt

        topk_stmt = _scope(
            select(ChatLongTermMemory, dist)
            .where(ChatLongTermMemory.embedding.is_not(None))
            .order_by(dist)
            .limit(k)
        )
        always_stmt = _scope(
            select(ChatLongTermMemory).where(ChatLongTermMemory.salience >= salience_floor)
        )

        async with self._sf() as db:
            top_rows = (await db.execute(topk_stmt)).all()
            always_rows = (await db.execute(always_stmt)).scalars().all()

        hits: dict[uuid.UUID, MemoryHit] = {}
        for m in always_rows:
            hits[m.id] = MemoryHit(
                id=m.id, memory_type=m.memory_type, content=m.content, salience=m.salience, score=1.0
            )
        for r in top_rows:
            m = r.ChatLongTermMemory
            if m.id not in hits:
                hits[m.id] = MemoryHit(
                    id=m.id, memory_type=m.memory_type, content=m.content,
                    salience=m.salience, score=round(1.0 - float(r.dist), 3),
                )
        return sorted(hits.values(), key=lambda h: h.score, reverse=True)
```

- [ ] **Step 4: wiring에 build_memory_store 추가**

`backend/domain/chat/wiring.py` 끝에 추가.

```python
def build_memory_store(s=settings):
    """롱텀 메모리 — EmbeddingProvider 주입(KB와 동일 구현)."""
    from domain.chat.adapters.pg_memory_store import PgMemoryStore

    return PgMemoryStore(embedder=build_embedding_provider(s))
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd backend && CHAT_TEST_DB_URL="<개인DB DSN>" uv run pytest tests/chat/test_pg_memory_store.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/chat/adapters/pg_memory_store.py backend/domain/chat/wiring.py backend/tests/chat/test_pg_memory_store.py
git commit -m "add: PgMemoryStore — LTM 적재·임베딩 top-k 회상·고salience always-load"
```

---

### Task 8: AsyncPostgresSaver 체크포인터

**Files:**
- Create: `backend/domain/chat/checkpointer.py`
- Modify: `backend/domain/chat/wiring.py` (`build_checkpointer` 추가)
- Test: `backend/tests/chat/test_checkpointer.py`

`checkpoints*` 테이블은 라이브러리 `.setup()`이 소유(Alembic 비관리). DB URL은 psycopg3 형식(`postgresql://`, `+asyncpg` 제거)으로 변환.

- [ ] **Step 1: URL 변환 + 실패 테스트 작성**

`backend/tests/chat/test_checkpointer.py`:

```python
# 체크포인터 — URL 변환(hermetic) + AsyncPostgresSaver setup·roundtrip(Postgres 게이트).
import os

import pytest

from domain.chat.checkpointer import to_psycopg_conninfo
from tests.chat.conftest import pg_only


def test_to_psycopg_conninfo_strips_asyncpg():
    out = to_psycopg_conninfo("postgresql+asyncpg://u:p@h/db?sslmode=require")
    assert out.startswith("postgresql://")
    assert "+asyncpg" not in out
    assert "sslmode=require" in out


@pg_only
@pytest.mark.asyncio
async def test_checkpointer_setup_and_roundtrip():
    from domain.chat.checkpointer import build_async_checkpointer

    saver, close = await build_async_checkpointer(os.environ["CHAT_TEST_DB_URL"])
    try:
        config = {"configurable": {"thread_id": "test-thread-1", "checkpoint_ns": ""}}
        cp = {"v": 1, "id": "cp-1", "ts": "2026-06-24T00:00:00+00:00", "channel_values": {},
              "channel_versions": {}, "versions_seen": {}, "pending_sends": []}
        await saver.aput(config, cp, {}, {})
        got = await saver.aget(config)
        assert got is not None and got["id"] == "cp-1"
    finally:
        await close()
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/chat/test_checkpointer.py::test_to_psycopg_conninfo_strips_asyncpg -v`
Expected: FAIL — `ModuleNotFoundError: ...checkpointer`

- [ ] **Step 3: checkpointer.py 작성**

`backend/domain/chat/checkpointer.py`:

```python
# AsyncPostgresSaver 체크포인터 — HITL thread 영속(checkpoints* 테이블, 라이브러리 .setup() 소유).
"""build_async_checkpointer: psycopg 풀로 AsyncPostgresSaver 생성·setup. close 콜백 함께 반환."""

from __future__ import annotations

from collections.abc import Awaitable, Callable


def to_psycopg_conninfo(url: str) -> str:
    """SQLAlchemy/asyncpg URL → psycopg3 conninfo. +asyncpg 제거(sslmode/channel_binding은 psycopg 호환)."""
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


async def build_async_checkpointer(database_url: str):
    """(saver, close) 반환. saver는 setup() 완료 상태. close()로 풀 정리."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    conninfo = to_psycopg_conninfo(database_url)
    pool = AsyncConnectionPool(
        conninfo=conninfo,
        max_size=5,
        open=False,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )
    await pool.open()
    saver = AsyncPostgresSaver(pool)
    await saver.setup()  # checkpoints* 멱등 생성/마이그레이션

    async def close() -> None:
        await pool.close()

    return saver, close


_close: Callable[[], Awaitable[None]] | None = None
```

- [ ] **Step 4: wiring에 build_checkpointer 추가**

`backend/domain/chat/wiring.py` 끝에 추가.

```python
async def build_checkpointer(s=settings):
    """그래프 체크포인터 — USE_MOCK/테스트는 MemorySaver, 실연동은 AsyncPostgresSaver.

    AsyncPostgresSaver는 풀 정리가 필요하므로 (saver, close)를 반환한다.
    """
    if getattr(s, "use_mock", True):
        from langgraph.checkpoint.memory import MemorySaver

        async def _noop() -> None:
            return None

        return MemorySaver(), _noop

    from domain.chat.checkpointer import build_async_checkpointer

    return await build_async_checkpointer(s.database_url)
```

- [ ] **Step 5: 테스트 통과 확인**

Run(hermetic 먼저): `cd backend && uv run pytest tests/chat/test_checkpointer.py::test_to_psycopg_conninfo_strips_asyncpg -v`
Expected: PASS

Run(게이트): `cd backend && CHAT_TEST_DB_URL="<개인DB DSN>" uv run pytest tests/chat/test_checkpointer.py -v`
Expected: PASS (2 passed). `checkpoints*` 테이블이 setup으로 생성/확인되고 put/get 왕복 성공.

- [ ] **Step 6: setup 멱등 확인**

같은 명령 1회 더 실행 → 여전히 PASS(테이블 이미 존재해도 `.setup()`이 멱등).

- [ ] **Step 7: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/chat/checkpointer.py backend/domain/chat/wiring.py backend/tests/chat/test_checkpointer.py
git commit -m "add: AsyncPostgresSaver 체크포인터 — checkpoints* setup·roundtrip + URL 변환"
```

---

### Task 9: 파리티 정합 + 기반 종합 검증

**Files:**
- Modify: `backend/tests/test_orm_db_parity.py:7` (chat 모델 import 추가)
- Test: 전체 hermetic 스위트 + 파리티(개인 DB)

- [ ] **Step 1: 파리티 테스트에 chat 모델 등록**

`backend/tests/test_orm_db_parity.py`의 import 블록(라인 7-9 부근)에 추가.

```python
import core.models  # noqa: F401  매핑 등록
import domain.chat.models  # noqa: F401  챗 ORM 등록(chat_sessions·messages·ltm·brand)
from core.db import Base
from domain.simulation.models import SimBase  # 시뮬은 별도 metadata(SimBase)
```

- [ ] **Step 2: 파리티 실행(개인 DB)**

Run: `cd backend && PARITY_DB_URL="<개인DB psycopg2 DSN>" uv run pytest tests/test_orm_db_parity.py -v`
Expected: PASS — chat_sessions·chat_messages·chat_long_term_memory·chat_brand_profiles·management_kb_chunks 모든 ORM 컬럼이 DB에 존재(드리프트 0).

> 실패 시 출력의 `테이블.컬럼 (ORM엔 있으나 DB에 없음)`을 읽고 마이그레이션 026(Task 3)에 누락된 ALTER를 보강 → 026 재적용 → 재실행.

- [ ] **Step 3: 전체 hermetic 스위트**

Run: `cd backend && uv run pytest tests/chat -v`
Expected: hermetic 테스트 전부 PASS, Postgres 게이트 테스트는 SKIPPED(CHAT_TEST_DB_URL 미설정 시). 게이트까지 보려면 `CHAT_TEST_DB_URL`·`PARITY_DB_URL` 주입.

- [ ] **Step 4: 회귀 — 기존 스위트 깨짐 없는지**

Run: `cd backend && uv run pytest tests -q -x -k "not slow"`
Expected: 기존 통과 테스트 유지(특히 management assistant/kb 회귀). 깨지면 Task 5 호출부 영향 — 수정 후 재실행.

- [ ] **Step 5: alembic 상태 최종 확인**

Run: `cd backend && uv run alembic current && uv run alembic heads`
Expected: `current = 026`, `heads = 026` (단일 head).

- [ ] **Step 6: Ruff 전체 + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check .
git add backend/tests/test_orm_db_parity.py
git commit -m "edit: 파리티 테스트에 챗 ORM 등록 — Phase ③-A 기반 정합 완료"
```

---

## 완료 기준 (Phase ③-A)

- [ ] alembic `current=heads=026`, 개인 DB에 챗 스키마 수렴 적용(messages 제거·세션 메타·route·LTM 임베딩 1024·KB 1024).
- [ ] `test_orm_db_parity.py`가 챗 4테이블 포함 드리프트 0으로 통과(PARITY_DB_URL).
- [ ] `EmbeddingProvider` 포트 + Mock·TEI(BGE-M3)·OpenAI 어댑터, KB·LTM 동일 1024 차원 공유.
- [ ] `PgChatRepo`·`PgMemoryStore`·`AsyncPostgresSaver` 체크포인터 동작(Postgres 게이트 통과).
- [ ] `domain/chat/wiring.py`가 임베딩·repo·memory·checkpointer 빌더 제공(3B 그래프가 주입받을 준비 완료).
- [ ] hermetic 스위트 CI 그린, 기존 스위트 회귀 없음.

## Phase ③-B 인계 (다음 계획)

3A 완료 후 `superpowers:writing-plans`로 **3B 오케스트레이터** 계획 작성. 3A가 제공하는 것 위에 올린다.
- `domain/chat/contracts`에 `SubAgent`·`ChatTurnRequest`·`ChatEvent`·`SubAgentResult` 추가, 서브에이전트 어댑터 3종(management `build_management_agent` 래핑, simulation `build_simulation_service`, generator `generator_service`/D1).
- 슈퍼바이저 LangGraph(`graph/`): load_context(3A memory_store·brand) → supervisor(Sonnet 4.6 tool-calling) → delegate → interrupt(3A checkpointer) → execute(매니지먼트 approval→executor) → synthesize(CLIO, 3A chat_repo 영속).
- `ChatOrchestratorService`(SSE 지휘) + LLM 팩토리(`chat_orchestrator_model`).
- **미해결(3B에서 결정)** — 시뮬 트리거 동기/비동기 정책(spec §12), `chat_brand_profiles` vs `brand_profiles` 통합, 라우팅 평가 하니스, `management_chat_*` 흡수·정리.

## 자체 리뷰 메모 (작성자 점검)

- **스펙 커버리지** — §6.2 스키마 수렴(Task 3), §9 임베딩 BGE-M3 1024 포트(Task 4·5), §6.1 LTM 3계층 중 롱텀 적재·회상(Task 7), §6.2 checkpoints* AsyncPostgresSaver(Task 8). §11 Phase ③의 "기반" 부분 전부 매핑. 그래프·서브에이전트·SSE·프론트는 의도적으로 3B/3C로 분리.
- **타입 일관성** — `EmbeddingProvider.embed(list[str])->list[list[float]]` 전 어댑터·repo·store 동일. `SessionDTO`/`MessageDTO`/`MemoryItem`/`MemoryHit` 정의(schemas.py)와 사용처(pg_chat_repo·pg_memory_store) 일치. `build_checkpointer`는 `(saver, close)` 튜플로 통일(MemorySaver 경로도 noop close 반환).
- **교차팀** — Task 3·5가 `management_kb_chunks`/매니지먼트 파일 수정(임베딩 1024). 개인 DB 한정·사전 공지 전제.
- **게이트 근거** — JSONB·pgvector·AsyncPostgresSaver는 SQLite 불가 → Postgres 게이트(CHAT_TEST_DB_URL). 핸드오프의 "sqlite" 메모와 의도적 차이, 사유 명시.
