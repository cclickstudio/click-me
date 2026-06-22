# CreatedCampaign.simulation_id 컬럼 존재 + _record_created_campaign 영속 단위
from core.models import CreatedCampaign


def test_created_campaign_has_simulation_id_column():
    cols = CreatedCampaign.__table__.columns
    assert "simulation_id" in cols
    assert cols["simulation_id"].nullable is True
