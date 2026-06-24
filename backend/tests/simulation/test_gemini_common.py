# Gemini 어댑터 공통 — 503/429/5xx 재시도(백오프) 단위 테스트
from __future__ import annotations

import pytest

from domain.simulation.adapters.gemini import _common


def test_is_transient_status_codes() -> None:
    class StatusError(Exception):
        def __init__(self, code: int) -> None:
            self.code = code

    assert _common._is_transient(StatusError(503))
    assert _common._is_transient(StatusError(429))
    assert _common._is_transient(StatusError(500))
    assert not _common._is_transient(StatusError(400))
    assert not _common._is_transient(StatusError(404))


def test_is_transient_by_message() -> None:
    assert _common._is_transient(Exception("503 UNAVAILABLE: The model is overloaded"))
    assert _common._is_transient(Exception("model is overloaded, please try again later"))
    assert not _common._is_transient(Exception("invalid argument: bad request"))


class _Resp:
    text = '{"ok": true}'
    usage_metadata = None


def _client(behavior) -> object:
    """aio.models.generate_content 가 behavior(콜번호) 결과를 내는 가짜 클라이언트."""
    calls = {"n": 0}

    class Models:
        async def generate_content(self, **kwargs):
            calls["n"] += 1
            return behavior(calls["n"])

    class Aio:
        models = Models()

    class Client:
        aio = Aio()
        n = calls

    return Client()


class _TransientError(Exception):
    code = 503


async def test_agen_json_retries_then_succeeds(monkeypatch) -> None:
    # 무대기로(백오프 0) 빠르게 검증.
    monkeypatch.setattr(_common, "_RETRY_WAIT_MULTIPLIER", 0.0)
    monkeypatch.setattr(_common, "_RETRY_WAIT_MAX", 0.0)

    def behavior(n: int):
        if n < 3:  # 2회 503 후 성공
            raise _TransientError("overloaded")
        return _Resp()

    client = _client(behavior)
    out = await _common._agen_json(client, "gemini-2.5-flash", "prompt")
    assert out == {"ok": True}
    assert client.n["n"] == 3


async def test_agen_json_gives_up_after_attempts(monkeypatch) -> None:
    monkeypatch.setattr(_common, "_RETRY_WAIT_MULTIPLIER", 0.0)
    monkeypatch.setattr(_common, "_RETRY_WAIT_MAX", 0.0)
    monkeypatch.setattr(_common, "_RETRY_ATTEMPTS", 3)

    def behavior(n: int):
        raise _TransientError("overloaded")

    client = _client(behavior)
    with pytest.raises(_TransientError):
        await _common._agen_json(client, "m", "p")
    assert client.n["n"] == 3  # 상한만큼만 시도


async def test_agen_json_does_not_retry_non_transient(monkeypatch) -> None:
    monkeypatch.setattr(_common, "_RETRY_WAIT_MULTIPLIER", 0.0)
    monkeypatch.setattr(_common, "_RETRY_WAIT_MAX", 0.0)

    class PermanentError(Exception):
        code = 400

    def behavior(n: int):
        raise PermanentError("bad request")

    client = _client(behavior)
    with pytest.raises(PermanentError):
        await _common._agen_json(client, "m", "p")
    assert client.n["n"] == 1  # 재시도 없이 즉시 실패
