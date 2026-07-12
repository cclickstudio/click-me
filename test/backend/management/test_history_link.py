# history_link 콜백 계약 — payload·actor 매핑·미귀속 생략·CREATE_CAMPAIGN 분기 고정
"""record_execution·resolve 함수를 monkeypatch로 캡처해 DB 없이 계약을 고정한다.

executor가 콜백을 '언제' 부르는지는 test_history_recorder.py 소관 — 여기는 콜백이
불렸을 때 '무엇을' 기록하는지만 본다.
"""

from uuid import uuid4

from management.helpers import NOW, make_action, make_proposal

import domain.management.history_link as hl
from domain.management.contracts.enums import ResultStatus
from domain.management.contracts.schemas import AUTO_APPROVER, ActionResult
from domain.management.history_link import build_history_recorder


def _result(status: ResultStatus = ResultStatus.SUCCESS) -> ActionResult:
    return ActionResult(
        result_id=str(uuid4()),
        approval_id="",
        idempotency_key="k",
        status=status,
        executed_at=NOW,
    )


def _capture(monkeypatch, *, ids_result="proj-ids", ad_result=None, gen_result=None):
    """resolve 3종·record_execution을 패치하고 캡처 dict를 돌려준다.

    fake resolver는 실물처럼 '입력이 없으면 None'을 지켜 체인 폴백이 테스트에서도 동작한다.
    """
    captured: dict = {"records": [], "resolve_ids": None, "resolve_ad": [], "resolve_gen": []}

    async def _resolve(ids):
        captured["resolve_ids"] = list(ids)
        return ids_result

    async def _resolve_ad(ad_id):
        captured["resolve_ad"].append(ad_id)
        return ad_result if ad_id else None

    async def _resolve_gen(generation_id):
        captured["resolve_gen"].append(generation_id)
        return gen_result if generation_id else None

    async def _record(pid, feature_type, action, summary, payload=None, user_id=None):
        captured["records"].append(
            {
                "project_id": pid,
                "feature_type": feature_type,
                "action": action,
                "summary": summary,
                "payload": payload,
            }
        )

    monkeypatch.setattr(hl, "resolve_project_id", _resolve)
    monkeypatch.setattr(hl, "resolve_project_id_from_ad", _resolve_ad)
    monkeypatch.setattr(hl, "resolve_project_id_from_generation", _resolve_gen)
    monkeypatch.setattr(hl, "record_execution", _record)
    return captured


async def test_records_contract_fields(monkeypatch):
    captured = _capture(monkeypatch)
    record = build_history_recorder()
    proposal = make_proposal()  # PAUSE_CAMPAIGN, target=("camp-001",)
    action = make_action(proposal)  # approver_id="user-77"

    await record(action, proposal, _result())

    assert len(captured["records"]) == 1
    rec = captured["records"][0]
    assert rec["project_id"] == "proj-ids"
    assert rec["feature_type"] == "management"
    assert rec["action"] == "pause_campaign"  # action_type 소문자화
    assert "일시중지" in rec["summary"] and "camp-001" in rec["summary"]
    assert rec["payload"]["actor"] == "user"
    assert rec["payload"]["status"] == ResultStatus.SUCCESS.value


async def test_auto_approver_maps_to_actor_auto(monkeypatch):
    captured = _capture(monkeypatch)
    record = build_history_recorder()
    proposal = make_proposal()
    action = make_action(proposal, approver_id=AUTO_APPROVER)

    await record(action, proposal, _result())

    assert captured["records"][0]["payload"]["actor"] == "auto"


async def test_skips_when_project_unresolved(monkeypatch):
    captured = _capture(monkeypatch, ids_result=None)
    record = build_history_recorder()
    proposal = make_proposal()

    await record(make_action(proposal), proposal, _result())

    assert captured["records"] == []


async def test_non_create_uses_target_ids_resolver(monkeypatch):
    captured = _capture(monkeypatch)
    record = build_history_recorder()
    proposal = make_proposal()

    await record(make_action(proposal), proposal, _result())

    assert captured["resolve_ids"] == ["camp-001"]
    assert captured["resolve_ad"] == []  # CREATE 전용 경로 미사용
    assert captured["resolve_gen"] == []


async def test_create_manual_resolves_via_creative_ad_id(monkeypatch):
    # CREATE의 target_object_ids는 광고계정 id(옵션 A)·created_campaigns는 미적재 시점 —
    # 수동 폼 제안은 campaign_config.creative_ad_id가 유일한 귀속 단서(스펙 리뷰 P1).
    captured = _capture(monkeypatch, ad_result="proj-a")
    record = build_history_recorder()
    proposal = make_proposal(
        action_type="CREATE_CAMPAIGN",
        target_object_ids=("act_001",),
        evidence_metrics={"campaign_config": {"creative_ad_id": "ad-uuid-1"}},
    )

    await record(make_action(proposal), proposal, _result())

    assert captured["resolve_ad"][0] == "ad-uuid-1"
    assert captured["resolve_ids"] is None  # 계정 id로 캠페인 역추적 시도 금지
    assert captured["records"][0]["action"] == "create_campaign"
    assert captured["records"][0]["project_id"] == "proj-a"


async def test_create_simulation_falls_back_to_source_ad_id(monkeypatch):
    # 시뮬 기반 제안(management.py:2842)은 creative_ad_id 없이 simulation_snapshot만 가짐.
    captured = _capture(monkeypatch, ad_result="proj-s")
    record = build_history_recorder()
    proposal = make_proposal(
        action_type="CREATE_CAMPAIGN",
        target_object_ids=("act_001",),
        evidence_metrics={
            "campaign_config": {},
            "simulation_snapshot": {"source_ad_id": "ad-uuid-2"},
        },
    )

    await record(make_action(proposal), proposal, _result())

    # 체인: creative_ad_id(None)→source_ad_id 순으로 같은 resolver가 두 번 불린다.
    assert captured["resolve_ad"] == [None, "ad-uuid-2"]
    assert captured["records"][0]["project_id"] == "proj-s"


async def test_create_candidate_falls_back_to_generation_id(monkeypatch):
    # 후보 기반 제안(management.py:2481)은 candidate_snapshot.generation_id만 가짐 —
    # AdGeneration.project_id(core/models.py:546)로 귀속.
    captured = _capture(monkeypatch, gen_result="proj-g")
    record = build_history_recorder()
    proposal = make_proposal(
        action_type="CREATE_CAMPAIGN",
        target_object_ids=("act_001",),
        evidence_metrics={
            "campaign_config": {},
            "candidate_snapshot": {"generation_id": "gen-uuid-1"},
        },
    )

    await record(make_action(proposal), proposal, _result())

    assert captured["resolve_gen"] == ["gen-uuid-1"]
    assert captured["records"][0]["project_id"] == "proj-g"


async def test_create_without_any_clue_skips(monkeypatch):
    # 모든 귀속 단서(creative_ad_id·source_ad_id·generation_id) 부재 → 기록 생략.
    captured = _capture(monkeypatch)
    record = build_history_recorder()
    proposal = make_proposal(
        action_type="CREATE_CAMPAIGN",
        target_object_ids=("act_001",),
        evidence_metrics={"campaign_config": {}},
    )

    await record(make_action(proposal), proposal, _result())

    assert captured["records"] == []
