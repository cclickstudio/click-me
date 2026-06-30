# Cognito JWKS(RS256) 검증 경로와 local↔cognito 분기를 네트워크 없이 단위 검증.
import time
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import JWTError, jwk
from jose import jwt as jose_jwt

from core import auth as auth_mod
from core import cognito_admin
from core.auth import (
    _resolve_user,
    create_access_token,
    decode_token,
)
from core.config import settings

ISSUER = "https://cognito-idp.ap-northeast-2.amazonaws.com/ap-northeast-2_test"
CLIENT_ID = "test-app-client-id"
KID = "test-kid"


@pytest.fixture
def rsa_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    pub_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    jwk_dict = jwk.construct(pub_pem, "RS256").to_dict()
    jwk_dict.update({"kid": KID, "use": "sig", "alg": "RS256"})
    return priv_pem, {"keys": [jwk_dict]}


def _make_token(priv_pem: str, **overrides) -> str:
    claims = {
        "sub": "cognito-sub-123",
        "cognito:username": "alice",
        "token_use": "id",
        "aud": CLIENT_ID,
        "iss": ISSUER,
        "exp": int(time.time()) + 3600,
        **overrides,
    }
    return jose_jwt.encode(claims, priv_pem, algorithm="RS256", headers={"kid": KID})


@pytest.fixture
def cognito_mode(monkeypatch, rsa_keypair):
    priv_pem, jwks = rsa_keypair
    monkeypatch.setattr(settings, "auth_provider", "cognito")
    monkeypatch.setattr(settings, "cognito_region", "ap-northeast-2")
    monkeypatch.setattr(settings, "cognito_user_pool_id", "ap-northeast-2_test")
    monkeypatch.setattr(settings, "cognito_app_client_id", CLIENT_ID)
    # 네트워크 차단 — JWKS는 고정 키셋을 반환.
    monkeypatch.setattr(auth_mod, "_fetch_jwks", lambda force=False: jwks)
    return priv_pem


def test_local_mode_roundtrip(monkeypatch):
    monkeypatch.setattr(settings, "auth_provider", "local")
    token = create_access_token("user-1", "ADMIN")
    payload = decode_token(token)
    assert payload["sub"] == "user-1"
    assert payload["role"] == "ADMIN"


def test_cognito_valid_id_token(cognito_mode):
    payload = decode_token(_make_token(cognito_mode))
    assert payload["cognito:username"] == "alice"
    assert payload["token_use"] == "id"


def test_cognito_rejects_access_token(cognito_mode):
    # access 토큰(token_use != id)은 거부.
    with pytest.raises(JWTError):
        decode_token(_make_token(cognito_mode, token_use="access"))


def test_cognito_rejects_wrong_audience(cognito_mode):
    with pytest.raises(JWTError):
        decode_token(_make_token(cognito_mode, aud="someone-else"))


def test_cognito_rejects_wrong_issuer(cognito_mode):
    with pytest.raises(JWTError):
        decode_token(_make_token(cognito_mode, iss="https://evil.example.com"))


class _FakeDB:
    """scalar(select(User).where(User.login_id == X)) 흉내 — login_id 매칭만 검증."""

    def __init__(self, user):
        self._user = user

    async def scalar(self, _stmt):
        return self._user


@pytest.mark.asyncio
async def test_resolve_user_cognito_uses_username(monkeypatch):
    monkeypatch.setattr(settings, "auth_provider", "cognito")
    user = SimpleNamespace(login_id="alice", status="ACTIVE")
    resolved = await _resolve_user({"cognito:username": "alice"}, _FakeDB(user))
    assert resolved is user


@pytest.mark.asyncio
async def test_resolve_user_cognito_missing_username_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "auth_provider", "cognito")
    resolved = await _resolve_user({"sub": "x"}, _FakeDB(SimpleNamespace()))
    assert resolved is None


@pytest.mark.asyncio
async def test_cognito_admin_noop_in_local(monkeypatch):
    # local 모드면 Cognito 동기화는 전부 no-op — boto 호출·네트워크 없이 즉시 반환.
    monkeypatch.setattr(settings, "auth_provider", "local")
    assert cognito_admin.is_enabled() is False
    await cognito_admin.create_user("x", "password", "USER")
    await cognito_admin.set_password("x", "password")
    assert await cognito_admin.delete_user("x") is False
