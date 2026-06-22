# before-after — creative_ad_id는 실측 귀속 유지, simulation_id는 예측 키로 전달되는지
import uuid
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import management
from core.db import get_db

_SIM = uuid.uuid4()


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Result._S(self._rows)

    class _S:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, stmt):
        return _Result(self._rows)


def test_before_after_passes_sim_and_keeps_creative(monkeypatch):
    calls = {}

    class _Pred:
        async def get_prediction(self, simulation_id, tenant_id):
            calls["pred"] = (simulation_id, tenant_id)
            return None

    class _Reader:
        async def list_campaigns(self):
            return [SimpleNamespace(campaign_id="m1", name="C1")]

        async def get_metrics(self, cid, now):
            return object()

    def fake_real_outcome(m, cid, creative_id):
        calls["creative"] = creative_id
        return SimpleNamespace()

    def fake_cba(cid, name, prediction, actual):
        calls["prediction_arg"] = prediction
        return SimpleNamespace(model_dump=lambda mode=None: {"campaign_id": cid, "name": name})

    monkeypatch.setattr(management, "build_reader", lambda s: _Reader())
    monkeypatch.setattr(management, "build_prediction_reader", lambda s: _Pred())
    monkeypatch.setattr(management, "_real_outcome", fake_real_outcome)
    monkeypatch.setattr(management, "compute_before_after", fake_cba)

    rows = [
        SimpleNamespace(
            meta_campaign_id="m1", creative_ad_id="cr1", simulation_id=_SIM, tenant_id="org_1"
        )
    ]
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_db] = lambda: _FakeDB(rows)
    res = TestClient(app).get("/api/management/compare/before-after")

    assert res.status_code == 200, res.text
    assert calls["pred"] == (str(_SIM), "org_1")  # 예측 키 = simulation_id + tenant
    assert calls["creative"] == "cr1"  # 실측 귀속 = creative_ad_id 유지


async def test_tools_live_before_after_passes_sim(monkeypatch):
    from contextlib import asynccontextmanager

    from domain.management.assistant import tools

    calls = {}

    class _Pred:
        async def get_prediction(self, simulation_id, tenant_id):
            calls["pred"] = (simulation_id, tenant_id)
            return None

    class _Reader:
        async def list_campaigns(self):
            return [SimpleNamespace(campaign_id="m1", name="C1")]

        async def get_metrics(self, cid, now):
            return object()

    rows = [
        SimpleNamespace(
            meta_campaign_id="m1", creative_ad_id="cr1", simulation_id=_SIM, tenant_id="org_1"
        )
    ]

    @asynccontextmanager
    async def fake_session():
        yield _FakeDB(rows)

    monkeypatch.setattr(tools, "AsyncSessionLocal", fake_session)
    monkeypatch.setattr(tools, "build_reader", lambda s: _Reader())
    monkeypatch.setattr(tools, "build_prediction_reader", lambda s: _Pred())
    monkeypatch.setattr(
        tools,
        "_outcome",
        lambda m, cid, creative_id: calls.setdefault("creative", creative_id) or SimpleNamespace(),
    )
    monkeypatch.setattr(
        tools,
        "compute_before_after",
        lambda cid, name, prediction, actual: SimpleNamespace(
            name=name, verdict=SimpleNamespace(value="unknown"), rationale="r"
        ),
    )

    out = await tools.live_before_after(SimpleNamespace())
    assert out["items"][0]["name"] == "C1"
    assert calls["pred"] == (str(_SIM), "org_1")
    assert calls["creative"] == "cr1"
