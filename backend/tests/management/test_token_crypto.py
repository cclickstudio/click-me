# Meta 토큰 AES-256-GCM 암호화 유틸 — 왕복·논스랜덤·변조감지·키검증
import base64

import pytest
from cryptography.exceptions import InvalidTag

from domain.management.adapters.meta.token_crypto import TokenCipher, generate_key


def _cipher() -> TokenCipher:
    return TokenCipher.from_base64_key(generate_key())


def test_roundtrip():
    c = _cipher()
    token = "EAAB-very-secret-long-lived-token"
    assert c.decrypt(c.encrypt(token)) == token


def test_ciphertext_differs_each_time():
    # 논스 랜덤이라 같은 평문도 매번 다른 암호문 (패턴 노출 방지)
    c = _cipher()
    token = "same-token"
    assert c.encrypt(token) != c.encrypt(token)


def test_plaintext_not_in_ciphertext():
    c = _cipher()
    token = "leak-check-token"
    assert token not in c.encrypt(token)


def test_tamper_is_detected():
    # GCM은 인증 암호 — 한 바이트만 바꿔도 복호화 실패
    c = _cipher()
    enc = c.encrypt("tamper-me")
    raw = bytearray(base64.urlsafe_b64decode(enc))
    raw[-1] ^= 0x01
    tampered = base64.urlsafe_b64encode(bytes(raw)).decode("ascii")
    with pytest.raises(InvalidTag):
        c.decrypt(tampered)


def test_wrong_key_fails():
    enc = _cipher().encrypt("secret")
    with pytest.raises(InvalidTag):
        _cipher().decrypt(enc)


def test_key_must_be_32_bytes():
    with pytest.raises(ValueError, match="32"):
        TokenCipher(b"too-short-key")


def test_generate_key_is_32_bytes_base64():
    key = base64.urlsafe_b64decode(generate_key())
    assert len(key) == 32
