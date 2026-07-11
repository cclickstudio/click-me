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


async def test_sim_reader_trusts_caller_org_scope():
    """org 대조 없음(b0ce8412) — 호출부가 이미 스코프한 링크는 org 불일치여도 신뢰(교차 조직 링크 허용)."""
    row = (_AD, str(uuid.uuid4()), None, 0.42, 3.8, 4.1, 0.12)
    snap = await SimPredictionReader(_factory(row)).get_prediction(_SIM, _ORG)
    assert snap is not None
    assert snap.ad_id == _AD


async def test_sim_reader_no_row_none():
    assert await SimPredictionReader(_factory(None)).get_prediction(_SIM, _ORG) is None


async def test_sim_reader_bad_uuid_none():
    assert await SimPredictionReader(_factory(None)).get_prediction("not-a-uuid", _ORG) is None


def test_sim_reader_sql_excludes_soft_deleted():
    """소프트삭제 시뮬은 예측 제외 — SQL에 deleted_at 필터 필수(성과 비교 삭제 반영·회귀 방지)."""
    sql = str(SimPredictionReader._SQL).lower()
    assert "deleted_at is null" in sql
