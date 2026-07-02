# 단계3 한국 특화 심리(체면·동조·눈치) 프레임워크 테스트 — 값 비면 비활성(현 동작 보존)
from __future__ import annotations

from domain.simulation.adapters.gemini.reaction import _social_values_lines
from domain.simulation.contracts.schemas import PanelSpec, Persona
from domain.simulation.data.simulation import loader
from domain.simulation.tools.sampling.persona_sampler import PersonaSampler, _generation_of_age

_FIXTURE = {
    "generation_specific": {
        "Z세대": {"체면": 0.4, "동조": 0.3, "눈치": 0.7},
        "베이비부머": {"체면": 0.7, "동조": 0.6, "눈치": 0.8},
    }
}


def test_persona_field_empty_by_default() -> None:
    # 기본 데이터(값 비움) → 전부 빈 dict(반응 무변화).
    personas = PersonaSampler().sample(PanelSpec(size=30, seed=1))
    assert all(p.social_values_deep == {} for p in personas)


def test_sample_returns_values_when_data_present() -> None:
    s = PersonaSampler(social_values_deep=_FIXTURE)
    assert s._sample_social_values_deep(25, {}) == {"체면": 0.4, "동조": 0.3, "눈치": 0.7}
    assert s._sample_social_values_deep(67, {})["체면"] == 0.7
    # 매핑 키 없는 세대(밀레니얼/X세대)는 빈 dict.
    assert s._sample_social_values_deep(35, {}) == {}


def test_generation_mapping() -> None:
    assert _generation_of_age(25) == "Z세대"
    assert _generation_of_age(35) == "밀레니얼"
    assert _generation_of_age(50) == "X세대"
    assert _generation_of_age(67) == "베이비부머"


def test_social_values_lines_render_and_fallback() -> None:
    bare = Persona(persona_id="P", age=25, gender="F", region="서울", ocean={})
    assert _social_values_lines(bare) == ""
    p = Persona(
        persona_id="P",
        age=25,
        gender="F",
        region="서울",
        ocean={},
        social_values_deep={"체면": 0.7},
    )
    line = _social_values_lines(p)
    assert "체면" in line and "70%" in line


def test_data_status_social_values_pending() -> None:
    assert "pending" in loader.data_status()["social_values_deep"]
