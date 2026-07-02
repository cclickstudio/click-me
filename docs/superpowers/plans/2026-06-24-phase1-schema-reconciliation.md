# Phase ① 기반 정합 (스키마 드리프트 해소) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 레포의 Alembic·ORM을 실 DB(개인 복제본, 스탬프 `024`)와 정합시켜, 레포가 챗 오케스트레이터 테이블을 공식 인지하고 ORM↔DB가 맞는 깨끗한 베이스라인(head `024`)을 확보한다.

**Architecture (스탬프 기반 — 2026-06-24 조정):** 레포 마이그레이션 체인은 빈 DB에서 자립 실행 불가다(004가 미생성 `personas`를 ALTER — 시뮬 `SimBase` 테이블이 alembic 밖에서 관리됨). 따라서 **풀-리플레이 대신 라이브 스키마를 정본**으로 삼는다. "레포가 모르는"(마이그레이션 CREATE·ORM 어디에도 없는) **live-only 테이블**을 pg_dump로 추출해 **멱등(IF NOT EXISTS) 마이그레이션 1개(revision `024`, down_revision `021`)**로 공식화한다. revision id가 `024`라 이미 024로 스탬프된 실/개인 DB는 head와 자동 일치(no-op). 검증은 빈 스크래치 빌드 없이 **개인 DB에 멱등 적용(no-op 안전성)** + **완전성 대조**로 한다. 이어 ORM 드리프트(`ads`/`projects`/`simulations`)를 수정하고, 역드리프트(`regeneration_jobs` 누락)를 개인 DB에 보정한다.

**Tech Stack:** Alembic(raw SQL, `target_metadata=None`), SQLAlchemy 2.x async, psycopg2, pg_dump 18(conda env `pgtools`), pgvector.

**전제 경로 (이 세션 환경)**
- uv: `C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe` (backend 디렉터리에서 실행)
- pg_dump/psql 18: `C:\Users\804\miniforge3\envs\pgtools\Library\bin`
- 개인 DB direct: `postgresql://neondb_owner:npg_uf8isdUoab4A@ep-solitary-block-aoo1kl14.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require` (pg_dump/psql용, `-pooler` 제거)
- PowerShell은 `Set-Location C:\Users\804\Documents\main_project\chat\click-me\backend` 후 실행(uv가 프로젝트 venv를 잡도록).

**범위 밖**
- Phase ② 정리 DROP, Phase ③ 오케스트레이터 스키마 변경(route/summary/embedding 등).
- **공용(공유) DB 정합** — 본 계획은 레포 + 개인 DB만.
- **alembic 풀-리플레이 자립성 수리** — 시뮬 `SimBase` 테이블(`personas`·`panels`·`ad_analyses`·`rubric_scores`·`simulation_aggregates`)이 마이그레이션에 없어 빈 DB 빌드가 004에서 깨진다. **시뮬 도메인 소유의 별도 부채**로 분리(아래 리스크).

---

## File Structure

- `backend/scripts/_recon_liveonly.py` (Create, 임시) — live 테이블에서 "레포 인지(마이그레이션 CREATE ∪ ORM)" 집합을 빼 live-only·역드리프트 산출. 작업 후 삭제.
- `backend/alembic/versions/024_chat_orchestrator_baseline.py` (Create) — live-only 테이블 멱등 생성 정합 마이그레이션.
- `backend/core/models.py` (Modify) — `Ad`(드리프트 수정), `Project`(컬럼 추가).
- `backend/domain/simulation/models.py` (Modify) — `Simulation`에 `deleted_at` 추가.
- `backend/tests/test_orm_db_parity.py` (Create) — ORM 컬럼 ⊆ 실 DB 컬럼 검증(`PARITY_DB_URL` 게이트).

---

## Task 1: 도구·접속 확인 ✅ (완료)

pg_dump 18.4 / alembic head 021 / 개인 DB 스탬프 024 / Docker는 데몬 미실행(스탬프 기반이라 불요) 확인됨.

---

## Task 2: live-only 집합·역드리프트 확정

**Files:** Create `backend/scripts/_recon_liveonly.py`

- [ ] **Step 1: 산출 스크립트 작성**

