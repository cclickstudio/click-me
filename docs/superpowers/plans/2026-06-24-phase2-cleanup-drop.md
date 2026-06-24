# Phase ② 정리 DROP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox(`- [ ]`).

**Goal:** db-cleanup.md에서 확정한 미사용·레거시 테이블 **19개**를 개인 DB와 레포에서 제거하고, 이를 참조하던 코드(purge 로직·쿼리·ORM)를 함께 정리한다.

**Architecture:** down_revision=024인 멱등 마이그레이션 `025`로 `DROP TABLE IF EXISTS ... CASCADE`. 개인 DB(스탬프 024)에 `alembic upgrade head`로 적용해 스탬프 025. 코드 참조(projects.py purge·상세쿼리, admin.py purge, ORM `SimulationResult`/`AdEmbedding`)를 같은 커밋에서 제거. refresh_tokens·brand_kits(저확신)와 챗 관련(management_chat_*/agent_runs→Phase ③ 수렴)은 **제외**.

**Tech Stack:** Alembic, psycopg2, pg_dump/psql 18(pgtools), uv.

**전제 경로:** uv=`C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe`, psql=`C:\Users\804\miniforge3\envs\pgtools\Library\bin\psql.exe`, 개인 DB direct=`postgresql://neondb_owner:npg_uf8isdUoab4A@ep-solitary-block-aoo1kl14.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require`. PowerShell은 backend로 Set-Location 후 실행.

**드롭 대상 19개**
- 그룹 A(코드 참조 없음, 12): generated_ads, ad_templates, generator_kb_chunks, rag_chunks, simulation_kb_chunks, persona_templates, project_members, user_settings, subscription_plans, benchmarks, calibration_data, audit_logs
- 그룹 B(코드 참조 있음→수술, 7): simulation_comparisons, organization_subscriptions, recommendations, diagnoses, reports, simulation_results, ad_embeddings

---

## File Structure

- `backend/alembic/versions/025_drop_unused_tables.py` (Create) — 19개 DROP IF EXISTS CASCADE.
- `backend/api/routers/projects.py` (Modify) — `_purge_simulations`·`_purge_ads`·`_purge_project`에서 드롭 테이블 DELETE 제거, `get_simulation_detail` 쿼리에서 simulation_results JOIN 제거.
- `backend/api/routers/admin.py` (Modify) — simulation_comparisons·organization_subscriptions DELETE 제거.
- `backend/core/models.py` (Modify) — `SimulationResult`·`AdEmbedding` 클래스 제거.

---

## Task 1: 드롭 전 스냅샷

**Files:** 없음

- [ ] **Step 1: 19개 테이블 행수 기록(데이터 손실 확인)**

```powershell
$psql="C:\Users\804\miniforge3\envs\pgtools\Library\bin\psql.exe"
$live="postgresql://neondb_owner:npg_uf8isdUoab4A@ep-solitary-block-aoo1kl14.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
$tabs="generated_ads ad_templates generator_kb_chunks rag_chunks simulation_kb_chunks persona_templates project_members user_settings subscription_plans benchmarks calibration_data audit_logs simulation_comparisons organization_subscriptions recommendations diagnoses reports simulation_results ad_embeddings".Split(" ")
foreach ($t in $tabs) { & $psql $live -t -c "select '$t', count(*) from $t;" }
```
Expected: 대부분 0행. 비어있지 않은 것(예: simulation_kb_chunks≈6)은 기록만 — 정리 대상이라 손실 허용. 0 아닌 게 많으면 멈추고 재검토.

---

## Task 2: projects.py 코드 수술

**Files:** Modify `backend/api/routers/projects.py`

- [ ] **Step 1: `_purge_simulations`에서 드롭 테이블 DELETE 제거**

다음 두 statement(`recommendations`+`diagnoses` 합본, `diagnoses` 단독, `reports`, `simulation_comparisons`)를 삭제. 아래 블록을
```python
        f"DELETE FROM persona_debates WHERE simulation_id IN ({sim_ids_sql})",
        f"DELETE FROM recommendations WHERE simulation_id IN ({sim_ids_sql}) "
        f"OR diagnosis_id IN (SELECT id FROM diagnoses WHERE simulation_id IN ({sim_ids_sql}))",
        f"DELETE FROM diagnoses WHERE simulation_id IN ({sim_ids_sql})",
        f"DELETE FROM persona_responses WHERE simulation_id IN ({sim_ids_sql})",
        f"DELETE FROM reports WHERE simulation_id IN ({sim_ids_sql})",
        f"DELETE FROM simulation_aggregates WHERE simulation_id IN ({sim_ids_sql})",
        f"DELETE FROM simulation_comparisons "
        f"WHERE simulation_a_id IN ({sim_ids_sql}) OR simulation_b_id IN ({sim_ids_sql})",
        f"DELETE FROM simulations WHERE id IN ({sim_ids_sql})",
```
다음으로 교체:
```python
        f"DELETE FROM persona_debates WHERE simulation_id IN ({sim_ids_sql})",
        f"DELETE FROM persona_responses WHERE simulation_id IN ({sim_ids_sql})",
        f"DELETE FROM simulation_aggregates WHERE simulation_id IN ({sim_ids_sql})",
        f"DELETE FROM simulations WHERE id IN ({sim_ids_sql})",
```

