# 🅱 시안 불가 시 비크리에이티브 전략 fallback — 단위 매핑 + rank() 통합
from domain.management.agents.outcome import OutcomeKind, OutcomeReason
from domain.management.agents.regeneration import fallback_action
from domain.management.agents.regeneration_tools import GeneratorInputError
from domain.management.contracts.enums import AnomalyType


def test_quality_degraded_falls_back_to_pause():
    action, human = fallback_action(AnomalyType.QUALITY_DEGRADED, conservative=True)
    assert action == "PAUSE_CAMPAIGN"
    assert human is False


def test_quality_degraded_aggressive_escalates_to_human():
    action, human = fallback_action(AnomalyType.QUALITY_DEGRADED, conservative=False)
    assert action is None
    assert human is True


def test_audience_narrow_falls_back_to_expand():
    action, human = fallback_action(AnomalyType.AUDIENCE_TOO_NARROW, conservative=True)
    assert action == "EXPAND_AUDIENCE"
    assert human is False


def test_unmapped_anomaly_has_no_fallback():
    action, human = fallback_action(AnomalyType.BID_LOSS, conservative=True)
    assert action is None
    assert human is False


class _EmptyGen:
    async def generate(self, diagnosis, count):
        return []  # 4-3 빈손 → CREATIVE_UNAVAILABLE 트리거


async def test_creative_unavailable_conservative_produces_pause_proposal(
    make_agent, make_diagnosis, make_context
):
    agent = make_agent(generator=_EmptyGen())
    dx = make_diagnosis(anomaly=AnomalyType.QUALITY_DEGRADED)
    ctx = make_context(action_type="REPLACE_CREATIVE")
    out = await agent.rank(dx, ctx)
    assert out.kind is OutcomeKind.PROPOSED
    assert out.proposal.action_type == "PAUSE_CAMPAIGN"
    assert out.reason is OutcomeReason.CREATIVE_FALLBACK_PAUSE


async def test_creative_unavailable_audience_produces_expand_proposal(
    make_agent, make_diagnosis, make_context
):
    agent = make_agent(generator=_EmptyGen())
    dx = make_diagnosis(anomaly=AnomalyType.AUDIENCE_TOO_NARROW)
    ctx = make_context(action_type="CREATE_CAMPAIGN")
    out = await agent.rank(dx, ctx)
    assert out.kind is OutcomeKind.PROPOSED
    assert out.proposal.action_type == "EXPAND_AUDIENCE"
    assert out.reason is OutcomeReason.CREATIVE_FALLBACK_EXPAND


# ── FIX 3 — 세분화된 CREATIVE_UNAVAILABLE reason codes ─────────────────


class _GeneratorInputErrorGen:
    async def generate(self, diagnosis, count):
        raise GeneratorInputError("existing_ad_s3_key 없음")


class _TimeoutGen:
    def __init__(self, retries: int = 1):
        self._retries = retries
        self._calls = 0

    async def generate(self, diagnosis, count):
        self._calls += 1
        raise TimeoutError("생성 타임아웃")


class _OtherErrorGen:
    async def generate(self, diagnosis, count):
        raise RuntimeError("예기치 못한 generator 오류")


class _GuardWipeoutGen:
    """guard에서 전부 제거되도록 금지 표현이 있는 후보만 반환한다."""

    async def generate(self, diagnosis, count):
        from domain.management.agents.regeneration import CreativeCandidate

        return [
            CreativeCandidate(
                candidate_id="bad1",
                copy="100% 보장 다이어트",
                idx=0,
                image_ref="s3/bad1.png",
            )
        ]


async def test_generator_input_error_emits_missing_creative_input(
    make_agent, make_diagnosis, make_context
):
    """FIX 3 — GeneratorInputError → MISSING_CREATIVE_INPUT."""
    agent = make_agent(generator=_GeneratorInputErrorGen())
    # conservative fallback이 있으면 PROPOSED/PAUSE — fallback이 없는 경우도 확인
    # BID_LOSS는 fallback 없음 → CREATIVE_UNAVAILABLE
    dx2 = make_diagnosis(anomaly=AnomalyType.BID_LOSS)
    ctx2 = make_context(action_type="REPLACE_CREATIVE")
    out2 = await agent.rank(dx2, ctx2)
    assert out2.kind is OutcomeKind.CREATIVE_UNAVAILABLE
    assert out2.reason is OutcomeReason.MISSING_CREATIVE_INPUT


async def test_timeout_error_emits_generator_timeout(make_agent, make_diagnosis, make_context):
    """FIX 3 — TimeoutError → GENERATOR_TIMEOUT."""
    agent = make_agent(generator=_TimeoutGen())
    dx = make_diagnosis(anomaly=AnomalyType.BID_LOSS)
    ctx = make_context(action_type="REPLACE_CREATIVE")
    out = await agent.rank(dx, ctx)
    assert out.kind is OutcomeKind.CREATIVE_UNAVAILABLE
    assert out.reason is OutcomeReason.GENERATOR_TIMEOUT


async def test_guard_wipeout_emits_guard_wipeout(make_agent, make_diagnosis, make_context):
    """FIX 3 — guard 전멸 → GUARD_WIPEOUT."""
    agent = make_agent(generator=_GuardWipeoutGen())
    dx = make_diagnosis(anomaly=AnomalyType.BID_LOSS)
    ctx = make_context(action_type="REPLACE_CREATIVE")
    out = await agent.rank(dx, ctx)
    assert out.kind is OutcomeKind.CREATIVE_UNAVAILABLE
    assert out.reason is OutcomeReason.GUARD_WIPEOUT


async def test_empty_generator_emits_generator_empty(make_agent, make_diagnosis, make_context):
    """FIX 3 — 예외 없이 빈 목록 → GENERATOR_EMPTY."""
    agent = make_agent(generator=_EmptyGen())
    dx = make_diagnosis(anomaly=AnomalyType.BID_LOSS)
    ctx = make_context(action_type="REPLACE_CREATIVE")
    out = await agent.rank(dx, ctx)
    assert out.kind is OutcomeKind.CREATIVE_UNAVAILABLE
    assert out.reason is OutcomeReason.GENERATOR_EMPTY
