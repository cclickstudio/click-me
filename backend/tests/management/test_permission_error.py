# MetaApiError 권한 거부 식별·요약 자리표시 단위 테스트 — DB·네트워크 불필요(순수).

from __future__ import annotations

from api.routers.management import _blocked_summary
from domain.management.adapters.meta.client import MetaApiError


def test_permission_codes_flagged():
    # 대표 권한 거부 코드(10=앱권한, 200/272/294=권한)는 is_permission_error=True.
    for code in (10, 200, 272, 294):
        assert MetaApiError(code, None, "permission").is_permission_error is True
    # 100은 subcode 33(필드/객체 접근 불가)일 때만 권한으로 본다.
    assert MetaApiError(100, 33, "no access").is_permission_error is True
    assert MetaApiError(100, 0, "other").is_permission_error is False


def test_non_permission_codes_not_flagged():
    # 인증 만료(190)·레이트리밋(17)은 권한 거부가 아니다(각자 별도 처리).
    assert MetaApiError(190, None, "expired").is_permission_error is False
    assert MetaApiError(17, None, "rate").is_permission_error is False
    assert MetaApiError(190, None, "expired").is_auth_error is True
    assert MetaApiError(17, None, "rate").is_rate_limited is True


def test_blocked_summary_has_full_kpi_keys():
    # 권한 거부 자리표시는 정상 요약과 같은 키 집합 — 프론트 타입 깨짐 방지.
    s = _blocked_summary()
    for key in (
        "impressions",
        "spend_krw",
        "cpm_krw",
        "pacing_pct",
        "spend_today_krw",
        "frequency_7d",
    ):
        assert key in s
    assert s["pacing_pct"] == 0.0
    assert s["conversions"] is None
