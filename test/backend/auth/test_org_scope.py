# org 스코프 공용 헬퍼(resolve_read_scope·require_write_org) 단위 검증 — DB·네트워크 없이.
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core import auth as auth_mod
from core.auth import require_write_org, resolve_read_scope


class _FakeDB:
    """user_org_id의 scalar(select(...)) 흉내 — 지정한 org_id를 반환."""

    def __init__(self, org_id):
        self._org_id = org_id

    async def scalar(self, _stmt):
        return self._org_id


def _user(role: str):
    return SimpleNamespace(id="u1", role=role, status="ACTIVE")


@pytest.fixture(autouse=True)
def _reset_selected_org():
    # 각 테스트가 ContextVar를 명시 세팅. 끝나면 None으로 원복.
    token = auth_mod._selected_org.set(None)
    yield
    auth_mod._selected_org.reset(token)


# ── 읽기 스코프 ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_read_admin_no_selection_is_all():
    auth_mod._selected_org.set(None)
    scope = await resolve_read_scope(_user("ADMIN"), _FakeDB(None))
    assert scope.all_orgs is True
    assert scope.org_id is None
    assert scope.empty is False  # admin 전체는 빈 결과 아님


@pytest.mark.asyncio
async def test_read_admin_with_selection_scopes_to_it():
    oid = "11111111-1111-1111-1111-111111111111"
    auth_mod._selected_org.set(oid)
    scope = await resolve_read_scope(_user("ADMIN"), _FakeDB(None))
    assert scope.all_orgs is False
    assert str(scope.org_id) == oid


@pytest.mark.asyncio
async def test_read_company_uses_own_org():
    own = "22222222-2222-2222-2222-222222222222"
    scope = await resolve_read_scope(_user("COMPANY"), _FakeDB(own))
    assert scope.all_orgs is False
    assert str(scope.org_id) == own
    assert scope.empty is False


@pytest.mark.asyncio
async def test_read_user_without_org_is_empty():
    scope = await resolve_read_scope(_user("USER"), _FakeDB(None))
    assert scope.all_orgs is False
    assert scope.org_id is None
    assert scope.empty is True  # 무소속 비-admin → 빈 결과


# ── 쓰기 스코프 ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_write_admin_requires_selection():
    auth_mod._selected_org.set(None)
    with pytest.raises(HTTPException) as ei:
        await require_write_org(_user("ADMIN"), _FakeDB(None))
    assert ei.value.status_code == 400


@pytest.mark.asyncio
async def test_write_admin_with_selection_ok():
    oid = "33333333-3333-3333-3333-333333333333"
    auth_mod._selected_org.set(oid)
    org = await require_write_org(_user("ADMIN"), _FakeDB(None))
    assert str(org) == oid


@pytest.mark.asyncio
async def test_write_company_uses_own_org():
    own = "44444444-4444-4444-4444-444444444444"
    org = await require_write_org(_user("COMPANY"), _FakeDB(own))
    assert str(org) == own


@pytest.mark.asyncio
async def test_write_user_without_org_409():
    with pytest.raises(HTTPException) as ei:
        await require_write_org(_user("USER"), _FakeDB(None))
    assert ei.value.status_code == 409


@pytest.mark.asyncio
async def test_read_admin_bad_xorgid_400():
    auth_mod._selected_org.set("not-a-uuid")
    with pytest.raises(HTTPException) as ei:
        await resolve_read_scope(_user("ADMIN"), _FakeDB(None))
    assert ei.value.status_code == 400
