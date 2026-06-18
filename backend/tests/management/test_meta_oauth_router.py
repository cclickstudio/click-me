# Meta 연결 라우터 — /meta/connect가 Facebook 로그인 대화상자로 리다이렉트
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import management


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(management.settings, "meta_app_id", "app-test", raising=False)
    monkeypatch.setattr(management.settings, "meta_graph_api_version", "v23.0", raising=False)
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    return TestClient(app)


def test_connect_redirects_to_facebook_dialog(client):
    res = client.get(
        "/api/management/meta/connect",
        params={"organization_id": "org_42"},
        follow_redirects=False,
    )
    assert res.status_code == 307
    parts = urlsplit(res.headers["location"])
    assert parts.netloc == "www.facebook.com"
    assert "/dialog/oauth" in parts.path
    q = parse_qs(parts.query)
    assert q["client_id"] == ["app-test"]
    assert q["response_type"] == ["code"]
    assert q["state"][0].startswith("org_42:")  # org 운반 + CSRF nonce


def test_connect_503_without_app_id(client, monkeypatch):
    monkeypatch.setattr(management.settings, "meta_app_id", None, raising=False)
    res = client.get(
        "/api/management/meta/connect",
        params={"organization_id": "org_1"},
        follow_redirects=False,
    )
    assert res.status_code == 503
