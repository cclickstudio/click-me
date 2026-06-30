# generator GET /generations/{id} 내부호출 org 스코프 — 라우터 분기 검증(B-1 선결)
import uuid
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import generator
from core.auth import optional_user
from core.config import settings
from core.db import get_db
from domain.generator.service import generator_service

_CORRECT_ORG = uuid.uuid4()
_OTHER_ORG = uuid.uuid4()
_GEN_ID = str(uuid.uuid4())
_INTERNAL_TOKEN = "internal-tok"


def _app(monkeypatch, *, user=None):
    async def fake_get_detail(generation_id, org_id=None):
        # org 스코프 흉내 — org_id 주어지면 일치할 때만 반환(불일치/타 org → None → 404).
        if org_id is not None and org_id != _CORRECT_ORG:
            return None
        return {"generation_id": generation_id}

    monkeypatch.setattr(generator_service, "get_detail", fake_get_detail)
    monkeypatch.setattr(settings, "internal_service_token", _INTERNAL_TOKEN)

    async def fake_require_user_org(u, db):
        return _CORRECT_ORG

    monkeypatch.setattr(generator, "_require_user_org", fake_require_user_org)

    app = FastAPI()
    app.include_router(generator.router, prefix="/api/generator")
    app.dependency_overrides[optional_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: SimpleNamespace()
    return TestClient(app)


_URL = f"/api/generator/generations/{_GEN_ID}"


def test_get_generation_internal_wrong_org_404(monkeypatch):
    client = _app(monkeypatch)
    resp = client.get(
        _URL, headers={"X-Internal-Token": _INTERNAL_TOKEN, "X-Org-Id": str(_OTHER_ORG)}
    )
    assert resp.status_code == 404


def test_get_generation_internal_correct_org_200(monkeypatch):
    client = _app(monkeypatch)
    resp = client.get(
        _URL, headers={"X-Internal-Token": _INTERNAL_TOKEN, "X-Org-Id": str(_CORRECT_ORG)}
    )
    assert resp.status_code == 200


def test_get_generation_internal_missing_org_400(monkeypatch):
    # internal 토큰 경로는 X-Org-Id 없으면 거부(무스코프 우회면 제거, 리뷰 P1-a).
    client = _app(monkeypatch)
    resp = client.get(_URL, headers={"X-Internal-Token": _INTERNAL_TOKEN})
    assert resp.status_code == 400


def test_get_generation_user_path_needs_no_org_header(monkeypatch):
    # 로그인 유저(비ADMIN) 경로는 세션 org를 쓰므로 X-Org-Id 불필요(프론트 정상, 리뷰 P2-c).
    client = _app(monkeypatch, user=SimpleNamespace(id=uuid.uuid4(), role="USER"))
    resp = client.get(_URL)
    assert resp.status_code == 200


def test_get_generation_admin_org_agnostic(monkeypatch):
    # ADMIN은 조직 무관 조회(3k 머지) — org 스코프 없이 200.
    client = _app(monkeypatch, user=SimpleNamespace(id=uuid.uuid4(), role="ADMIN"))
    resp = client.get(_URL)
    assert resp.status_code == 200


def test_get_generation_mock_no_user_no_header_ok(monkeypatch):
    # use_mock + 무인증 + 헤더 없음 = 기존 dev 브라우징 — 400 아님(리뷰 P2-c).
    client = _app(monkeypatch)
    resp = client.get(_URL)
    assert resp.status_code == 200
