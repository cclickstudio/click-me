# Meta 플랫폼(IG/FB) 특정 도달 폴백 단위 테스트 — 플랫폼 데이터 없으면 통합 reach(현 동작 보존)
from __future__ import annotations

from domain.simulation.tools.sampling.persona_sampler import PersonaSampler

_FIXTURE = {
    "age_bands": {"20-29": 0.3, "30-39": 0.2},
    "platform_specifics": {
        "instagram": {
            "age_bands": {"20-29": 0.5, "30-39": 0.1},
            "by_age_gender": {"20-29|F": 0.6},
        },
        "facebook": {"age_bands": {}, "by_age_gender": {}},
    },
}


def _sampler(platform: str | None = None) -> PersonaSampler:
    return PersonaSampler(meta_reach=_FIXTURE, platform=platform)


def test_reach_uses_combined_without_platform() -> None:
    s = _sampler()
    assert s._reach_marginal("20-29") == 0.3
    assert s._cell_reach(25, "F") == 0.3


def test_reach_falls_back_when_platform_data_empty() -> None:
    s = _sampler(platform="facebook")  # platform_specifics 비어 있음
    assert s._reach_marginal("20-29") == 0.3
    assert s._cell_reach(25, "M") == 0.3


def test_reach_uses_platform_when_present() -> None:
    s = _sampler(platform="instagram")
    assert s._reach_marginal("20-29") == 0.5  # 플랫폼 연령 marginal
    assert s._cell_reach(25, "F") == 0.6  # 연령×성별 실값
    # by_age_gender에 없는 성별은 플랫폼 연령 marginal로 폴백.
    assert s._cell_reach(25, "M") == 0.5


def test_real_platform_specifics_skew() -> None:
    # 실 meta_reach.json(KOSIS SNS 1순위 산출) — IG는 젊은층, FB는 중년 편중.
    ig = PersonaSampler(platform="instagram")
    fb = PersonaSampler(platform="facebook")
    bands = ig._meta_reach["platform_specifics"]["instagram"]["age_bands"]
    assert abs(sum(bands.values()) - 1.0) < 0.01  # 연령 marginal 합≈1
    assert ig._reach_marginal("20-29") > ig._reach_marginal("50-59")  # IG 젊은층↑
    assert fb._reach_marginal("40-49") > fb._reach_marginal("10-19")  # FB 중년↑
    # 플랫폼 간 편중 대비 — IG는 20대, FB는 40대에서 상대적으로 큼.
    assert ig._reach_marginal("20-29") > fb._reach_marginal("20-29")
    assert fb._reach_marginal("40-49") > ig._reach_marginal("40-49")
