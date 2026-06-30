# 🅱 HITL rank/package 분리 — AWAITING_SELECTION → PROPOSED, membership 거부, idx 순서 보존

from domain.management.agents.outcome import OutcomeKind
from domain.management.agents.regeneration import CreativeCandidate


class _StubGen:
    def __init__(self, cands):
        self._cands = cands

    async def generate(self, diagnosis, count):
        return self._cands[:count]


async def test_creative_success_returns_awaiting_selection(
    make_agent, make_diagnosis, make_context
):
    cands = [CreativeCandidate(candidate_id="c0", copy="카피", idx=0, image_ref="k")]
    agent = make_agent(generator=_StubGen(cands))
    out = await agent.rank(make_diagnosis(), make_context(action_type="REPLACE_CREATIVE"))
    assert out.kind is OutcomeKind.AWAITING_SELECTION
    assert out.selection_token is not None
    assert out.proposal is None
    assert "sim_score" not in out.candidates[0]


async def test_rank_preserves_4_3_idx_order(make_agent, make_diagnosis, make_context):
    cands = [
        CreativeCandidate(candidate_id="c0", copy="첫째", idx=0, image_ref="k0"),
        CreativeCandidate(candidate_id="c1", copy="둘째", idx=1, image_ref="k1"),
    ]
    agent = make_agent(generator=_StubGen(cands))
    out = await agent.rank(make_diagnosis(), make_context(action_type="REPLACE_CREATIVE"))
    assert [c["candidate_id"] for c in out.candidates] == ["c0", "c1"]
    assert [c["idx"] for c in out.candidates] == [0, 1]


async def test_package_with_selected_id_returns_proposed(make_agent, make_diagnosis, make_context):
    cands = [CreativeCandidate(candidate_id="c0", copy="카피", idx=0, image_ref="k")]
    agent = make_agent(generator=_StubGen(cands))
    dx, ctx = make_diagnosis(), make_context(action_type="REPLACE_CREATIVE")
    ranked = await agent.rank(dx, ctx)
    out = await agent.package(ranked.selection_token, tenant_id="org_1", selected_id="c0")
    assert out.kind is OutcomeKind.PROPOSED
    assert out.proposal.evidence_metrics["selected_candidate_id"] == "c0"
    # 후보 evidence에 채점 흔적 없음
    assert "sim_score" not in out.proposal.evidence_metrics["candidates"][0]


async def test_package_rejects_non_member(make_agent, make_diagnosis, make_context):
    cands = [CreativeCandidate(candidate_id="c0", copy="카피", idx=0, image_ref="k")]
    agent = make_agent(generator=_StubGen(cands))
    ranked = await agent.rank(make_diagnosis(), make_context(action_type="REPLACE_CREATIVE"))
    out = await agent.package(ranked.selection_token, tenant_id="org_1", selected_id="cX")
    assert out.kind is OutcomeKind.INPUT_INVALID


async def test_package_rejects_wrong_tenant(make_agent, make_diagnosis, make_context):
    cands = [CreativeCandidate(candidate_id="c0", copy="카피", idx=0, image_ref="k")]
    agent = make_agent(generator=_StubGen(cands))
    ranked = await agent.rank(make_diagnosis(), make_context(action_type="REPLACE_CREATIVE"))
    out = await agent.package(ranked.selection_token, tenant_id="other_org", selected_id="c0")
    assert out.kind is OutcomeKind.INPUT_INVALID


async def test_rank_failure_returns_failed(make_agent, make_diagnosis, make_context):
    class _Boom:
        async def generate(self, diagnosis, count):
            raise RuntimeError("불의의 사고")

    # 생성 실패는 재시도 후 빈손 → CREATIVE_UNAVAILABLE이지 FAILED가 아니다.
    # FAILED는 그래프 자체가 터질 때 — selection_store.save에서 예외를 강제한다.
    class _ExplodingStore:
        async def save(self, rnd):
            raise RuntimeError("store down")

        async def claim(self, token, *, tenant_id, selected_id):
            raise RuntimeError("store down")

    from domain.management.agents.regeneration import RemediationAgent

    agent = RemediationAgent(
        generator=_StubGen(
            [CreativeCandidate(candidate_id="c0", copy="카피", idx=0, image_ref="k")]
        ),
        selection_store=_ExplodingStore(),
    )
    out = await agent.rank(make_diagnosis(), make_context(action_type="REPLACE_CREATIVE"))
    assert out.kind is OutcomeKind.FAILED
