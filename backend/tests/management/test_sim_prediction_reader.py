# SimPredictionReader 단위 + Mock 시그니처
import uuid

from domain.management.comparison.prediction_adapters import (
    MockPredictionReader,
    SimPredictionReader,
)

_ORG = str(uuid.uuid4())
_SIM = str(uuid.uuid4())


async def test_mock_reader_new_signature_returns_snapshot():
    snap = await MockPredictionReader().get_prediction(_SIM, _ORG)
    assert snap is not None
    assert snap.source == "mock"
    assert 0.0 <= snap.click_intent_rate <= 1.0


async def test_mock_reader_empty_key_none():
    assert await MockPredictionReader().get_prediction("", _ORG) is None


_AD = str(uuid.uuid4())


class _Row:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeSession:
    def __init__(self, row):
        self._row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, stmt, params=None):
        return _Row(self._row)


def _factory(row):
    # row = (ad_id, org_id, completed_at, cir, purchase_intent_avg, trust_avg, rejection_rate)
    def make():
        return _FakeSession(row)

    return make


async def test_sim_reader_maps_aggregate():
    row = (_AD, _ORG, None, 0.42, 3.8, 4.1, 0.12)
    snap = await SimPredictionReader(_factory(row)).get_prediction(_SIM, _ORG)
    assert snap is not None
    assert snap.source == "sim"
    assert snap.ad_id == _AD
    assert snap.click_intent_rate == 0.42
    assert snap.purchase_intent == 3.8
    assert snap.trust_avg == 4.1
    assert snap.rejection_rate == 0.12


async def test_sim_reader_other_org_none():
    row = (_AD, str(uuid.uuid4()), None, 0.42, 3.8, 4.1, 0.12)
    assert await SimPredictionReader(_factory(row)).get_prediction(_SIM, _ORG) is None


async def test_sim_reader_no_row_none():
    assert await SimPredictionReader(_factory(None)).get_prediction(_SIM, _ORG) is None


async def test_sim_reader_bad_uuid_none():
    assert await SimPredictionReader(_factory(None)).get_prediction("not-a-uuid", _ORG) is None
