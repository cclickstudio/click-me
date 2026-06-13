# 분포 로더 단위 테스트 — JSON 적재·스키마·CSV 우선·상태 보고 검증
from __future__ import annotations

from domain.simulation.data import loader


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
    # 트레이트 실수치는 아직 미확보(placeholder) 상태여야 함.
    assert data["trait_params"]["needs_real_values"] is True


def test_population_shares_sum_to_one() -> None:
    data = loader.load_population_age_sex()
    total = sum(b["share"] for b in data["bands"])
    assert abs(total - 1.0) < 1e-6
    assert all(0.0 <= b["male_ratio"] <= 1.0 for b in data["bands"])


def test_data_status_reports_pending_items() -> None:
    status = loader.data_status()
    assert status["consumption_values"].startswith("real")
    assert "pending" in status["media_behavior"]
    assert "pending" in status["social_values_deep"]
