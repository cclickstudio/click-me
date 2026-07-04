# Task 3: 캠페인→프로젝트 resolver — `remediation/resolver.py`

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-02-anomaly-remediation-advisor.md` · 스펙: `docs/superpowers/specs/2026-07-02-anomaly-remediation-advisor-design.md`
> **실행 규칙**: 모든 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 .py 첫 줄 한국어 헤더 주석 · 🅰 소유 파일(detection/, approval.py, agents/diagnosis*) 수정 금지(읽기만).
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.

---

**Files:**
- Create: `backend/domain/management/remediation/resolver.py`
- Test: `test/backend/management/test_remediation_resolver.py`

스펙 §7 체인 1(AdCampaignLog 역추적)만 구현. 체인 2(생성 제안 링크)는 실행된 Meta
campaign_id ↔ proposal 연계 저장 위치가 미확인이라 **후속 PR**(§7-2 열린 결정) — resolver를
순서 리스트 구조로 만들어 꽂을 자리를 남긴다. 실패는 None(호출자가 skip).

- [ ] **Step 1: 실패하는 테스트 작성**

`test/backend/management/test_remediation_resolver.py`:
```python
# resolver 테스트 — AdCampaignLog 역추적(raw SQL, SQLite 검증)·org 불일치 fail-closed·실패 None
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from domain.management.remediation.resolver import resolve_project


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # resolver의 raw SQL이 쓰는 세 테이블만 최소 DDL로 생성
        await conn.execute(
            text(
                "CREATE TABLE projects ("
                "id TEXT PRIMARY KEY, organization_id TEXT, deleted_at TEXT)"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE ad_generations ("
                "id TEXT PRIMARY KEY, project_id TEXT, deleted_at TEXT)"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE ad_campaign_logs ("
                "id TEXT PRIMARY KEY, generation_id TEXT, campaign_id TEXT, "
                "created_at TEXT DEFAULT '2026-07-02T00:00:00')"
            )
        )
        await conn.execute(text("INSERT INTO projects VALUES ('proj-77', 'org-9', NULL)"))
        await conn.execute(
            text("INSERT INTO ad_generations VALUES ('gen-1', 'proj-77', NULL)")
        )
        # soft-delete된 generation은 역추적에서 제외돼야 한다(실 DB에 deleted_at 존재)
        await conn.execute(
            text("INSERT INTO ad_generations VALUES ('gen-del', 'proj-88', '2026-07-01')")
        )
        await conn.execute(text("INSERT INTO projects VALUES ('proj-88', 'org-9', NULL)"))
        await conn.execute(
            text(
                "INSERT INTO ad_campaign_logs (id, generation_id, campaign_id) "
                "VALUES ('log-1', 'gen-1', 'camp_meta_123')"
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_resolves_project_and_org_via_ad_campaign_log(session_factory):
    resolved = await resolve_project("camp_meta_123", session_factory=session_factory)
    assert resolved == ("proj-77", "org-9")


@pytest.mark.asyncio
async def test_fail_closed_on_org_mismatch(session_factory):
    # 기대 org와 다르면 매핑 폐기(None) — 오배정=기밀 노출이므로 fail-closed
    resolved = await resolve_project(
        "camp_meta_123", expected_org_id="org-other", session_factory=session_factory
    )
    assert resolved is None


@pytest.mark.asyncio
async def test_passes_when_expected_org_matches(session_factory):
    resolved = await resolve_project(
        "camp_meta_123", expected_org_id="org-9", session_factory=session_factory
    )
    assert resolved == ("proj-77", "org-9")


@pytest.mark.asyncio
async def test_soft_deleted_generation_is_ignored(session_factory):
    # deleted_at이 찍힌 generation만 연결된 캠페인 → 매핑 없음(None)
    async with session_factory() as db:
        from sqlalchemy import text as _text

        await db.execute(
            _text(
                "INSERT INTO ad_campaign_logs (id, generation_id, campaign_id) "
                "VALUES ('log-2', 'gen-del', 'camp_deleted_gen')"
            )
        )
        await db.commit()
    assert await resolve_project("camp_deleted_gen", session_factory=session_factory) is None


@pytest.mark.asyncio
async def test_returns_none_when_no_link(session_factory):
    assert await resolve_project("unknown_camp", session_factory=session_factory) is None


@pytest.mark.asyncio
async def test_returns_none_on_db_failure():
    def broken_factory():
        raise RuntimeError("db down")

    assert await resolve_project("camp_meta_123", session_factory=broken_factory) is None
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_remediation_resolver.py -v`
Expected: FAIL — `ModuleNotFoundError: domain.management.remediation.resolver`

- [ ] **Step 3: 구현**

`backend/domain/management/remediation/resolver.py`:
```python
# 캠페인→프로젝트 역추적 — 오배정=기밀 노출이므로 결정론 체인 + org fail-closed (🅱)
"""스펙 §7. 체인 1: AdCampaignLog(campaign_id) → generation → project(+org).
- expected_org_id가 주어지면 불일치 시 None(fail-closed). 스케줄러 tenant="global"이면 미검증.
- 반환 (project_id, organization_id) — 해석된 org는 consult meta의 org_id 정본이 된다.
체인 2(생성 제안 링크)는 campaign_id↔proposal 연계 저장 확인 후 후속 — _CHAIN에 추가.
타 도메인 테이블 raw SQL 읽기는 SimPredictionReader 선례와 동일 성격(읽기 전용).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

# 주의: ad_generations.deleted_at은 실 DB에는 있으나 ORM(core/models.py)에는 없는
# 드리프트 컬럼(2026-07-02 information_schema 확인) — soft-delete 제외는 raw SQL이라 가능.
_VIA_CAMPAIGN_LOG = text(
    """
    SELECT g.project_id, p.organization_id
    FROM ad_campaign_logs l
    JOIN ad_generations g ON g.id = l.generation_id
    JOIN projects p ON p.id = g.project_id
    WHERE l.campaign_id = :cid
      AND g.project_id IS NOT NULL
      AND g.deleted_at IS NULL
      AND p.deleted_at IS NULL
    ORDER BY l.created_at DESC
    LIMIT 1
    """
)


async def _via_campaign_log(
    campaign_id: str, session_factory: Any
) -> tuple[str, str] | None:
    async with session_factory() as db:
        row = (await db.execute(_VIA_CAMPAIGN_LOG, {"cid": campaign_id})).first()
        if row is None:
            return None
        return str(row[0]), str(row[1])


#: 순서 리스트 — 체인 2(생성 제안 링크)는 연계 확인 후 여기 추가한다.
_CHAIN = (_via_campaign_log,)


async def resolve_project(
    campaign_id: str, *, expected_org_id: str | None = None, session_factory: Any = None
) -> tuple[str, str] | None:
    """체인 순서대로 시도 → (project_id, org_id). org 불일치·전부 실패면 None(예외 안 나감)."""
    if session_factory is None:
        from core.db import AsyncSessionLocal  # noqa: PLC0415 — 테스트 주입 지원

        session_factory = AsyncSessionLocal
    for step in _CHAIN:
        try:
            resolved = await step(campaign_id, session_factory)
        except Exception:  # noqa: BLE001 — 역추적 실패는 다음 체인/skip
            continue
        if resolved is None:
            continue
        if expected_org_id is not None and resolved[1] != expected_org_id:
            return None  # fail-closed — 다른 org의 프로젝트로는 절대 배달하지 않는다
        return resolved
    return None
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_remediation_resolver.py -v`
Expected: PASS (6 tests). `aiosqlite` 미설치로 에러 나면 dev 의존성 확인:
`uv run python -c "import aiosqlite"` — 없으면 기존 테스트가 SQLite를 어떻게 쓰는지
`grep -r "aiosqlite" ../test/backend` 확인 후 동일 방식 사용(없으면 `uv add --dev aiosqlite`).

- [ ] **Step 5: 커밋**

```bash
git add backend/domain/management/remediation/resolver.py test/backend/management/test_remediation_resolver.py
git commit -m "add: 캠페인-프로젝트 역추적 resolver(AdCampaignLog 체인, org fail-closed)"
```
