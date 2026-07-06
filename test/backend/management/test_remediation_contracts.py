# remediation 고정 계약 테스트 — 옵션 스키마(어휘·index 연속·tool_hint·schema_version) 검증
from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.management.remediation.contracts import (
    CONSULT_SCHEMA_VERSION,
    ConsultResult,
    OptionKind,
    RemediationAction,
    RemediationOption,
)


def _opt(index: int, action: RemediationAction = RemediationAction.OBSERVE, **kw):
    defaults = {"kind": OptionKind.OBSERVE, "label": "관망", "tool_hint": None}
    defaults.update(kw)
    return RemediationOption(index=index, action=action, **defaults)


def test_option_rejects_unregistered_tool_hint():
    with pytest.raises(ValidationError):
        RemediationOption(
            index=1,
            kind=OptionKind.PLATFORM,
            action=RemediationAction.VERIFY_SIM,
            label="시뮬 검증",
            tool_hint="launch_rocket",  # 미등록 도구
        )


def test_option_accepts_registered_tool_hints():
    o = RemediationOption(
        index=1,
        kind=OptionKind.PLATFORM,
        action=RemediationAction.REGENERATE_CREATIVE,
        label="새 시안",
        tool_hint="run_generation",
    )
    assert o.tool_hint == "run_generation"


def test_consult_result_requires_contiguous_indices_from_1():
    # status 규칙은 전부 충족시켜 index 규칙만 위반 — 잘못된 이유로 통과하지 않게 격리
    with pytest.raises(ValidationError, match="index"):
        ConsultResult(
            status="anomaly",
            campaign_id="c1",
            anomaly_type="no_delivery",
            options=[_opt(1), _opt(3)],  # 2 건너뜀
        )
    with pytest.raises(ValidationError):
        ConsultResult(
            status="anomaly",
            campaign_id="c1",
            anomaly_type="no_delivery",
            options=[_opt(2)],  # 1부터 아님
        )


def test_consult_result_normal_allows_empty_options():
    r = ConsultResult(status="normal", campaign_id="c1", message="정상 범위")
    assert r.options == []


def test_status_rules_are_enforced():
    # normal은 options 금지
    with pytest.raises(ValidationError):
        ConsultResult(status="normal", campaign_id="c1", options=[_opt(1)])
    # anomaly는 options 최소 1개 + anomaly_type 필수
    with pytest.raises(ValidationError):
        ConsultResult(status="anomaly", campaign_id="c1", anomaly_type="no_delivery", options=[])
    with pytest.raises(ValidationError):
        ConsultResult(status="anomaly", campaign_id="c1", options=[_opt(1)])  # anomaly_type 누락


def test_to_meta_shape_is_fixed():
    r = ConsultResult(
        status="anomaly",
        campaign_id="c1",
        campaign_name="여름 캠페인",
        anomaly_type="no_delivery",
        confidence=0.9,
        diagnosed_at="2026-07-02T00:00:00+00:00",
        message="노출 0",
        options=[
            _opt(
                1,
                RemediationAction.VERIFY_SIM,
                kind=OptionKind.PLATFORM,
                label="시뮬 검증",
                tool_hint="run_simulation",
            ),
            _opt(2),
        ],
    )
    meta = r.to_meta(org_id="org-1")
    assert meta["kind"] == "remediation_consult"
    assert meta["schema_version"] == CONSULT_SCHEMA_VERSION
    assert meta["campaign_id"] == "c1"
    assert meta["org_id"] == "org-1"
    assert meta["anomaly_type"] == "no_delivery"
    assert meta["options"][0] == {
        "index": 1,
        "action": "VERIFY_SIM",
        "tool_hint": "run_simulation",
        "label": "시뮬 검증",
    }
