# from-candidate — 후보 → CREATE_CAMPAIGN(traffic) 제안 패키징
import uuid
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import management
from core.auth import get_current_user
from core.db import get_db


class _FakeDB:
    """org 조회(db.scalar)만 흉내 — meta_connections는 None으로 mock fallback."""

    def __init__(self, org_id):
        self._org_id = org_id

    async def scalar(self, stmt, *a, **k):
        if "organization_members" in str(stmt):
            return self._org_id
        return None


_CAND = {
    "candidate_id": "c1",
    "idx": 0,
    "strategy": "s",
    "template_id": "t",
    "copy": {"headline": "제목", "body": "본문", "cta": "사기"},
    "s3_key": "generator/images/g1/0.png",
}

_URL = "/api/management/campaign-proposals/from-candidate"


def _client(monkeypatch):
    from domain.management.adapters.generator.client import GeneratorReadClient, HandoffCandidate

    async def fake_get_candidate(self, gen_id, cand_id):
        return HandoffCandidate.model_validate(_CAND)

    async def fake_download(key):
        return b"\x89PNG fake"

    async def fake_policy(reader):
        return {}

    monkeypatch.setattr(GeneratorReadClient, "get_candidate", fake_get_candidate)
    monkeypatch.setattr(management, "download_bytes", fake_download)
    monkeypatch.setattr(management, "get_campaign_policy", fake_policy)
    monkeypatch.setattr(management, "min_daily_budget_for", lambda objective, policy: 1)

    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_db] = lambda: _FakeDB(uuid.uuid4())
    return TestClient(app)


def _body(**over):
    base = {
        "generation_id": "g1",
        "candidate_id": "c1",
        "link_url": "https://shop.example.com",
        "name": "캠페인",
        "daily_budget_krw": 50000,
        "run_days": 7,
    }
    base.update(over)
    return base


def test_from_candidate_builds_traffic_proposal(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post(_URL, json=_body())
    assert resp.status_code == 200, resp.text
    proposal = resp.json()["proposal"]
    assert proposal["action_type"] == "CREATE_CAMPAIGN"
    cfg = proposal["evidence_metrics"]["campaign_config"]
    assert cfg["objective"] == "traffic"
    assert cfg["headline"] == "제목"
    assert cfg["body"] == "본문"
    assert cfg["link_url"].rstrip("/") == "https://shop.example.com"
    snap = proposal["evidence_metrics"]["candidate_snapshot"]
    assert snap["candidate_id"] == "c1"
    assert "image_hash" in snap


def test_from_candidate_rejects_unknown_field(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post(_URL, json=_body(objective="leads"))
    assert resp.status_code == 422


def test_from_candidate_missing_link_url_422(monkeypatch):
    client = _client(monkeypatch)
    body = _body()
    del body["link_url"]
    resp = client.post(_URL, json=body)
    assert resp.status_code == 422


def test_from_candidate_invalid_url_422(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post(_URL, json=_body(link_url="not-a-url"))
    assert resp.status_code == 422


def test_from_candidate_rejects_path_injection_in_ids(monkeypatch):
    # generation_id에 경로 주입 문자 → 패턴 검증 422 (self-call URL 보호)
    client = _client(monkeypatch)
    resp = client.post(_URL, json=_body(generation_id="../admin"))
    assert resp.status_code == 422
