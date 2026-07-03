"""도메인 자동화 레지스트리 — 등록·목록·domain 필터·멱등. gen/sim 확장 seam(hermetic)."""

from core.automation import register_automation, registered_automations


def test_register_and_list_by_domain():
    register_automation("generation", "unit_scan_x", interval_minutes=30, description="d")
    gen = registered_automations("generation")
    assert any(a["name"] == "unit_scan_x" and a["interval_minutes"] == 30 for a in gen)
    # domain 필터가 다른 도메인은 안 섞는다.
    assert all(a["domain"] == "generation" for a in gen)


def test_management_anomaly_scan_registered_on_import():
    import domain.management.scheduler  # noqa: F401 — import 시 register_automation 트리거

    mgmt = registered_automations("management")
    assert any(a["name"] == "anomaly_scan" for a in mgmt)


def test_register_is_idempotent_overwrite():
    register_automation("simulation", "dup", description="v1")
    register_automation("simulation", "dup", description="v2")
    dups = [a for a in registered_automations("simulation") if a["name"] == "dup"]
    assert len(dups) == 1
    assert dups[0]["description"] == "v2"
