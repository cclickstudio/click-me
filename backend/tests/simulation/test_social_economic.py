# 사회경제·심리 prior(MDIS) 슬롯 테스트 — 세대별 값 적용·graceful·반응 힌트 렌더.
from __future__ import annotations

from domain.simulation.adapters.gemini.reaction import _social_economic_lines
from domain.simulation.contracts.schemas import PanelSpec, Persona
from domain.simulation.data.simulation import loader
from domain.simulation.tools.sampling.persona_sampler import PersonaSampler

_FIXTURE = {"generation_specific": {"Z세대": {"생활만족": 0.66, "사회참여": 0.47}}}


def test_persona_gets_social_economic_from_real_data() -> None:
    # 실데이터 적재 → 페르소나 social_economic 비어있지 않고 0~1 범위.
    personas = PersonaSampler().sample(PanelSpec(size=30, seed=1))
    assert all(p.social_economic for p in personas)
    assert all(0.0 <= v <= 1.0 for p in personas for v in p.social_economic.values())


def test_sample_uses_generation_base() -> None:
    s = PersonaSampler(social_economic=_FIXTURE)
    assert s._sample_social_economic(25) == {"생활만족": 0.66, "사회참여": 0.47}
    assert s._sample_social_economic(50) == {}  # X세대 키 없음 → {}


def test_empty_data_is_graceful() -> None:
    s = PersonaSampler(social_economic={"generation_specific": {}})
    assert s._sample_social_economic(25) == {}


def test_social_economic_lines_render_and_fallback() -> None:
    bare = Persona(persona_id="P", age=25, gender="F", region="서울", ocean={})
    assert _social_economic_lines(bare) == ""
    p = Persona(
        persona_id="P",
        age=25,
        gender="F",
        region="서울",
        ocean={},
        social_economic={"생활만족": 0.66},
    )
    line = _social_economic_lines(p)
    assert "생활만족" in line and "66%" in line


def test_data_status_social_economic_real() -> None:
    assert loader.data_status()["social_economic"].startswith("real")
