# 집행 URL UTM 자동 부착 — 기존 utm 보존·쿼리 유무별 조립 확인
from api.routers.management import _with_utm


def test_utm_appended_to_bare_url():
    out = _with_utm("https://shop.example.com/landing", "camp_sim_abc123")
    assert out.startswith("https://shop.example.com/landing?")
    assert "utm_source=clickme" in out
    assert "utm_medium=paid_social" in out
    assert "utm_campaign=camp_sim_abc123" in out


def test_utm_appended_after_existing_query():
    out = _with_utm("https://shop.example.com/p?ref=insta", "camp_cand_x")
    assert "ref=insta&utm_source=clickme" in out


def test_existing_utm_respected():
    url = "https://shop.example.com/p?utm_source=naver&utm_campaign=own"
    assert _with_utm(url, "camp_sim_y") == url  # 광고주 설정 존중 — 덮어쓰기 금지
