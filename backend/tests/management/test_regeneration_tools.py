"""🅱 재생성 tool 구현체 테스트 — 생성·시뮬·미리보기 + 폴백 (contracts·B 내부만 import)."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from domain.management.agents.regeneration import (
    BANNED_EXPRESSIONS,
    MAX_CANDIDATES,
    CreativeCandidate,
    RegenerationAgent,
)
from domain.management.agents.regeneration_tools import (
    HeuristicSimulationScorer,
    LLMCreativeGenerator,
    MetaPreviewTool,
    SsrSimulationScorer,
    TemplateCreativeGenerator,
    build_regeneration_agent,
)
from domain.management.contracts.enums import (
    ActionTier,
    AnomalyType,
    DiagnosisSource,
    DiagnosisStatus,
)
from domain.management.contracts.schemas import DiagnosisResult, verify_proposal_hash
from tests.management.helpers import NOW, POLICY_VERSION, STATE_VERSION


def make_diagnosis(anomaly: AnomalyType = AnomalyType.BID_LOSS) -> DiagnosisResult:
    return DiagnosisResult(
        diagnosis_id="dx-tools-1",
        tenant_id="org-1111",
        campaign_id="camp-001",
        anomaly_type=anomaly,
        source=DiagnosisSource.AGENT,
        hypothesis="입찰 패배 — 소재 경쟁력 저하",
        confidence=0.7,
        evidence_metrics={"cpm_surge_ratio": 1.6},
        metrics_as_of=datetime(2026, 6, 24, 9, 0, tzinfo=UTC),
        status=DiagnosisStatus.CONFIRMED,
    )


class FakeChat:
    """ChatModelLike fake — 고정 content 응답."""

    def __init__(self, content: str):
        self.content = content
        self.calls = 0

    async def ainvoke(self, input):  # noqa: A002 — LangChain 시그니처
        self.calls += 1
        return SimpleNamespace(content=self.content)


# ── 생성: 템플릿 폴백 ────────────────────────────────────────────────


async def test_template_generator_deterministic_and_capped():
    generator = TemplateCreativeGenerator()
    first = await generator.generate(make_diagnosis(), count=2)
    second = await generator.generate(make_diagnosis(), count=2)

    assert len(first) == 2
    assert [c.ad_copy for c in first] == [c.ad_copy for c in second]  # 게이트 #10 재현성
    assert all(not any(banned in c.ad_copy for banned in BANNED_EXPRESSIONS) for c in first)


async def test_template_generator_varies_by_anomaly_type():
    generator = TemplateCreativeGenerator()
    bid = await generator.generate(make_diagnosis(AnomalyType.BID_LOSS), MAX_CANDIDATES)
    quality = await generator.generate(make_diagnosis(AnomalyType.QUALITY_DEGRADED), MAX_CANDIDATES)
    fallback = await generator.generate(make_diagnosis(AnomalyType.SCHEDULE_GAP), MAX_CANDIDATES)

    assert {c.ad_copy for c in bid} != {c.ad_copy for c in quality}
    assert len(fallback) == MAX_CANDIDATES  # 미등록 유형은 기본 템플릿


# ── 생성: LLM ────────────────────────────────────────────────────────


async def test_llm_generator_parses_json_array():
    llm = FakeChat('["지금 만나는 여름 신상", "오늘만 특가 혜택"]')
    generator = LLMCreativeGenerator(llm=llm)

    candidates = await generator.generate(make_diagnosis(), count=2)

    assert [c.ad_copy for c in candidates] == ["지금 만나는 여름 신상", "오늘만 특가 혜택"]
    assert all(c.candidate_id.startswith("gen_") for c in candidates)


async def test_llm_generator_strips_code_fences_and_dict_items():
    content = '```json\n[{"ad_copy": "후기로 증명된 선택"}]\n```'
    generator = LLMCreativeGenerator(llm=FakeChat(content))

    candidates = await generator.generate(make_diagnosis(), count=3)

    assert [c.ad_copy for c in candidates] == ["후기로 증명된 선택"]


async def test_llm_generator_caps_at_max_candidates():
    llm = FakeChat('["a1", "a2", "a3", "a4", "a5"]')
    generator = LLMCreativeGenerator(llm=llm)

    candidates = await generator.generate(make_diagnosis(), count=10)

    assert len(candidates) == MAX_CANDIDATES  # P6 상한은 tool에서도 강제


async def test_llm_generator_invalid_payload_raises_for_agent_retry():
    generator = LLMCreativeGenerator(llm=FakeChat("죄송합니다, JSON을 만들 수 없어요"))
    with pytest.raises(ValueError):
        await generator.generate(make_diagnosis(), count=2)

    generator = LLMCreativeGenerator(llm=FakeChat('{"not": "an array"}'))
    with pytest.raises(ValueError):
        await generator.generate(make_diagnosis(), count=2)


# ── 시뮬 채점: 휴리스틱 폴백 ─────────────────────────────────────────


async def test_heuristic_scorer_deterministic_and_bounded():
    scorer = HeuristicSimulationScorer()
    candidate = CreativeCandidate(candidate_id="c1", ad_copy="지금 가장 인기있는 신제품")

    first = await scorer.score(candidate)
    second = await scorer.score(candidate)

    assert first == second
    assert 0.0 <= first <= 1.0


async def test_heuristic_scorer_prefers_cta_over_banned():
    scorer = HeuristicSimulationScorer()
    cta = await scorer.score(CreativeCandidate(candidate_id="c1", ad_copy="오늘만 특가 베스트"))
    banned = await scorer.score(
        CreativeCandidate(candidate_id="c2", ad_copy="효과 100% 보장 다이어트")
    )

    assert cta > banned


# ── 시뮬 채점: SSR 어댑터 ────────────────────────────────────────────


class FakeSsr:
    def __init__(self, mean):
        self._mean = mean

    async def score(self, exposure_text: str):
        return {"purchase_intent": SimpleNamespace(mean=self._mean)}


async def test_ssr_scorer_normalizes_to_unit_interval():
    scorer = SsrSimulationScorer(FakeSsr(mean=3.8))
    candidate = CreativeCandidate(candidate_id="c1", ad_copy="아무 카피")

    assert await scorer.score(candidate) == pytest.approx((3.8 - 1.0) / 4.0)


async def test_ssr_scorer_clamps_and_accepts_dict_distribution():
    class DictSsr:
        async def score(self, exposure_text: str):
            return {"purchase_intent": {"mean": 9.9}}

    scorer = SsrSimulationScorer(DictSsr())
    assert await scorer.score(CreativeCandidate(candidate_id="c1", ad_copy="x")) == 1.0


# ── 미리보기 ─────────────────────────────────────────────────────────


async def test_preview_tool_uses_writer_readonly_method():
    tool = MetaPreviewTool()
    with_image = CreativeCandidate(candidate_id="c1", ad_copy="x", image_ref="img_77")
    without_image = CreativeCandidate(candidate_id="c2", ad_copy="y")

    assert "img_77" in await tool.preview(with_image)
    assert "c2" in await tool.preview(without_image)


# ── 통합: 기본 tool 체인으로 agent 끝까지 관통 ───────────────────────


async def test_default_tool_chain_produces_finalized_proposal():
    from domain.management.agents.regeneration import RegenerationContext

    agent = build_regeneration_agent()  # 키 없는 환경 → Template + Heuristic + Preview
    assert isinstance(agent, RegenerationAgent)

    context = RegenerationContext(
        ad_account_id="act_001",
        target_object_ids=("camp-001",),
        budget_before_krw=50_000,
        budget_after_krw=50_000,
        run_days=7,
        expected_state_version=STATE_VERSION,
        approval_policy_version=POLICY_VERSION,
        action_type="REPLACE_CREATIVE",
    )
    proposal = await agent.propose(make_diagnosis(), context)

    assert proposal is not None
    assert verify_proposal_hash(proposal)  # finalize까지 완료
    assert proposal.action_tier is ActionTier.TIER_3  # REPLACE_CREATIVE → 정책표 라벨
    candidates = proposal.evidence_metrics["candidates"]
    assert 1 <= len(candidates) <= MAX_CANDIDATES
    selected = proposal.evidence_metrics["selected_candidate_id"]
    assert selected in {c["candidate_id"] for c in candidates}
    best = max(candidates, key=lambda c: c["sim_score"])
    assert best["preview_url"] is not None  # 최선 후보에 미리보기 부착
    assert proposal.metrics_as_of == make_diagnosis().metrics_as_of
    assert proposal.expires_at > NOW
