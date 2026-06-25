# from-simulation — 시뮬(generator-소스) → CREATE_CAMPAIGN(traffic) 제안 + 순수 헬퍼
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import management
from core.auth import get_current_user
from core.db import get_db

_ORG = uuid.uuid4()
_AD = uuid.uuid4()
_SIM = "11111111-1111-1111-1111-111111111111"
_URL = "/api/management/campaign-proposals/from-simulation"


def test_resolve_sim_asset_key():
    f = management._resolve_sim_asset_key
    assert f("/api/generator/image?key=generator%2Fimages%2Fx.png") == "generator/images/x.png"
    assert f("generator/images/y.png") == "generator/images/y.png"
    assert f("/tmp/clickme_ad_abc.png") is None  # 업로드 임시 → 이연
    assert f("https://evil.example.com/x.png") is None  # 외부 → SSRF 차단
    assert f("/api/generator/image?key=secret%2Fkey") is None  # 비-durable prefix
    # 우리 S3 버킷 URL(presigned 포함) → 경로에서 키 추출(서명 쿼리 무시)
    assert (
        f("https://clickme-assets.s3.amazonaws.com/generated-ads/g/candidate-2.png?X-Amz-Signature=z")
        == "generated-ads/g/candidate-2.png"
    )
    assert f("https://other-bucket.s3.amazonaws.com/generated-ads/g/x.png") is None  # 타 버킷
    assert f(None) is None


def test_is_executable_verdict():
    # ⚠️ 임시(TEST): 게이트 해제 — 모든 입력 통과. 운영 복원 시 0.2/0.2 단언으로 되돌릴 것.
    f = management._is_executable_verdict
    assert f(0.0, 1.0) is True
    assert f(0.2, 0.1) is True
    assert f(0.05, 0.5) is True


class _Row:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeDB:
    """org(scalar) + 시뮬 raw SQL(execute) mock. MetaConnection은 None→mock 폴백."""

    def __init__(self, *, my_org, sim_org, cir, rej, asset_url):
        self._my_org = my_org
        self._sim = (sim_org, _AD)
        self._agg = (cir, rej)
        self._ad = ("제목", asset_url, "본문")

    async def scalar(self, stmt, *a, **k):
        if "organization_members" in str(stmt):
            return self._my_org
        return None

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
        if "from simulations" in s:
            return _Row(self._sim)
        if "from simulation_aggregates" in s:
            return _Row(self._agg)
        if "from ads" in s:
            return _Row(self._ad)
        return _Row(None)


def _client(
    monkeypatch,
    *,
    my_org=_ORG,
    sim_org=_ORG,
    cir=0.25,
    rej=0.1,
    asset_url="/api/generator/image?key=generator%2Fimages%2Fx.png",
):
    async def fake_download(key):
        return b"\x89PNG fake"

    class _Writer:
        async def upload_image(self, *a, **k):
            return None  # mock 모드 image_hash None 허용

    async def fake_policy(reader):
        return {}

    monkeypatch.setattr(management, "download_bytes", fake_download)
    monkeypatch.setattr(management, "build_writer", lambda s: _Writer())
    monkeypatch.setattr(management, "build_reader", lambda s: object())
    monkeypatch.setattr(management, "get_campaign_policy", fake_policy)
    monkeypatch.setattr(management, "min_daily_budget_for", lambda obj, pol: 1)

    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_db] = lambda: _FakeDB(
        my_org=my_org, sim_org=sim_org, cir=cir, rej=rej, asset_url=asset_url
    )
    return TestClient(app)


def _body(**over):
    base = {
        "simulation_id": _SIM,
        "link_url": "https://shop.example.com",
        "name": "캠페인",
        "daily_budget_krw": 50000,
        "start_date": "2030-01-01",
        "end_date": "2030-01-15",
    }
    base.update(over)
    return base


def test_from_simulation_builds_proposal(monkeypatch):
    resp = _client(monkeypatch).post(_URL, json=_body())
    assert resp.status_code == 200, resp.text
    proposal = resp.json()["proposal"]
    assert proposal["action_type"] == "CREATE_CAMPAIGN"
    assert proposal["evidence_metrics"]["campaign_config"]["objective"] == "traffic"
    snap = proposal["evidence_metrics"]["simulation_snapshot"]
    assert snap["simulation_id"] == _SIM
    assert snap["verdict"] == "집행 권장"
    assert snap["source_ad_id"] == str(_AD)
    assert "image_hash" in snap


def test_from_simulation_other_org_404(monkeypatch):
    resp = _client(monkeypatch, sim_org=uuid.uuid4()).post(_URL, json=_body())
    assert resp.status_code == 404


@pytest.mark.skip(reason="임시(TEST): 집행 게이트 해제로 409 미발생 — 게이트 0.2/0.2 복원 시 해제")
def test_from_simulation_bad_verdict_409(monkeypatch):
    resp = _client(monkeypatch, cir=0.1).post(_URL, json=_body())
    assert resp.status_code == 409


def test_from_simulation_non_durable_asset_422(monkeypatch):
    resp = _client(monkeypatch, asset_url="/tmp/clickme_ad_x.png").post(_URL, json=_body())
    assert resp.status_code == 422


def test_from_simulation_missing_link_url_422(monkeypatch):
    body = _body()
    del body["link_url"]
    resp = _client(monkeypatch).post(_URL, json=body)
    assert resp.status_code == 422


def test_from_simulation_rejects_unknown_field(monkeypatch):
    resp = _client(monkeypatch).post(_URL, json=_body(objective="leads"))
    assert resp.status_code == 422