`backend/scripts/_recon_liveonly.py`:
```python
# 임시 — live 테이블에서 레포 인지(마이그레이션 CREATE ∪ ORM __tablename__) 집합을 빼 live-only 산출
import glob
import os
import re

import psycopg2

from core.db import Base
import core.models  # noqa: F401
from domain.simulation.models import SimBase  # noqa: F401

known = set(Base.metadata.tables) | set(SimBase.metadata.tables)
for f in glob.glob("alembic/versions/*.py"):
    txt = open(f, encoding="utf-8").read()
    for m in re.finditer(r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?([a-z_]+)", txt, re.I):
        known.add(m.group(1))

c = psycopg2.connect(os.environ["LIVE_DB"])
cur = c.cursor()
cur.execute(
    "select table_name from information_schema.tables "
    "where table_schema='public' and table_type='BASE TABLE'"
)
live = {r[0] for r in cur.fetchall()}
cur.close()
c.close()

print("=== LIVE-ONLY (레포가 모르는 → 024가 공식화) ===")
for t in sorted(live - known):
    print(" +", t)
print("\n=== REPO-KNOWN but NOT in live (역드리프트 → 개인 DB 보정) ===")
for t in sorted(known - live):
    print(" -", t)
```

- [ ] **Step 2: 실행**

```powershell
Set-Location "C:\Users\804\Documents\main_project\chat\click-me\backend"
$env:LIVE_DB="postgresql://neondb_owner:npg_uf8isdUoab4A@ep-solitary-block-aoo1kl14.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
& "C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe" run python scripts/_recon_liveonly.py
```
Expected: LIVE-ONLY에 `chat_long_term_memory`·`chat_brand_profiles`·`management_chat_sessions`·`management_chat_messages`·`management_agent_runs`·`management_kb_documents`·`management_kb_eval_cases`·`management_kb_feedback`·`checkpoints`·`checkpoint_blobs`·`checkpoint_writes`·`checkpoint_migrations`·`simulation_kb_chunks` 등. REPO-KNOWN-not-live에 `regeneration_jobs`. (`chat_sessions`/`chat_messages`는 001에서 만들어 known일 수 있음 — 그럼 live-only 아님.)

- [ ] **Step 3: 출력 저장**

LIVE-ONLY 목록을 메모 — Task 3(pg_dump 대상)·Task 5(완전성 대조)의 기준이다.

---

## Task 3: live-only 테이블 DDL 추출

**Files:** 없음(DDL 산출물)

- [ ] **Step 1: live-only 테이블 schema-only 덤프**

Task 2의 LIVE-ONLY 목록을 `-t public.<table>`로 나열(아래는 예시 — 실제 목록으로 대체):
```powershell
$bin="C:\Users\804\miniforge3\envs\pgtools\Library\bin"
$live="postgresql://neondb_owner:npg_uf8isdUoab4A@ep-solitary-block-aoo1kl14.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
& "$bin\pg_dump.exe" --schema-only --no-owner --no-acl `
  -t public.chat_long_term_memory -t public.chat_brand_profiles `
  -t public.management_chat_sessions -t public.management_chat_messages -t public.management_agent_runs `
  -t public.management_kb_documents -t public.management_kb_eval_cases -t public.management_kb_feedback `
  -t public.checkpoints -t public.checkpoint_blobs -t public.checkpoint_writes -t public.checkpoint_migrations `
  -t public.simulation_kb_chunks `
  $live -f "C:\Users\804\AppData\Local\Temp\clickme_liveonly_ddl.sql"
Get-Content "C:\Users\804\AppData\Local\Temp\clickme_liveonly_ddl.sql"
```
Expected: 각 테이블 `CREATE TABLE`·인덱스·제약·필요 enum(예: `chat_role`) DDL 포함. **반드시 Task 2 목록과 정확히 일치**시킬 것.

- [ ] **Step 2: 멱등 변환 규칙**

