"""Task2 — LIVE 실행 모드 게이팅.

실 게재 단계 진입(§7 갱신) — LIVE 봉인 해제. DEFAULT_ALLOWED_MODES에 LIVE 포함.
실집행은 use_mock=False + management_execution_mode=live 명시 opt-in일 때만 일어난다.
"""

from __future__ import annotations

from api.routers import management as m
from domain.management.contracts.enums import ExecutionMode
from domain.management.execution.executor import DEFAULT_ALLOWED_MODES


def test_default_allowed_modes_allows_live():
    # 실 게재 단계 — LIVE 봉인 해제. opt-in(use_mock=False+mode=live)일 때 실집행.
    assert ExecutionMode.LIVE in DEFAULT_ALLOWED_MODES


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
