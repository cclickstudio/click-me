# core.tracing.make_trace_config 표준 조립 검증

from core.config import settings
from core.tracing import make_trace_config


def test_run_name_without_mode():
    cfg = make_trace_config(domain="management", feature="regenerate")
    assert cfg["run_name"] == "management.regenerate"


def test_run_name_with_mode():
    cfg = make_trace_config(domain="generator", feature="generate", mode="create")
    assert cfg["run_name"] == "generator.generate.create"


def test_standard_tags_and_metadata():
    cfg = make_trace_config(domain="management", feature="regenerate", ad_id="ad_1")
    assert cfg["tags"] == ["management", "regenerate", settings.app_env]
    md = cfg["metadata"]
    assert md["domain"] == "management"
    assert md["feature"] == "regenerate"
    assert md["env"] == settings.app_env
    assert md["user_id"] == "anonymous"
    assert md["ad_id"] == "ad_1"


def test_mode_added_to_tags_and_metadata():
    cfg = make_trace_config(domain="generator", feature="generate", mode="improve")
    assert "improve" in cfg["tags"]
    assert cfg["metadata"]["mode"] == "improve"


def test_extra_tags_and_metadata_merge():
    cfg = make_trace_config(
        domain="management",
        feature="regenerate",
        extra_tags=["part-b"],
        extra_metadata={"tenant_id": "t1", "campaign_id": "c1"},
    )
    assert "part-b" in cfg["tags"]
    assert cfg["metadata"]["tenant_id"] == "t1"
    assert cfg["metadata"]["campaign_id"] == "c1"
