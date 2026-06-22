# SimPredictionReader 단위 + Mock 시그니처
import uuid

from domain.management.comparison.prediction_adapters import MockPredictionReader

_ORG = str(uuid.uuid4())
_SIM = str(uuid.uuid4())


async def test_mock_reader_new_signature_returns_snapshot():
    snap = await MockPredictionReader().get_prediction(_SIM, _ORG)
    assert snap is not None
    assert snap.source == "mock"
    assert 0.0 <= snap.click_intent_rate <= 1.0


async def test_mock_reader_empty_key_none():
    assert await MockPredictionReader().get_prediction("", _ORG) is None
