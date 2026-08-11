import uuid
from types import SimpleNamespace

import pytest

from api.routers import center
from domain.chat import history


class _Rows:
    def all(self):
        return []


class _Db:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _Rows()


@pytest.mark.asyncio
async def test_user_session_query_is_limited_to_accessible_projects():
    db = _Db()
    await history.list_sessions_for_org(
        db,
        uuid.uuid4(),
        user_id=uuid.uuid4(),
        team_id=uuid.uuid4(),
        restrict_user_projects=True,
    )

    sql = str(db.statement)
    assert "projects.organization_id" in sql
    assert "projects.team_id" in sql
    assert "projects.created_by" in sql


@pytest.mark.asyncio
async def test_center_passes_user_scope_to_history(monkeypatch):
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    captured = {}

    async def _resolve_org(user, db, x_org_id):
        return org_id

    async def _list(db, org, project_id=None, **kwargs):
        captured.update(org=org, project_id=project_id, **kwargs)
        return []

    monkeypatch.setattr(center, "_resolve_org", _resolve_org)
    monkeypatch.setattr(history, "list_sessions_for_org", _list)

    user = SimpleNamespace(id=user_id, team_id=team_id, role="USER")
    result = await center.center_sessions(user=user, db=object())

    assert result == {"sessions": [], "org_selected": True}
    assert captured == {
        "org": org_id,
        "project_id": None,
        "user_id": user_id,
        "team_id": team_id,
        "restrict_user_projects": True,
    }


@pytest.mark.asyncio
async def test_center_does_not_restrict_company_to_one_team(monkeypatch):
    org_id = uuid.uuid4()
    captured = {}

    async def _resolve_org(user, db, x_org_id):
        return org_id

    async def _list(db, org, project_id=None, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(center, "_resolve_org", _resolve_org)
    monkeypatch.setattr(history, "list_sessions_for_org", _list)

    user = SimpleNamespace(id=uuid.uuid4(), team_id=None, role="COMPANY")
    await center.center_sessions(user=user, db=object())

    assert captured["restrict_user_projects"] is False


@pytest.mark.asyncio
async def test_center_checks_access_when_project_is_explicit(monkeypatch):
    org_id = uuid.uuid4()
    project_id = str(uuid.uuid4())
    checked = []

    async def _resolve_org(user, db, x_org_id):
        return org_id

    async def _assert_access(db, pid, user):
        checked.append(pid)

    async def _list(db, org, project_id=None, **kwargs):
        return []

    monkeypatch.setattr(center, "_resolve_org", _resolve_org)
    monkeypatch.setattr(center, "assert_project_access", _assert_access)
    monkeypatch.setattr(history, "list_sessions_for_org", _list)

    user = SimpleNamespace(id=uuid.uuid4(), team_id=uuid.uuid4(), role="USER")
    await center.center_sessions(project_id=project_id, user=user, db=object())

    assert checked == [project_id]
