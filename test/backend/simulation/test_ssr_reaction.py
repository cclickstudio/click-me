# SSR 점수화 재배선 단위 테스트 — 앵커·프롬프트 확장·SSR 데코레이터·wiring 플래그(전부 무API fake)
from __future__ import annotations

import pytest

from core.schemas import ScoreDistribution
from domain.simulation.adapters.gemini.reaction import (
    build_persona_reaction,
    build_reaction_prompt,
)
from domain.simulation.adapters.ssr_reaction import SSRScoringReactor, build_ssr_input_text
from domain.simulation.contracts.schemas import AdInterpretation, Aisas, Persona, PersonaReaction
from domain.simulation.wiring import _ssr_scoring_enabled
from tools.simulation.anchors import ANCHOR_STATEMENTS, SCORE_RANGES


def _persona() -> Persona:
    return Persona(persona_id="p1", age=34, gender="여성", region="서울", ocean={"openness": 0.5})


def _ad() -> AdInterpretation:
    return AdInterpretation(ad_id="A", detected_industry="식품", detected_message="신제품 출시")


def _reaction(**overrides) -> PersonaReaction:
    base = {
        "persona_id": "p1",
        "aisas": Aisas(attention=True, interest=True),
        "purchase_intent": 3,
        "trust": 3,
        "utterance": "음, 그냥 그렇네.",
    }
    base.update(overrides)
    return PersonaReaction(**base)


def _dist(mean: float) -> ScoreDistribution:
    return ScoreDistribution(mean=mean, std=0.5, p10=1.0, p90=5.0, raw_probs=[0.2] * 5)


# ── 앵커 ──────────────────────────────────────────────────────────────


def test_anchors_have_purchase_intent_and_trust() -> None:
    for dim in ("purchase_intent", "trust"):
        assert dim in ANCHOR_STATEMENTS, f"{dim} 앵커 누락"
        assert len(ANCHOR_STATEMENTS[dim]) == 5  # 1~5점 5단계
        assert SCORE_RANGES[dim] == (1.0, 5.0)


# ── 프롬프트 확장(플래그) ─────────────────────────────────────────────


def test_prompt_default_has_no_reaction_text() -> None:
    prompt = build_reaction_prompt(_persona(), _ad(), None)
    assert "reaction_text" not in prompt  # 기본 off — 현행 프롬프트 보존


def test_prompt_with_reaction_text_includes_fields() -> None:
    prompt = build_reaction_prompt(_persona(), _ad(), None, with_reaction_text=True)
    assert '"reaction_text"' in prompt
    for field in ("first_impression", "supporting_thoughts", "opposing_thoughts", "final_attitude"):
        assert field in prompt
    # 기존 정수 필드도 유지(하위호환 — QA·폴백 경로)
    assert '"purchase_intent"' in prompt and '"trust"' in prompt


def test_build_persona_reaction_parses_reaction_text() -> None:
    data = {
        "aisas": {"attention": True},
        "purchase_intent": 4,
        "trust": 3,
        "reaction_text": {"first_impression": "눈에 띈다", "final_attitude": "사볼까"},
    }
    r = build_persona_reaction(_persona(), None, data)
    assert r.reaction_text == data["reaction_text"]
    # 없으면 None(현행 동작)
    r2 = build_persona_reaction(_persona(), None, {"aisas": {}, "purchase_intent": 3, "trust": 3})
    assert r2.reaction_text is None


# ── SSR 입력 텍스트 ───────────────────────────────────────────────────


def test_build_ssr_input_text_prefers_reaction_text() -> None:
    r = _reaction(
        reaction_text={
            "first_impression": "색감이 눈에 띈다",
            "supporting_thoughts": ["가격이 착하다"],
            "opposing_thoughts": ["브랜드를 모른다"],
            "final_attitude": "한번 사볼 만하다",
        }
    )
    text = build_ssr_input_text(r)
    assert "색감이 눈에 띈다" in text and "한번 사볼 만하다" in text
    assert "가격이 착하다" in text and "브랜드를 모른다" in text


def test_build_ssr_input_text_falls_back_to_utterance() -> None:
    r = _reaction(perceived_message="신제품 광고")
    text = build_ssr_input_text(r)
    assert "음, 그냥 그렇네." in text and "신제품 광고" in text


# ── SSR 데코레이터 ────────────────────────────────────────────────────


