# MetaCredentials 심 — settings(.env 단일 토큰) 폴백 로드 + build_meta_client 드롭인 검증
from types import SimpleNamespace

from domain.management.adapters.meta.client import build_meta_client
from domain.management.adapters.meta.credentials import (
    MetaCredentials,
    load_meta_credentials,
)


def _settings(**overrides):
    base = {
        "meta_access_token": "tok-abc",
        "meta_ad_account_id": "act_1",
        "meta_graph_api_version": "v23.0",
        "meta_app_id": "app1",
        "meta_app_secret": "sec1",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_load_mirrors_settings():
    creds = load_meta_credentials(_settings())
    assert isinstance(creds, MetaCredentials)
    assert creds.meta_access_token == "tok-abc"
    assert creds.meta_ad_account_id == "act_1"
    assert creds.meta_graph_api_version == "v23.0"
    assert creds.meta_app_id == "app1"
    assert creds.meta_app_secret == "sec1"


def test_load_handles_missing_attrs():
    # 빈 settings여도 폴백이 깨지지 않고 None으로 채움
    creds = load_meta_credentials(SimpleNamespace())
    assert creds.meta_access_token is None
    assert creds.meta_ad_account_id is None


def test_organization_id_reserved_but_falls_back_to_settings():
    # (A) meta_connections 도입 전까지는 org를 줘도 전역 settings로 폴백
    creds = load_meta_credentials(_settings(), organization_id="org_42")
    assert creds.meta_access_token == "tok-abc"


def test_credentials_drop_in_for_build_meta_client():
    s = _settings()
    via_settings = build_meta_client(s)
    via_creds = build_meta_client(load_meta_credentials(s))
    # 같은 인터페이스 — 토큰만 바뀔 자리, 지금은 동일 값이라 산출도 동일
    assert via_creds.ad_account_id == via_settings.ad_account_id


def test_repr_masks_token_and_secret():
    # 앞 4자만 남기는 마스킹이라 실제처럼 긴 값으로 검증(전체 노출 금지)
    creds = load_meta_credentials(
        _settings(
            meta_access_token="EAAB-secret-token-value",
            meta_app_secret="appsecret-confidential-value",
        )
    )
    text = repr(creds)
    assert "EAAB-secret-token-value" not in text
    assert "appsecret-confidential-value" not in text
