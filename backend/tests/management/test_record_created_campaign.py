# CreatedCampaign.simulation_id 컬럼 존재 + _record_created_campaign 영속 단위
import uuid
from types import SimpleNamespace

import pytest

from api.routers import management
from core.models import CreatedCampaign


def test_created_campaign_has_simulation_id_column():
    cols = CreatedCampaign.__table__.columns
    assert "simulation_id" in cols
    assert cols["simulation_id"].nullable is True


_SIM = str(uuid.uuid4())
_SIM2 = str(uuid.uuid4())


class _CaptureDB:
    def __init__(self):
        self.added = None

    def add(self, obj):
        self.added = obj

    async def commit(self):
        return None


def _proposal(evidence):
    return SimpleNamespace(
        evidence_metrics=evidence,
        tenant_id="org_1",
        ad_account_id="act_1",
        budget_after_krw=10000,
    )


def _result():
    return SimpleNamespace(status=SimpleNamespace(value="success"), platform_response_snapshot={})


@pytest.mark.parametrize(
    "evidence,expected",
    [
        ({"campaign_config": {"name": "C"}, "simulation_id": _SIM}, _SIM),
        (
            {"campaign_config": {"name": "C"}, "simulation_snapshot": {"simulation_id": _SIM2}},
            _SIM2,
        ),
        (
            {
                "campaign_config": {"name": "C"},
                "simulation_id": _SIM,
                "simulation_snapshot": {"simulation_id": _SIM2},
            },
            _SIM,
        ),  # 수동 우선
        ({"campaign_config": {"name": "C"}}, None),
    ],
)
async def test_record_persists_simulation_id(evidence, expected):
    db = _CaptureDB()
    await management._record_created_campaign(db, _proposal(evidence), _result())
    got = db.added.simulation_id
    assert (str(got) if got else None) == expected
