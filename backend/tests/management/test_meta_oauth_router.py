# Meta 연결 라우터 — /meta/connect가 JWT org로 Facebook 로그인 URL을 반환
import uuid
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import management
from core.auth import get_current_user
from core.db import get_db


class _FakeDB:
    """connect의 org 조회(db.scalar)만 흉내 — 실제 쿼리는 실행 안 함."""

    def __init__(self, org_id):
        self._org_id = org_id

    async def scalar(self, *args, **kwargs):
        return self._org_id


def _make_client(monkeypatch, *, org_id):
    monkeypatch.setattr(management.settings, "meta_app_id", "app-test", raising=False)
    monkeypatch.setattr(management.settings, "meta_graph_api_version", "v23.0", raising=False)
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_db] = lambda: _FakeDB(org_id)
    return TestClient(app)


def test_connect_returns_login_url_with_org_state(monkeypatch):
    org = uuid.uuid4()
    client = _make_client(monkeypatch, org_id=org)
    res = client.get("/api/management/meta/connect")
    assert res.status_code == 200
    parts = urlsplit(res.json()["login_url"])
    assert parts.netloc == "www.facebook.com"
    assert "/dialog/oauth" in parts.path
    q = parse_qs(parts.query)
    assert q["client_id"] == ["app-test"]
    assert q["response_type"] == ["code"]
    assert q["state"][0].startswith(f"{org}:")  # JWT org를 state로 운반


def test_connect_409_without_org(monkeypatch):
    client = _make_client(monkeypatch, org_id=None)
    res = client.get("/api/management/meta/connect")
    assert res.status_code == 409


def test_connect_503_without_app_id(monkeypatch):
    client = _make_client(monkeypatch, org_id=uuid.uuid4())
    monkeypatch.setattr(management.settings, "meta_app_id", None, raising=False)
    res = client.get("/api/management/meta/connect")
    assert res.status_code == 503
