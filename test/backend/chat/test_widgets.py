# 위젯 신호 형태 골든 — 프론트 meta.widget 계약(바이트 동일 유지)
"""widgets.py 순수 함수가 내보내는 위젯 dict가 프론트 계약과 정확히 일치하는지 고정한다."""

from domain.chat import widgets


def test_sim_form():
    assert widgets.sim_form({"ad_title": "A", "ad_content": "B"}) == {
        "widget": {"type": "sim_form", "data": {"ad_title": "A", "ad_content": "B"}},
        "source": "simulation",
    }


def test_gen_form():
    assert widgets.gen_form({"product_name": "P"}) == {
        "widget": {"type": "gen_form", "data": {"product_name": "P"}},
        "source": "generator",
    }


def test_sim_list_modes():
    for mode in ("read", "select", "compare"):
        assert widgets.sim_list([{"id": 1}], mode) == {
            "widget": {"type": "sim_list", "mode": mode, "data": {"items": [{"id": 1}]}},
            "source": "simulation",
        }


def test_gen_list_default_read():
    w = widgets.gen_list([])
    assert w["widget"]["type"] == "gen_list"
    assert w["widget"]["mode"] == "read"
    assert w["source"] == "generator"


def test_report_ready():
    assert widgets.report_ready("p1", "month") == {
        "widget": {"type": "report_ready", "data": {"project_id": "p1", "period": "month"}},
        "source": "simulation",
    }


def test_batch_sim_form_has_no_data():
    assert widgets.batch_sim_form() == {
        "widget": {"type": "batch_sim_form"},
        "source": "simulation",
    }


def test_create_campaign_source_is_deep_agent():
    assert widgets.create_campaign({"objective": "leads"}) == {
        "widget": {"type": "create_campaign", "data": {"prefill": {"objective": "leads"}}},
        "source": "deep-agent",
    }


def test_campaign_action_source_is_deep_agent():
    assert widgets.campaign_action({"action": "pause"}) == {
        "widget": {"type": "campaign_action", "data": {"action": {"action": "pause"}}},
        "source": "deep-agent",
    }


def test_exec_from_sim_widget_shape():
    data = {
        "simulation_id": "sim-1",
        "default_name": "수분크림 광고",
        "click_intent_rate": 0.042,
        "rejection_rate": 0.08,
        "link_url": "https://example.com",
        "daily_budget_krw": 20000,
        "start_date": "2026-07-10",
        "end_date": None,
    }
    out = widgets.exec_from_sim(data)
    assert out["widget"]["type"] == "exec_from_sim"
    assert out["widget"]["data"]["simulation_id"] == "sim-1"
    assert out["source"] == "deep-agent"
