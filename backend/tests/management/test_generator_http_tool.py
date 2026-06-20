# 🅱 generator HTTP 어댑터 — IMPROVE 호출·폴링·타임아웃·후보 매핑 + 폴백 검증
import pytest

from domain.management.agents.regeneration import CreativeCandidate
from domain.management.agents.regeneration_tools import (
    FallbackCreativeGenerator,
    GeneratorHttpTool,
    GeneratorInputError,
)
from domain.management.contracts.enums import AnomalyType
from domain.management.contracts.schemas import DiagnosisResult
from tests.management.helpers import NOW


def make_diagnosis(**evidence) -> DiagnosisResult:
    return DiagnosisResult(
        diagnosis_id="diag-001",
        tenant_id="org-1",
        campaign_id="camp-1",
        anomaly_type=AnomalyType.QUALITY_DEGRADED,
        source="agent",
        hypothesis="품질 저하 — 시안 피로도",
        confidence=0.7,
        evidence_metrics={"existing_ad_s3_key": "s3/old.png", **evidence},
        metrics_as_of=NOW,
        status="confirmed",
    )


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeHttpClient:
    """post는 고정 응답, get은 스크립트된 순서대로(마지막은 반복) 반환."""

    def __init__(self, post_payload, get_payloads):
        self._post_payload = post_payload
        self._get_payloads = list(get_payloads)
        self.posts: list[tuple[str, dict]] = []
        self.gets = 0

    async def post(self, url, json):
        self.posts.append((url, json))
        return FakeResp(self._post_payload)

    async def get(self, url):
        idx = min(self.gets, len(self._get_payloads) - 1)
        self.gets += 1
        return FakeResp(self._get_payloads[idx])


class FakeClock:
    def __init__(self, values):
        self._values = list(values)
        self._i = 0

    def __call__(self):
        v = self._values[min(self._i, len(self._values) - 1)]
        self._i += 1
        return v


async def _no_sleep(_seconds):
    return None


def _completed(*candidates):
    return {"status": "completed", "candidates": list(candidates)}


def build_tool(
    get_payloads, *, clock_values=(0,), timeout_s=30
) -> tuple[GeneratorHttpTool, FakeHttpClient]:
    client = FakeHttpClient({"generation_id": "gen-1"}, get_payloads)
    tool = GeneratorHttpTool(
        client,
        poll_interval=0.1,
        timeout_s=timeout_s,
        clock=FakeClock(clock_values),
        sleep=_no_sleep,
    )
    return tool, client


async def test_completed_candidates_are_mapped():
    detail = _completed(
        {"candidate_id": "g1", "copy": "새 카피1", "s3_key": "s3/a.png", "qa_passed": True},
        {"candidate_id": "g2", "copy": "새 카피2", "s3_key": "s3/b.png", "qa_passed": True},
    )
    tool, _ = build_tool([detail])

    result = await tool.generate(make_diagnosis(), count=3)

    assert result == [
        CreativeCandidate(candidate_id="g1", ad_copy="새 카피1", image_ref="s3/a.png"),
        CreativeCandidate(candidate_id="g2", ad_copy="새 카피2", image_ref="s3/b.png"),
    ]


async def test_count_is_respected():
    detail = _completed(
        *[{"candidate_id": f"g{i}", "copy": f"c{i}", "s3_key": None} for i in range(3)]
    )
    tool, _ = build_tool([detail])

    result = await tool.generate(make_diagnosis(), count=2)

    assert len(result) == 2


async def test_improve_request_body_is_built_from_diagnosis():
    tool, client = build_tool([_completed({"candidate_id": "g1", "copy": "c", "s3_key": None})])

    await tool.generate(make_diagnosis(), count=1)

    url, body = client.posts[0]
    assert url.endswith("/generations")
    assert body["mode"] == "improve"
    assert body["existing_ad_s3_key"] == "s3/old.png"
    assert body["simulation_summary"].strip()  # 진단에서 합성


async def test_polls_until_completed():
    running = {"status": "running", "candidates": []}
    detail = _completed({"candidate_id": "g1", "copy": "c", "s3_key": None})
    tool, client = build_tool([running, running, detail], clock_values=[0])

    result = await tool.generate(make_diagnosis(), count=1)

    assert client.gets == 3
    assert len(result) == 1


async def test_failed_status_raises():
    tool, _ = build_tool([{"status": "failed", "candidates": []}])

    with pytest.raises(RuntimeError):
        await tool.generate(make_diagnosis(), count=1)


async def test_timeout_raises():
    running = {"status": "running", "candidates": []}
    tool, _ = build_tool([running], clock_values=[0, 10, 20, 30], timeout_s=25)

    with pytest.raises(TimeoutError):
        await tool.generate(make_diagnosis(), count=1)


async def test_missing_s3_key_raises_input_error():
    diagnosis = DiagnosisResult(
        diagnosis_id="d",
        tenant_id="o",
        campaign_id="c",
        anomaly_type=AnomalyType.QUALITY_DEGRADED,
        source="agent",
        confidence=0.7,
        evidence_metrics={},  # s3_key 없음
        metrics_as_of=NOW,
        status="confirmed",
    )
    tool, _ = build_tool([_completed()])

    with pytest.raises(GeneratorInputError):
        await tool.generate(diagnosis, count=1)


# ── 폴백 합성기 ──────────────────────────────────────────────────────


class _Boom:
    async def generate(self, diagnosis, count):
        raise RuntimeError("primary down")


class _Stub:
    def __init__(self, candidates):
        self.candidates = candidates
        self.called = False

    async def generate(self, diagnosis, count):
        self.called = True
        return self.candidates


async def test_fallback_used_when_primary_fails():
    fallback = _Stub([CreativeCandidate(candidate_id="t1", ad_copy="템플릿")])
    gen = FallbackCreativeGenerator(primary=_Boom(), fallback=fallback)

    result = await gen.generate(make_diagnosis(), count=1)

    assert fallback.called is True
    assert result[0].candidate_id == "t1"


async def test_primary_used_when_ok():
    primary = _Stub([CreativeCandidate(candidate_id="p1", ad_copy="실생성")])
    fallback = _Stub([CreativeCandidate(candidate_id="t1", ad_copy="템플릿")])
    gen = FallbackCreativeGenerator(primary=primary, fallback=fallback)

    result = await gen.generate(make_diagnosis(), count=1)

    assert result[0].candidate_id == "p1"
    assert fallback.called is False


# ── 조립 헬퍼 통합 — generator_client 주입 시 전체 agent 관통 ──────────


async def test_build_agent_with_generator_client_runs_end_to_end():
    """generator HTTP 후보가 진짜 agent를 관통해 REPLACE_CREATIVE 제안까지 도달한다."""
    from domain.management.agents.regeneration import RemediationContext
    from domain.management.agents.regeneration_tools import build_regeneration_agent

    detail = _completed(
        {"candidate_id": "g1", "copy": "지금 바로 확인하세요", "s3_key": "s3/a.png"}
    )
    client = FakeHttpClient({"generation_id": "gen-1"}, [detail])
    agent = build_regeneration_agent(generator_client=client)
    ctx = RemediationContext(
        ad_account_id="act",
        target_object_ids=("camp-1",),
        budget_before_krw=50_000,
        budget_after_krw=50_000,
        run_days=7,
        expected_state_version="sv",
        approval_policy_version="v1",
    )

    proposal = await agent.propose(make_diagnosis(), ctx)

    assert proposal is not None
    assert proposal.action_type == "REPLACE_CREATIVE"
    assert proposal.evidence_metrics["selected_candidate_id"] == "g1"
