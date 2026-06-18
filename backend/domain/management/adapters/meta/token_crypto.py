# 🅰 Meta 토큰 저장용 AES-256-GCM 암호화 — 평문 토큰 DB/로그 금지(CLAUDE.md 보안 규칙)
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_BYTES = 32  # AES-256
_NONCE_BYTES = 12  # GCM 권장 논스 길이


def generate_key() -> str:
    """새 32바이트(AES-256) 키를 base64(urlsafe)로 반환 — 환경변수/시크릿에 저장용."""
    return base64.urlsafe_b64encode(os.urandom(_KEY_BYTES)).decode("ascii")


class TokenCipher:
    """AES-256-GCM으로 토큰을 암호화/복호화한다.

    저장 포맷은 base64(urlsafe)(nonce(12B) + ciphertext+tag). GCM은 인증 암호라 변조 시
    복호화가 InvalidTag로 실패한다. 같은 평문도 논스가 매번 달라 암호문이 달라진다.
    키는 32바이트(주입) — 설정/시크릿 매니저에서 읽어 넘긴다(이 모듈은 키 출처를 모른다).
    """

    def __init__(self, key: bytes) -> None:
        if len(key) != _KEY_BYTES:
            raise ValueError(f"AES-256 키는 {_KEY_BYTES}바이트여야 함 (입력 {len(key)}B)")
        self._aes = AESGCM(key)

    @classmethod
    def from_base64_key(cls, key_b64: str) -> TokenCipher:
        """base64(urlsafe) 인코딩된 키 문자열로 생성."""
        return cls(base64.urlsafe_b64decode(key_b64))

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = self._aes.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, token_enc: str) -> str:
        raw = base64.urlsafe_b64decode(token_enc)
        nonce, ciphertext = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
        return self._aes.decrypt(nonce, ciphertext, None).decode("utf-8")
