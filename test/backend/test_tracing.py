# core.tracing.make_trace_config 표준 조립 + 이미지 비용 조회 검증

from core.config import settings
from core.tracing import _lookup_image_price, make_trace_config


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


def test_user_identity_metadata_added_when_present():
    cfg = make_trace_config(
        domain="chat",
        feature="assistant",
        user_id="u-uuid",
        login_id="alice",
        user_name="앨리스",
        role="USER",
    )
    md = cfg["metadata"]
    assert md["user_id"] == "u-uuid"
    assert md["login_id"] == "alice"
    assert md["user_name"] == "앨리스"
    assert md["role"] == "USER"


def test_user_identity_metadata_omitted_when_absent():
    md = make_trace_config(domain="chat", feature="assistant")["metadata"]
    assert "login_id" not in md
    assert "user_name" not in md
    assert "role" not in md


def test_image_price_lookup_gpt_image():
    assert _lookup_image_price("gpt-image-1", "1024x1024", "medium") == 0.042
    assert _lookup_image_price("gpt-image-1", "1024x1024", "high") == 0.167
    # gpt-image-2는 잠정 gpt-image-1 동일 단가.
    assert _lookup_image_price("gpt-image-2", "1024x1024", "low") == 0.011


def test_image_price_lookup_flat_and_unknown():
    assert _lookup_image_price("gemini-2.5-flash-image", "1024x1024", "medium") == 0.039
    assert _lookup_image_price("unknown-model", "1024x1024", "medium") is None
