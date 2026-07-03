# 컨텍스트 주입 판정 테스트 — 3조건(TTL·근접성·최신 1건) 각각 미충족 시 None
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from domain.management.remediation.context import pick_consult_context

NOW = datetime.now(UTC)


def _meta(campaign="camp_1", diagnosed_at=None):
    return {
        "kind": "remediation_consult",
        "schema_version": 1,
        "campaign_id": campaign,
        "anomaly_type": "no_delivery",
        "diagnosed_at": (diagnosed_at or NOW).isoformat(),
        "options": [
            {
                "index": 1,
                "action": "VERIFY_SIM",
                "tool_hint": "run_simulation",
                "label": "시뮬 검증",
            },
            {"index": 2, "action": "OBSERVE", "tool_hint": None, "label": "관망"},
        ],
    }


def test_injects_for_fresh_consult_in_recent_messages():
    msgs = [(None, NOW), (_meta(), NOW - timedelta(hours=1))]  # (meta, created_at) 최신순
    ctx = pick_consult_context(msgs, now=NOW, ttl_hours=24, recent_k=10)
    assert ctx is not None
    assert "camp_1" in ctx and "run_simulation" in ctx
    assert "직접 실행하지" in ctx  # HITL 지시 포함


def test_no_injection_when_ttl_expired():
    msgs = [(_meta(diagnosed_at=NOW - timedelta(hours=30)), NOW - timedelta(hours=30))]
    assert pick_consult_context(msgs, now=NOW, ttl_hours=24, recent_k=10) is None


def test_no_injection_when_consult_outside_recent_k():
    filler = [(None, NOW)] * 10  # 최근 10개가 전부 일반 메시지
    msgs = filler + [(_meta(), NOW - timedelta(hours=1))]
    assert pick_consult_context(msgs, now=NOW, ttl_hours=24, recent_k=10) is None


def test_latest_consult_wins_when_multiple():
    old = _meta(campaign="camp_old", diagnosed_at=NOW - timedelta(hours=2))
    new = _meta(campaign="camp_new", diagnosed_at=NOW - timedelta(hours=1))
    msgs = [(new, NOW - timedelta(hours=1)), (old, NOW - timedelta(hours=2))]
    ctx = pick_consult_context(msgs, now=NOW, ttl_hours=24, recent_k=10)
    assert "camp_new" in ctx and "camp_old" not in ctx


def test_no_injection_after_widget_shown():
    # consult 이후 위젯 메시지 존재 = 옵션 진행됨 → 낡은 상담 재주입 중단
    msgs = [
        ({"widget": {"type": "gen_form"}}, NOW),
        (_meta(), NOW - timedelta(hours=1)),
    ]
    assert pick_consult_context(msgs, now=NOW, ttl_hours=24, recent_k=10) is None


def test_none_when_no_consult():
    assert pick_consult_context([(None, NOW)], now=NOW, ttl_hours=24, recent_k=10) is None


def test_build_option_instruction_prefers_meta_mapping():
    from domain.management.remediation.context import build_option_instruction

    sel = {
        "option_index": 1,
        "action": "VERIFY_SIM",
        "tool_hint": "run_simulation",
        "campaign_id": "c1",
        "label": "시뮬레이션으로 소재 점검",
    }
    text = build_option_instruction(sel)
    assert "run_simulation" in text and "c1" in text
    assert "1" in text  # 선택 번호 명시


def test_build_option_instruction_observe_without_tool():
    from domain.management.remediation.context import build_option_instruction

    sel = {
        "option_index": 4,
        "action": "OBSERVE",
        "tool_hint": None,
        "campaign_id": "c1",
        "label": "두고 보기(추가 조치 없음)",
    }
    text = build_option_instruction(sel)
    assert "호출하지" in text  # 도구 호출 금지 지시


def test_build_option_instruction_rejects_unknown_tool_hint():
    from domain.management.remediation.context import build_option_instruction

    sel = {
        "option_index": 1,
        "action": "VERIFY_SIM",
        "tool_hint": "rm_rf_everything",
        "campaign_id": "c1",
        "label": "시뮬",
    }
    text = build_option_instruction(sel)
    assert text is not None and "rm_rf_everything" not in text
    assert "호출하지" in text  # 관망 강등


def test_build_option_instruction_missing_required_returns_none():
    from domain.management.remediation.context import build_option_instruction

    assert build_option_instruction({"label": "시뮬"}) is None
