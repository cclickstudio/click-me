# 리밸런스 챗 연결 — rebalance_action 위젯 형태와 tool_hint 허용을 검증
"""위젯 계약(형태 고정)과 remediation tool_hint 등록을 잠근다."""

import pytest
from pydantic import ValidationError

from domain.chat import widgets
from domain.management.remediation.contracts import (
    ALLOWED_TOOL_HINTS,
    OptionKind,
    RemediationAction,
    RemediationOption,
)

_TRANSFER = {
    "kind": "transfer",
    "from": {
        "campaign_id": "camp_low",
        "name": "저효율",
        "cpc_krw": 1200,
        "daily_budget_krw": 50_000,
        "after_krw": 40_000,
    },
    "to": {
        "campaign_id": "camp_high",
        "name": "고효율",
        "cpc_krw": 800,
        "daily_budget_krw": 30_000,
        "after_krw": 40_000,
    },
    "move_krw": 10_000,
    "basis": "last_7d",
    "reason": "테스트",
}


def test_rebalance_action_widget_shape():
    out = widgets.rebalance_action(_TRANSFER)
    assert out["source"] == widgets.DEEP_AGENT
    assert out["widget"]["type"] == "rebalance_action"
    assert out["widget"]["data"]["proposal"]["from"]["campaign_id"] == "camp_low"


def test_apply_rebalance_tool_hint_allowed():
    assert "apply_rebalance" in ALLOWED_TOOL_HINTS
    opt = RemediationOption(
        index=1,
        kind=OptionKind.SPEND,
        action=RemediationAction.DECREASE_BUDGET,
        label="리밸런스 적용",
        tool_hint="apply_rebalance",
    )
    assert opt.tool_hint == "apply_rebalance"


def test_unknown_tool_hint_still_rejected():
    with pytest.raises(ValidationError):
        RemediationOption(
            index=1,
            kind=OptionKind.SPEND,
            action=RemediationAction.DECREASE_BUDGET,
            label="오타",
            tool_hint="apply_rebalans",
        )