`CREATE TABLE x` → `CREATE TABLE IF NOT EXISTS x`. `CREATE INDEX y` → `CREATE INDEX IF NOT EXISTS y`. `CREATE TYPE t AS ENUM (...)` → `DO $$ BEGIN CREATE TYPE t AS ENUM (...); EXCEPTION WHEN duplicate_object THEN null; END $$;`. `ALTER TABLE ... ADD CONSTRAINT`은 `DO $$ ... EXCEPTION WHEN duplicate_object THEN null; END $$;`로 감쌈. `vector` 컬럼 있으면 맨 앞 `CREATE EXTENSION IF NOT EXISTS vector;`. pg_dump의 `SET`/`SELECT pg_catalog.set_config(...)` 헤더 라인은 제거.

---

## Task 4: 정합 마이그레이션 `024` 작성

**Files:** Create `backend/alembic/versions/024_chat_orchestrator_baseline.py`

- [ ] **Step 1: 골격 작성**

```python
"""chat orchestrator baseline — repo(021)와 실 DB(024) 정합 (스탬프 기반)

레포에 없던 챗 오케스트레이터·체크포인터·KB live-only 테이블을 멱등 생성해
레포가 공식 인지하게 한다. 이미 024로 스탬프된 DB에는 no-op.

Revision ID: 024
Revises: 021
"""

from alembic import op

revision = "024"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute(
        r"""
        -- ↓↓↓ Task 3에서 추출·멱등 변환한 live-only DDL 전체를 여기에 붙인다 ↓↓↓
        """
    )


def downgrade() -> None:
    op.execute(
        r"""
        -- DROP TABLE IF EXISTS <생성 테이블 역순>;  -- 운영 DB 사용 금지
        """
    )
```

- [ ] **Step 2: Task 3 멱등 DDL을 `upgrade()`에 채우고 `downgrade()`에 역순 DROP 작성**

- [ ] **Step 3: 단일 head 확인**

```powershell
Set-Location "C:\Users\804\Documents\main_project\chat\click-me\backend"
& "C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe" run alembic heads
```
Expected: `024 (head)` 단일. 멀티 head면 down_revision 수정.

---

## Task 5: 검증 — 개인 DB 멱등 적용 + 완전성

빈 스크래치 빌드는 불가(체인 부채 + 챗 테이블 FK→projects/users)하므로, **개인 DB(이미 024)에 멱등성으로 검증**한다.

**Files:** 없음(검증)

- [ ] **Step 1: 마이그레이션 upgrade SQL을 개인 DB에 직접 적용(멱등 no-op 확인)**

024 마이그레이션 `upgrade()`의 `op.execute` 본문 SQL을 파일로 저장 후 psql로 실행(개인 DB엔 이미 다 있어 IF NOT EXISTS → no-op, 에러 0이어야 함):
```powershell
$bin="C:\Users\804\miniforge3\envs\pgtools\Library\bin"
$live="postgresql://neondb_owner:npg_uf8isdUoab4A@ep-solitary-block-aoo1kl14.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
# 024의 upgrade SQL을 C:\Users\804\AppData\Local\Temp\mig024.sql 로 저장했다고 가정
& "$bin\psql.exe" $live -v ON_ERROR_STOP=1 -f "C:\Users\804\AppData\Local\Temp\mig024.sql"
```
Expected: 에러 없이 완료(모두 no-op). 에러가 나면 DDL 멱등 변환 누락 — Task 3 Step 2 보완.

- [ ] **Step 2: 완전성 대조**

Task 2 LIVE-ONLY 목록의 모든 테이블이 024 마이그레이션 SQL에 `CREATE TABLE IF NOT EXISTS`로 포함됐는지 1:1 확인. 누락 시 추가.

- [ ] **Step 3: alembic 상태 정합 확인**

```powershell
Set-Location "C:\Users\804\Documents\main_project\chat\click-me\backend"
$env:DATABASE_URL="postgresql+asyncpg://neondb_owner:npg_uf8isdUoab4A@ep-solitary-block-aoo1kl14.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
& "C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe" run alembic current
& "C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe" run alembic heads
```
Expected: current=`024`, heads=`024`. 둘이 같으면 개인 DB와 레포 head가 정합(업그레이드 불필요).

---

## Task 6: 역드리프트 보정 — `regeneration_jobs`

**Files:** 없음(개인 DB 데이터-픽스)

