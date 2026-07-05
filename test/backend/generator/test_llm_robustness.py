# 생성 LLM 견고성·이미지 provider 폴백·자동화 seam 골든 — §1-A/1-B/1-C 계약 고정
"""데모 안정성 관점의 얇은 계약 테스트(외부 호출 없이 순수 로직만).

- with_llm_retry: 일시적 예외 목록이 비어있지 않고, 원 Runnable을 재시도로 감싼다.
- _require_openai_for: openai면 통과 / 타 provider는 키 있으면 폴백(통과) · 없으면 실패.
- 자동화 레지스트리: generation:quality_digest 등록 + 비활성 시 스케줄러 미기동.
"""

from __future__ import annotations

import pytest

from core.automation import registered_automations
from core.config import settings
from domain.generator import scheduler
from domain.generator.llm import factory
from domain.generator.pipeline import image_providers


def test_transient_exceptions_populated():
    # openai(4종)만 있어도 재시도가 실질 동작하도록 비어있지 않아야 한다.
    assert factory._TRANSIENT_EXC
    names = {e.__name__ for e in factory._TRANSIENT_EXC}
    assert "RateLimitError" in names  # 429가 재시도 대상


def test_with_llm_retry_wraps_runnable():
    class _Fake:
        def with_retry(self, **kwargs):
            self.retry_kwargs = kwargs
            return "WRAPPED"

    fake = _Fake()
    out = factory.with_llm_retry(fake)
    assert out == "WRAPPED"
    assert fake.retry_kwargs["stop_after_attempt"] == 3
    assert fake.retry_kwargs["wait_exponential_jitter"] is True


def test_require_openai_passes_for_openai():
    # openai면 키 여부와 무관하게 통과.
    image_providers._require_openai_for("이미지 편집", "openai")  # 예외 없으면 통과


def test_require_openai_falls_back_when_key_present(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test", raising=False)
    # 타 provider여도 openai 키가 있으면 폴백(예외 없이 통과).
    image_providers._require_openai_for("인페인팅", "google_genai")


def test_require_openai_raises_without_key(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", None, raising=False)
    with pytest.raises(NotImplementedError):
        image_providers._require_openai_for("누끼", "google_genai")


def test_quality_digest_registered():
    names = {a["name"] for a in registered_automations("generation")}
    assert "quality_digest" in names


def test_stuck_scan_registered():
    names = {a["name"] for a in registered_automations("generation")}
    assert "stuck_scan" in names


def test_scheduler_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "generator_scheduler_enabled", False, raising=False)
    assert scheduler.start_scheduler(settings) is False


async def test_quality_digest_no_completed_returns_false(monkeypatch):
    # 완료 생성이 0이면 다이제스트를 적재하지 않고 False.
    class _FakeDB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def scalar(self, *a, **k):
            return 0

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", lambda: _FakeDB())

    recorded = []

    async def _rec(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(scheduler, "record_automation_run", _rec)
    assert await scheduler.run_quality_digest(settings) is False
    assert recorded == []


class _FakeStuckDB:
    """execute().scalars().all()이 미리 심은 stuck 행을 돌려주는 가짜 세션."""

    def __init__(self, rows):
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, *a, **k):
        rows = self._rows

        class _Result:
            def scalars(self):
                return self

            def all(self):
                return rows

        return _Result()


async def test_stuck_scan_records_finding(monkeypatch):
    import uuid
    from types import SimpleNamespace

    gid = uuid.uuid4()
    pid = uuid.uuid4()
    stuck = SimpleNamespace(
        id=gid, project_id=pid, status="running", input={"product_name": "수분크림"}
    )
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", lambda: _FakeStuckDB([stuck]))

    recorded = []

    async def _rec(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(scheduler, "record_automation_run", _rec)

    assert await scheduler.run_stuck_scan(settings) == 1
    assert len(recorded) == 1
    row = recorded[0]
    assert row["domain"] == "generation"
    assert row["job_name"] == "stuck_scan"
    assert row["status"] == "finding"
    assert row["severity"] == "warning"
    assert row["dedup_key"] == f"gen-stuck:{gid}"  # 재통지 방지 계약
    assert row["project_id"] == str(pid)
    assert "수분크림" in row["body"]
    assert row["payload"]["generation_id"] == str(gid)


async def test_stuck_scan_empty_no_record(monkeypatch):
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", lambda: _FakeStuckDB([]))

    recorded = []

    async def _rec(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(scheduler, "record_automation_run", _rec)

    assert await scheduler.run_stuck_scan(settings) == 0
    assert recorded == []
