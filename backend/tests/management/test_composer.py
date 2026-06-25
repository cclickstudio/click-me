# compose_card: AskResult→ChatCard 섹션 매핑 — 순서·생략·서술 가드·trace
from domain.management.assistant.composer import compose_card
from domain.management.assistant.contracts import AskResult, Citation, SuggestedAction


def _kinds(card):
    return [s.kind for s in card.sections]


def _section(card, kind):
    return next(s for s in card.sections if s.kind == kind)


def _pause(requires_approval=False, tier="TIER_1"):
    return SuggestedAction(
        action_type="PAUSE_CAMPAIGN",
        target_campaign_id="camp_1",
        tier=tier,
        requires_approval=requires_approval,
        rationale="런레이트 초과",
    )


def test_read_only_no_action_has_summary_and_metrics_only():
    res = AskResult(
        answer="예산은 정상 페이스입니다.",
        evidence={
            "this_month_spent_krw": 29082,
            "runrate_projection_krw": 34898,
            "period": "2026-06",
        },
    )
    card = compose_card(res, turn_id="t1")
    assert card.type == "management"
    assert _kinds(card) == ["summary", "metrics"]
    assert _section(card, "summary").text == "예산은 정상 페이스입니다."
    assert card.trace.turn_id == "t1"


def test_metrics_section_formats_krw_and_period_title():
    res = AskResult(answer="x", evidence={"account_balance_krw": 9, "period": "2026-06"})
    card = compose_card(res, turn_id="t1")
    metrics = _section(card, "metrics")
    assert metrics.title == "핵심 지표 (2026-06)"
    assert metrics.items[0].value == "9원"


def test_empty_evidence_omits_metrics():
    card = compose_card(AskResult(answer="x", evidence={}), turn_id="t1")
    assert "metrics" not in _kinds(card)


def test_action_builds_proposal_review_in_order():
    res = AskResult(
        answer="일시중지를 제안합니다.",
        citations=[Citation(kind="live", source="live_budget")],
        suggested_action=_pause(),
    )
    card = compose_card(res, turn_id="t2")
    assert _kinds(card) == ["summary", "proposal", "review", "evidence"]
    assert _section(card, "proposal").action_type == "PAUSE_CAMPAIGN"


def test_review_decision_reflects_requires_approval():
    auto = compose_card(
        AskResult(answer="x", suggested_action=_pause(requires_approval=False)), turn_id="t3"
    )
    needs = compose_card(
        AskResult(answer="x", suggested_action=_pause(requires_approval=True, tier="TIER_3")),
        turn_id="t4",
    )
    assert _section(auto, "review").decision == "auto_ok"
    assert _section(needs, "review").decision == "needs_approval"


def test_badges_present_for_action():
    card = compose_card(AskResult(answer="x", suggested_action=_pause()), turn_id="t5")
    assert {b.label for b in card.badges} == {"TIER_1", "draft", "auto_ok"}


def test_no_badges_for_read_only():
    card = compose_card(AskResult(answer="x"), turn_id="t6")
    assert card.badges == []


def test_conclusion_strips_execution_directive():
    res = AskResult(answer="예산이 초과됐습니다. 지금 실행하세요.", suggested_action=_pause())
    card = compose_card(res, turn_id="t7")
    text = next(s for s in card.sections if s.kind == "summary").text
    assert "실행하세요" not in text
    assert "예산이 초과됐습니다." in text


def test_evidence_section_carries_citations_and_tools():
    res = AskResult(
        answer="x",
        citations=[Citation(kind="kb", source="meta_ad_policy.md", title="Meta 정책")],
        used_tools=["live_budget"],
    )
    card = compose_card(res, turn_id="t8")
    ev = next(s for s in card.sections if s.kind == "evidence")
    assert ev.citations[0].source == "meta_ad_policy.md"
    assert ev.used_tools == ["live_budget"]