- [ ] **Step 1: 020 마이그레이션의 regeneration_jobs DDL 확인**

`backend/alembic/versions/020_add_regeneration_jobs.py`를 열어 `CREATE TABLE regeneration_jobs (...)` 컬럼 정의를 확인.

- [ ] **Step 2: 개인 DB에 멱등 생성**

```powershell
$bin="C:\Users\804\miniforge3\envs\pgtools\Library\bin"
$live="postgresql://neondb_owner:npg_uf8isdUoab4A@ep-solitary-block-aoo1kl14.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
& "$bin\psql.exe" $live -c "CREATE TABLE IF NOT EXISTS regeneration_jobs ( /* 020 파일 컬럼 정의 그대로 */ );"
```
Expected: `CREATE TABLE`(생성됨) 또는 이미 있으면 no-op.

- [ ] **Step 3: 재확인**

```powershell
$env:LIVE_DB="postgresql://neondb_owner:npg_uf8isdUoab4A@ep-solitary-block-aoo1kl14.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
& "C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe" run python scripts/_recon_liveonly.py
```
Expected: REPO-KNOWN-not-live 목록이 비거나 `regeneration_jobs`가 사라짐.

---

## Task 7: ORM 드리프트 수정 — `Ad` 모델

**Files:** Modify `backend/core/models.py` (`Ad`)

- [ ] **Step 1: 실 DB ads 컬럼 확인**

`docs/db-erd.md`의 `### \`ads\`` 섹션에서 컬럼·타입 확인.

- [ ] **Step 2: `Ad` 재작성(실 DB 정합)**

```python
class Ad(Base):
    __tablename__ = "ads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str | None] = mapped_column(String(20))
    asset_url: Mapped[str | None] = mapped_column(Text)
    copy_text: Mapped[str | None] = mapped_column(Text)
    industry_category: Mapped[str | None] = mapped_column(String(100))
    product_category: Mapped[str | None] = mapped_column(String(100))
    ad_objective: Mapped[str | None] = mapped_column(String(50))
    target_filter: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str | None] = mapped_column(String(20))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="ads")
```
제거: `ad_type`·`s3_key`·`analysis`(유령), `simulations` 관계(레거시). 타입은 db-erd.md와 다르면 맞춤.

- [ ] **Step 3: `SimulationResult.ad` 역관계 정리**

`Ad.simulations`를 지웠으므로 `SimulationResult`의 `ad` 관계에서 `back_populates`를 제거(단방향) 또는 관계 삭제해 매핑 에러 방지.

- [ ] **Step 4: 매핑 임포트 확인**

```powershell
Set-Location "C:\Users\804\Documents\main_project\chat\click-me\backend"
& "C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe" run python -c "import core.models; print('models import OK')"
```
Expected: `models import OK`.

---

## Task 8: ORM 드리프트 — soft delete 컬럼

**Files:** Modify `backend/core/models.py`(`Project`), `backend/domain/simulation/models.py`(`Simulation`)

- [ ] **Step 1: `Project`에 누락 컬럼 추가(db-erd.md `projects` 확인)**

```python
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(20), server_default="ACTIVE")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
```

- [ ] **Step 2: `Simulation`에 `deleted_at` 추가**

```python
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
```

- [ ] **Step 3: 임포트 확인**

```powershell
Set-Location "C:\Users\804\Documents\main_project\chat\click-me\backend"
& "C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe" run python -c "import core.models, domain.simulation.models; print('OK')"
```
Expected: `OK`.

---

## Task 9: ORM↔DB 패리티 테스트 + pytest

**Files:** Create `backend/tests/test_orm_db_parity.py`

- [ ] **Step 1: 패리티 테스트 작성**