- [ ] **Step 2: `_purge_ads`에서 simulation_results·ad_embeddings DELETE 제거**

```python
    stmts = [
        f"DELETE FROM simulation_results WHERE ad_id IN ({ad_ids_sql})",
        f"DELETE FROM ad_embeddings WHERE ad_id IN ({ad_ids_sql})",
        f"DELETE FROM rubric_scores WHERE ad_analysis_id IN "
```
→
```python
    stmts = [
        f"DELETE FROM rubric_scores WHERE ad_analysis_id IN "
```

- [ ] **Step 3: `_purge_project`에서 simulation_comparisons DELETE 제거**

이 줄 삭제:
```python
    await db.execute(text("DELETE FROM simulation_comparisons WHERE project_id = :pid"), p)
```

- [ ] **Step 4: `get_simulation_detail` 쿼리에서 simulation_results JOIN 제거**

`text("""...""")` 안에서 `sr.distribution, sr.personas`(SELECT 끝부분)와 LEFT JOIN을 제거. 아래
```python
                   p.organization_id, p.team_id, p.created_by AS project_created_by,
                   sr.distribution, sr.personas
            FROM simulations s
            LEFT JOIN users u ON u.id = s.created_by
            JOIN ads a ON a.id = s.ad_id
            JOIN projects p ON p.id = a.project_id
            LEFT JOIN simulation_results sr ON sr.ad_id = s.ad_id
            WHERE s.id = :sim_id
```
→
```python
                   p.organization_id, p.team_id, p.created_by AS project_created_by
            FROM simulations s
            LEFT JOIN users u ON u.id = s.created_by
            JOIN ads a ON a.id = s.ad_id
            JOIN projects p ON p.id = a.project_id
            WHERE s.id = :sim_id
```

- [ ] **Step 5: 반환부 `r.distribution`/`r.personas` → None (legacy 항상 NULL이었음)**

```python
        "result": r.distribution,
        "persona_results": r.personas,
```
→
```python
        "result": None,
        "persona_results": None,
```

---

## Task 3: admin.py 코드 수술

**Files:** Modify `backend/api/routers/admin.py`

- [ ] **Step 1: simulation_comparisons·organization_subscriptions DELETE 제거**

이 두 줄 삭제:
```python
        text(f"DELETE FROM simulation_comparisons WHERE project_id IN ({proj_sub})"), p
```
```python
    await db.execute(text("DELETE FROM organization_subscriptions WHERE organization_id = :org"), p)
```
주의: 167행은 `await db.execute(\n    text(f"..."), p\n)` 형태일 수 있으니 해당 `await db.execute(...)` 호출 전체를 제거(괄호 짝 유지). 제거 후 인접 코드 문법 확인.

---

## Task 4: ORM 클래스 제거

**Files:** Modify `backend/core/models.py`

- [ ] **Step 1: `SimulationResult`·`AdEmbedding` 클래스 삭제**

`class SimulationResult(Base):` 전체 블록(약 153~163행)과 `class AdEmbedding(Base):` 전체 블록(약 166~? 행, `__tablename__ = "ad_embeddings"` 포함)을 삭제. (Ad.simulations 관계는 Phase ①에서 이미 제거됨.)

- [ ] **Step 2: 매핑 임포트 확인**

```powershell
Set-Location "C:\Users\804\Documents\main_project\chat\click-me\backend"
& "C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe" run python -c "import core.models; from sqlalchemy.orm import configure_mappers; configure_mappers(); print('OK')"
```
Expected: `OK`. NameError/매핑 에러면 다른 곳의 SimulationResult/AdEmbedding 참조 잔존 — grep로 제거.

---

## Task 5: 마이그레이션 025 작성·적용

**Files:** Create `backend/alembic/versions/025_drop_unused_tables.py`

- [ ] **Step 1: 마이그레이션 작성**

```python
"""drop unused/legacy tables — Phase ② 정리 (db-cleanup.md)

Revision ID: 025
Revises: 024
"""

from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None

_TABLES = [
    "generated_ads", "ad_templates", "generator_kb_chunks", "rag_chunks",
    "simulation_kb_chunks", "persona_templates", "project_members", "user_settings",
    "subscription_plans", "benchmarks", "calibration_data", "audit_logs",
    "simulation_comparisons", "organization_subscriptions", "recommendations",
    "diagnoses", "reports", "simulation_results", "ad_embeddings",
]


def upgrade() -> None:
    for t in _TABLES:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")


def downgrade() -> None:
    # 정리 마이그레이션 — 복원은 022~024 이력/백업 필요. no-op.
    pass
```