class _FakeInner:
    def __init__(self, reaction: PersonaReaction) -> None:
        self._reaction = reaction
        self.version = "fake-inner"

    async def react(self, persona, ad) -> PersonaReaction:
        return self._reaction


class _FakeScorer:
    def __init__(self, dists: dict[str, ScoreDistribution]) -> None:
        self._dists = dists
        self.precompute_calls = 0

    async def precompute_anchors(self) -> None:
        self.precompute_calls += 1

    async def score(self, text: str) -> dict[str, ScoreDistribution]:
        return self._dists


async def test_ssr_reactor_overwrites_scores_with_distribution() -> None:
    inner = _FakeInner(_reaction(reaction_text={"final_attitude": "사고 싶다"}))
    scorer = _FakeScorer({"purchase_intent": _dist(4.4), "trust": _dist(1.2)})
    reactor = SSRScoringReactor(inner, scorer)

    r = await reactor.react(_persona(), _ad())

    assert r.purchase_intent == 4 and r.trust == 1  # 분포 평균 반올림(1~5 클램프)
    assert r.purchase_intent_dist == _dist(4.4)
    assert r.trust_dist == _dist(1.2)


async def test_ssr_reactor_precomputes_anchors_once() -> None:
    inner = _FakeInner(_reaction())
    scorer = _FakeScorer({"purchase_intent": _dist(3.0), "trust": _dist(3.0)})
    reactor = SSRScoringReactor(inner, scorer)

    await reactor.react(_persona(), _ad())
    await reactor.react(_persona(), _ad())

    assert scorer.precompute_calls == 1  # lazy 1회


async def test_ssr_reactor_keeps_llm_scores_when_dims_missing() -> None:
    inner = _FakeInner(_reaction(purchase_intent=2, trust=5))
    scorer = _FakeScorer({})  # SSR 차원 미산출 — LLM 정수 유지
    reactor = SSRScoringReactor(inner, scorer)

    r = await reactor.react(_persona(), _ad())

    assert r.purchase_intent == 2 and r.trust == 5
    assert r.purchase_intent_dist is None and r.trust_dist is None


# ── 집계기 population 분포 합성 ───────────────────────────────────────


def test_aggregator_synthesizes_ssr_population_dist() -> None:
    from domain.simulation.tools.aggregation.aggregator import BasicAggregator

    d1 = ScoreDistribution(mean=4.0, std=0.5, p10=3.0, p90=5.0, raw_probs=[0.0, 0.0, 0.2, 0.4, 0.4])
    d2 = ScoreDistribution(mean=2.0, std=0.5, p10=1.0, p90=3.0, raw_probs=[0.4, 0.4, 0.2, 0.0, 0.0])
    reactions = [
        _reaction(purchase_intent=4, purchase_intent_dist=d1, trust_dist=d1, weight=1.0),
        _reaction(purchase_intent=2, purchase_intent_dist=d2, trust_dist=d2, weight=3.0),
    ]

    agg = BasicAggregator().aggregate(reactions)

    probs = agg.payload["ssr_purchase_intent_probs"]
    # 가중 평균: (1*d1 + 3*d2) / 4
    assert probs == pytest.approx([0.3, 0.3, 0.2, 0.1, 0.1])
    assert sum(probs) == pytest.approx(1.0)
    assert agg.payload["ssr_trust_probs"] == pytest.approx([0.3, 0.3, 0.2, 0.1, 0.1])
    assert agg.payload["ssr_dist_n"] == 2


def test_aggregator_payload_unchanged_without_ssr_dists() -> None:
    from domain.simulation.tools.aggregation.aggregator import BasicAggregator

    agg = BasicAggregator().aggregate([_reaction(), _reaction()])

    assert "ssr_purchase_intent_probs" not in agg.payload  # SSR 미사용 시 payload 무변화
    assert "ssr_trust_probs" not in agg.payload


# ── wiring 플래그 ─────────────────────────────────────────────────────


def test_ssr_scoring_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIMULATION_SCORING", raising=False)
    assert _ssr_scoring_enabled() is False  # 기본 off — 현행 동작 보존
    monkeypatch.setenv("SIMULATION_SCORING", "ssr")
    assert _ssr_scoring_enabled() is True
    monkeypatch.setenv("SIMULATION_SCORING", "llm")
    assert _ssr_scoring_enabled() is False
