"""계약 검증 — 골든 샘플 적합성 + frozen/extra=forbid/UTC/해시 규칙 (§9.0)."""

import json
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from domain.management.contracts.schemas import (
    ActionProposal,
    ActionResult,
    ApprovedAction,
    FaultConfig,
    verify_proposal_hash,
)
from tests.management.helpers import make_proposal

FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "domain"
    / "management"
    / "evals"
    / "fixtures"
    / "contracts"
)

GOLDEN_SAMPLES = [
    ("action_proposal_normal.json", ActionProposal),
    ("action_proposal_edge_expired.json", ActionProposal),
    ("approved_action_normal.json", ApprovedAction),
    ("approved_action_edge_tier3.json", ApprovedAction),
    ("action_result_normal.json", ActionResult),
    ("action_result_edge_partial_failure.json", ActionResult),
    ("fault_config_normal.json", FaultConfig),
    ("fault_config_edge_probabilistic.json", FaultConfig),
]


@pytest.mark.parametrize(("filename", "model"), GOLDEN_SAMPLES)
def test_golden_sample_validates(filename, model):
    data = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    instance = model.model_validate(data)
    assert instance.schema_version == "1.0"


def test_golden_proposal_hash_is_consistent():
    data = json.loads((FIXTURES / "action_proposal_normal.json").read_text(encoding="utf-8"))
    assert verify_proposal_hash(ActionProposal.model_validate(data))


def test_extra_field_is_forbidden():
    data = json.loads((FIXTURES / "action_proposal_normal.json").read_text(encoding="utf-8"))
    data["sneaky_field"] = 1  # 합의 안 된 필드를 슬쩍 못 끼운다
    with pytest.raises(ValidationError):
        ActionProposal.model_validate(data)


def test_contract_is_frozen():
    proposal = make_proposal()
    with pytest.raises(ValidationError):
        proposal.status = "executed"


def test_naive_datetime_is_rejected():
    with pytest.raises(ValidationError, match="naive"):
        make_proposal(metrics_as_of=datetime(2026, 6, 12, 9, 0, 0))  # tzinfo 없음


def test_krw_must_be_non_negative_int():
    with pytest.raises(ValidationError):
        make_proposal(budget_after_krw=-1)


def test_tampering_breaks_hash_verification():
    proposal = make_proposal()
    assert verify_proposal_hash(proposal)
    tampered = proposal.model_copy(update={"max_total_spend_krw": 10_000_000})
    assert not verify_proposal_hash(tampered)


def test_status_change_does_not_break_hash():
    """status는 라이프사이클 필드 — 해시 대상에서 제외된다."""
    proposal = make_proposal()
    executed = proposal.model_copy(update={"status": "executed"})
    assert verify_proposal_hash(executed)


def test_relabel_does_not_break_hash():
    """action_tier는 approval.py 재라벨 판정으로 합법 변경 — 해시 제외 (P1)."""
    proposal = make_proposal()
    relabeled = proposal.model_copy(update={"action_tier": 3})
    assert verify_proposal_hash(relabeled)