- [ ] **Step 2: 단일 head 확인**

```powershell
Set-Location "C:\Users\804\Documents\main_project\chat\click-me\backend"
& "C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe" run alembic heads
```
Expected: `025 (head)` 단일.

- [ ] **Step 3: 개인 DB에 적용**

```powershell
$env:DATABASE_URL="postgresql+asyncpg://neondb_owner:npg_uf8isdUoab4A@ep-solitary-block-aoo1kl14.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
& "C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe" run alembic upgrade head
& "C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe" run alembic current
```
Expected: `Running upgrade 024 -> 025`, current=`025`.

---

## Task 6: 검증

**Files:** 없음

- [ ] **Step 1: 드롭 확인**

```powershell
$psql="C:\Users\804\miniforge3\envs\pgtools\Library\bin\psql.exe"
$live="postgresql://neondb_owner:npg_uf8isdUoab4A@ep-solitary-block-aoo1kl14.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
& $psql $live -t -c "select count(*) from information_schema.tables where table_schema='public' and table_name in ('generated_ads','ad_templates','generator_kb_chunks','rag_chunks','simulation_kb_chunks','persona_templates','project_members','user_settings','subscription_plans','benchmarks','calibration_data','audit_logs','simulation_comparisons','organization_subscriptions','recommendations','diagnoses','reports','simulation_results','ad_embeddings');"
```
Expected: `0` (모두 삭제됨). 총 테이블 수는 70→51 예상(regeneration_jobs 보정으로 +1 했으니 실제 카운트는 별도 확인).

- [ ] **Step 2: 패리티 + 회귀 테스트**

```powershell
Set-Location "C:\Users\804\Documents\main_project\chat\click-me\backend"
$env:PARITY_DB_URL="postgresql://neondb_owner:npg_uf8isdUoab4A@ep-solitary-block-aoo1kl14.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
& "C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe" run pytest tests/test_orm_db_parity.py tests/test_projects.py tests/management -q
```
Expected: 패리티 PASS(ORM에서 SimulationResult/AdEmbedding 제거됐으니 드롭과 정합), projects/management 관련 GREEN. (projects 테스트 경로가 다르면 `tests/` 전체 또는 해당 파일로 조정.) `text_overlay`·`ssr_deterministic` 기존 환경/flaky 실패는 무시.

---

## Task 7: Ruff·커밋

- [ ] **Step 1: Ruff**

```powershell
Set-Location "C:\Users\804\Documents\main_project\chat\click-me\backend"
& "C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe" run ruff format alembic/versions/025_drop_unused_tables.py api/routers/projects.py api/routers/admin.py core/models.py
& "C:\Users\804\miniforge3\envs\aiproject\Scripts\uv.exe" run ruff check alembic/versions/025_drop_unused_tables.py api/routers/projects.py api/routers/admin.py core/models.py --fix
```
Expected: 통과.

- [ ] **Step 2: 커밋**

```bash
git add backend/alembic/versions/025_drop_unused_tables.py backend/api/routers/projects.py backend/api/routers/admin.py backend/core/models.py docs/superpowers/plans/2026-06-24-phase2-cleanup-drop.md
git commit -m $'delete: Phase ② 미사용 테이블 19개 정리 + 참조 코드 제거\n\n- alembic 025: 미사용/레거시 테이블 19개 DROP IF EXISTS CASCADE\n- projects.py/admin.py purge·상세쿼리에서 드롭 테이블 참조 제거\n- ORM SimulationResult/AdEmbedding 제거\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>'
```

---

## 완료 기준
- 19개 테이블 개인 DB에서 삭제, `alembic current=heads=025`.
- 패리티 PASS, projects/management 테스트 GREEN(기존 환경/flaky 실패 제외).
- projects.py/admin.py purge·상세쿼리에 드롭 테이블 참조 0, ORM에 SimulationResult/AdEmbedding 0.

## 리스크
- **파괴적** — 19개 테이블 삭제(개인 DB). 대부분 빈 테이블이나 simulation_kb_chunks 등 소량 데이터 손실 허용(정리 대상). 공유 DB 적용은 별도 합의.
- **CASCADE** — 드롭 후보는 leaf/child라 KEEP 테이블에 영향 없음(검증: cross-domain FK는 후보→KEEP 방향뿐). 그래도 Step 6-1로 잔존 0 확인.
- **refresh_tokens·brand_kits 제외** — 저확신(향후 필요 가능)이라 보류. 챗 관련은 Phase ③에서 처리.
