# 분포 로더 단위 테스트 — JSON 적재·스키마·CSV 우선·상태 보고 검증
from __future__ import annotations

from domain.simulation.data.simulation import loader


def test_consumption_values_loads_with_rates() -> None:
    data = loader.load_consumption_values()
    assert 0.0 < data["values"]["성능"] <= 1.0
    assert "Z세대" in data["generation_specific"]


def test_ocean_age_bands_have_tiers_and_samples() -> None:
    data = loader.load_ocean_age_bands()
    bands = data["age_bands"]
    assert bands["20-29"]["tier"] == "P1"
    assert bands["50-59"]["tier"] == "P2"
    assert all(b["sample_size"] > 0 for b in bands.values())
    assert len(data["personality_types"]) == 5
    # 5유형 프로필이 OCEAN 5차원의 실 mean·sd(Table 1)를 갖는다.
    expressive = data["type_profiles"]["Expressive"]
    assert expressive["extraversion"]["mean"] == 1.33
    # 유형 비율은 실 표본수 기반(미확보 아님), 합≈1.
    assert data["type_proportions"]["needs_real_values"] is False
    assert abs(sum(data["type_proportions"]["default"].values()) - 1.0) < 0.01


def test_population_shares_sum_to_one() -> None:
    data = loader.load_population_age_sex()
    total = sum(b["share"] for b in data["bands"])
    assert abs(total - 1.0) < 1e-6
    assert all(0.0 <= b["male_ratio"] <= 1.0 for b in data["bands"])


def test_population_region_weights_real_when_csv_present() -> None:
    # 행안부 원본 CSV가 있으면 시도(17개) 실분포가 합=1 로 나온다. (정규화·placeholder면 키 없음)
    data = loader.load_population_age_sex()
    rw = data.get("region_weights")
    if rw is None:  # CSV 미적재 환경 — 스킵(샘플러는 근사 폴백)
        return
    assert len(rw) == 17
    assert abs(sum(rw.values()) - 1.0) < 1e-3
    assert "경기도" in rw


def test_media_behavior_cells_have_device_minutes_and_exposure() -> None:
    # v2(KISDI raw) — 연령×성별 셀별 매체 사용시간 + 노출맥락(시간대·매체·행위·장소).
    data = loader.load_media_behavior()
    assert data["slot_minutes"] == 15
    cell = data["cells"]["20-29|F"]
    assert cell["device_minutes"]  # 매체대분류별 일일 평균(분)
    assert all(v >= 0 for v in cell["device_minutes"].values())
    assert cell["daily_media_minutes"]["mean"] > 0
    expo = cell["exposure"]
    assert expo and {"timeband", "medium", "activity", "place", "p"} <= set(expo[0])


def test_socioeconomic_cells_have_income_and_education() -> None:
    # KISDI 소득(8구간)·학력(6단계) — 셀별 분포, share 합≈1.
    data = loader.load_socioeconomic()
    cell = data["cells"]["30-39|M"]
    for dim in ("income", "education"):
        dist = cell[dim]
        assert dist and {"label", "code", "share"} <= set(dist[0])
        assert abs(sum(d["share"] for d in dist) - 1.0) < 1e-2


def test_data_status_reports_pending_items() -> None:
    status = loader.data_status()
    assert status["consumption_values"].startswith("real")
    assert status["media_behavior"].startswith("real")
    assert status["socioeconomic"].startswith("real")
    assert "pending" in status["social_values_deep"]