```python
# ORM 선언 컬럼이 실 DB에 모두 존재하는지 검증(드리프트 회귀 방지). PARITY_DB_URL 있을 때만 실행.
import os

import psycopg2
import pytest

from core.db import Base
import core.models  # noqa: F401  매핑 등록
from domain.simulation.models import SimBase  # 시뮬은 별도 metadata(SimBase)

pytestmark = pytest.mark.skipif(
    not os.environ.get("PARITY_DB_URL"), reason="PARITY_DB_URL 미설정"
)


def _db_columns(url: str, table: str) -> set[str]:
    c = psycopg2.connect(url)
    cur = c.cursor()
    cur.execute(
        "select column_name from information_schema.columns "
        "where table_schema='public' and table_name=%s",
        (table,),
    )
    cols = {r[0] for r in cur.fetchall()}
    cur.close()
    c.close()
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
```

- [ ] **Step 2: 패리티 테스트 실행(개인 DB)**

```powershell
Set-Location "C:\Users\804\Documents\main_project\chat\click-me\backend"
$env:PARITY_DB_URL="postgresql://neondb_owner:npg_uf8isdUoab4A@ep-solitary-block-aoo1kl14.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
& "C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe" run pytest tests/test_orm_db_parity.py -v
```
Expected: PASS. 실패하면 메시지 컬럼을 Task 7/8에 반영(또는 실 DB에 없으면 ORM에서 제거).

- [ ] **Step 3: 기존 스위트 회귀 확인**

```powershell
& "C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe" run pytest tests/ -q
```
Expected: GREEN(또는 변경 전과 동일). `Ad` 변경으로 깨지는 곳(`s3_key`/`analysis`/`ad_type` 참조)은 실 컬럼명으로 수정.

---

## Task 10: Ruff·커밋

**Files:** 없음

- [ ] **Step 1: 임시 스크립트 삭제**

```powershell
Remove-Item "C:\Users\804\Documents\main_project\chat\click-me\backend\scripts\_recon_liveonly.py" -Force
```

- [ ] **Step 2: Ruff (백엔드 .py 변경 — CLAUDE.md 규칙)**

```powershell
Set-Location "C:\Users\804\Documents\main_project\chat\click-me\backend"
& "C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe" run ruff format .
& "C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe" run ruff check . --fix
```
Expected: 통과.

- [ ] **Step 3: 커밋**

```bash
git add backend/alembic/versions/024_chat_orchestrator_baseline.py backend/core/models.py backend/domain/simulation/models.py backend/tests/test_orm_db_parity.py
git commit -m $'add: Phase ① 스탬프 기반 정합 — 챗 베이스라인 마이그레이션 + ORM 드리프트 수정\n\n- alembic 024(멱등): live-only 챗/체크포인터/KB 테이블 공식화, head=024 정합\n- Ad ORM 실 DB 정합(ad_type/s3_key/analysis 제거, media_type 등 추가)\n- projects/simulations deleted_at 등 추가, regeneration_jobs 개인 DB 보정\n- ORM↔DB 패리티 테스트(PARITY_DB_URL 게이트)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>'
```
Expected: 커밋 생성(브랜치 `feat/chat-yeotaeho`).

---

## 완료 기준 (Definition of Done)

- `_recon_liveonly.py`의 LIVE-ONLY 전부가 024 마이그레이션에 포함, 개인 DB에 멱등 적용 시 에러 0.
- `alembic current`=`heads`=`024` (개인 DB ↔ 레포 head 정합).
- 개인 DB에 `regeneration_jobs` 보정 완료(역드리프트 해소).
- `test_orm_db_parity.py` 개인 DB 대상 PASS, 기존 pytest 스위트 GREEN.

## 리스크 / 주의

- **alembic 풀-리플레이 불가(선재 부채)** — 시뮬 `SimBase` 테이블이 마이그레이션에 없어 빈 DB `alembic upgrade`가 004에서 깨진다. CI/신규배포에 영향(단 현재 CI는 `dev`/`feat`에서 미작동이라 잠복). **시뮬 도메인 소유의 별도 과제**로 분리 — 본 정합 범위 밖.
- **공용(공유) DB 정합 범위 밖** — 동일 절차 필요할 수 있으나 팀 합의 후 별도.
- **`ads` 변경 파급** — `s3_key`/`analysis`/`ad_type` 참조 코드가 있으면 깨짐. Task 9 Step 3에서 전수 확인·수정.
- **멱등성** — 024의 모든 DDL은 IF NOT EXISTS/예외 가드여야 개인·공유 DB에 안전.
