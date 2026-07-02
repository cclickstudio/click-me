# Composer: AskResult→봉투 매핑 — 서술 가드·슬롯 순서·actionbar 변경액션 비활성(MVP)
from domain.management.assistant.chat_cards import CardKind, TurnOrigin, validate_card
from domain.management.assistant.composer import compose_turn
from domain.management.assistant.contracts import AskResult, Citation, SuggestedAction


def _kinds(env):
    return [c.kind for c in env.cards]


def _card(env, kind):
    return next(c for c in env.cards if c.kind == kind)


def _pause(requires_approval=False, tier="TIER_1"):
    return SuggestedAction(
        action_type="PAUSE_CAMPAIGN",
        target_campaign_id="camp_1",
        tier=tier,
        requires_approval=requires_approval,
        rationale="런레이트 초과",
    )


def test_read_only_answer_has_conclusion_no_action_cards():
    res = AskResult(
        answer="예산은 정상 페이스입니다.", citations=[Citation(kind="live", source="live_budget")]
    )
    env = compose_turn(res, turn_id="t1")
    assert env.turn_id == "t1"
    assert env.origin == TurnOrigin.USER
    assert env.conclusion == "예산은 정상 페이스입니다."
    assert CardKind.EVIDENCE in _kinds(env)
    assert CardKind.RESULT not in _kinds(env)
    assert CardKind.ACTIONBAR not in _kinds(env)


def test_evidence_card_carries_citations():
    res = AskResult(
        answer="x", citations=[Citation(kind="kb", source="meta_ad_policy.md", title="Meta 정책")]
    )
    env = compose_turn(res, turn_id="t1")
    ev = _card(env, CardKind.EVIDENCE)
    assert ev.payload.type == "rag_citations"
    assert ev.payload.version == 1
    assert ev.payload.data["citations"][0]["source"] == "meta_ad_policy.md"


def test_action_intent_builds_result_review_actionbar_in_order():
    res = AskResult(answer="일시중지를 제안합니다.", suggested_action=_pause())
    env = compose_turn(res, turn_id="t2")
    assert _kinds(env) == [
        CardKind.RESULT,
        CardKind.REVIEW,
        CardKind.ACTIONBAR,
    ]  # 슬롯 순서 + actionbar 마지막
    result = _card(env, CardKind.RESULT)
    assert result.payload.type == "action_proposal"
    assert result.payload.data["action_type"] == "PAUSE_CAMPAIGN"


def test_conclusion_strips_execution_directive():
    # 불변식 ③ — 결론은 서술만. "지금 실행하세요" 같은 지시 문장 제거.
    res = AskResult(answer="예산이 초과됐습니다. 지금 실행하세요.", suggested_action=_pause())
    env = compose_turn(res, turn_id="t3")
    assert "실행하세요" not in env.conclusion
    assert "예산이 초과됐습니다." in env.conclusion


def test_directive_only_answer_degrades_to_neutral():
    # 답변이 지시문뿐이면 원문을 흘리지 말고 중립 강등(P1 — 원문 재노출 금지).
    res = AskResult(answer="지금 실행하세요.", suggested_action=_pause())
    env = compose_turn(res, turn_id="t3b")
    assert "실행하세요" not in env.conclusion
    assert env.conclusion == "자세한 내용은 아래 카드를 확인하세요."


def test_result_card_marks_draft_not_executable():
    # result는 draft 단계 — "바로 실행 가능"이 아님을 data로 명시.
    res = AskResult(answer="제안합니다.", suggested_action=_pause())
    env = compose_turn(res, turn_id="t3c")
    data = _card(env, CardKind.RESULT).payload.data
    assert data["stage"] == "draft"
    assert data["executable"] is False


def test_mutating_actions_disabled_pending_execute_api():
    # MVP — 변경 액션은 실행 API 미연결이라 비활성, proposal_draft만 실림(불변식 ①).
    res = AskResult(answer="일시중지를 제안합니다.", suggested_action=_pause())
    env = compose_turn(res, turn_id="t4")
    actions = {a["id"]: a for a in _card(env, CardKind.ACTIONBAR).payload.data["actions"]}
    assert actions["regenerate"]["enabled"] is True
    for aid in ("approve", "execute"):
        assert actions[aid]["enabled"] is False
        assert actions[aid]["wired"] is False
        assert actions[aid]["kind"] == "mutating"
        assert actions[aid]["proposal_draft"]["action_type"] == "PAUSE_CAMPAIGN"


def test_review_records_decision_without_enabling_execute():
    # auto_ok든 needs_approval이든 MVP에선 execute가 자동 활성되지 않는다.
    auto = compose_turn(
        AskResult(answer="x", suggested_action=_pause(requires_approval=False)), turn_id="t5"
    )
    needs = compose_turn(
        AskResult(
            answer="x",
            suggested_action=_pause(requires_approval=True, tier="TIER_3"),
        ),
        turn_id="t6",
    )
    assert _card(auto, CardKind.REVIEW).payload.data["decision"] == "auto_ok"
    assert _card(needs, CardKind.REVIEW).payload.data["decision"] == "needs_approval"
    for env in (auto, needs):
        ab = {a["id"]: a for a in _card(env, CardKind.ACTIONBAR).payload.data["actions"]}
        assert ab["execute"]["enabled"] is False  # 실행 정본은 실행 API


def test_all_cards_are_registered():
    res = AskResult(
        answer="x",
        citations=[Citation(kind="live", source="live_budget")],
        suggested_action=_pause(),
    )
    env = compose_turn(res, turn_id="t7")
    for card in env.cards:
        validate_card(card)  # 미등록이면 raise
