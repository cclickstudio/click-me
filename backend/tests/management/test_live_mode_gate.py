"""Task2 — LIVE 실행 모드 게이팅.

LIVE는 use_mock=False + management_execution_mode=live 명시 opt-in일 때만 풀린다.
기본값은 봉인(DEFAULT_ALLOWED_MODES에 LIVE 없음). 실 Meta 호출은 일어나지 않는다.
"""

from __future__ import annotations

from api.routers import management as m
from domain.management.contracts.enums import ExecutionMode
from domain.management.execution.executor import DEFAULT_ALLOWED_MODES


def test_default_allowed_modes_seals_live():
    assert ExecutionMode.LIVE not in DEFAULT_ALLOWED_MODES


def test_resolved_mode_mock_when_use_mock(monkeypatch):
    monkeypatch.setattr(m.settings, "use_mock", True, raising=False)
    assert m._resolved_execution_mode() is ExecutionMode.MOCK


def test_resolved_mode_live_when_configured(monkeypatch):
    monkeypatch.setattr(m.settings, "use_mock", False, raising=False)
    monkeypatch.setattr(m.settings, "management_execution_mode", "live", raising=False)
    assert m._resolved_execution_mode() is ExecutionMode.LIVE


def test_resolved_mode_validate_only(monkeypatch):
    monkeypatch.setattr(m.settings, "use_mock", False, raising=False)
    monkeypatch.setattr(m.settings, "management_execution_mode", "validate_only", raising=False)
    assert m._resolved_execution_mode() is ExecutionMode.VALIDATE_ONLY


def test_resolved_mode_fallback_dry_run_on_garbage(monkeypatch):
    monkeypatch.setattr(m.settings, "use_mock", False, raising=False)
    monkeypatch.setattr(m.settings, "management_execution_mode", "garbage", raising=False)
    assert m._resolved_execution_mode() is ExecutionMode.DRY_RUN
