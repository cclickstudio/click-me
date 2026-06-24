# 서브에이전트 어댑터 — 읽기/트리거/제안 매핑(hermetic, fake 주입).
import pytest

from domain.chat.adapters.generator_subagent import GeneratorSubAgent
from domain.chat.adapters.management_subagent import ManagementSubAgent
from domain.chat.adapters.simulation_subagent import SimulationSubAgent
from domain.chat.contracts.agent_io import Route, SubAgentRequest


# ---- management ----
class _FakeAskResult:
    def __init__(self, sa=None):
        self.answer = "캠페인 상태는 양호합니다"
        self.citations = []
        self.used_tools = ["live_campaigns"]
        self.evidence = {}
        self.suggested_action = sa
        self.requires_approval = bool(sa and sa.requires_approval)
        self.thread_id = None


class _SA:
    action_type = "PAUSE_CAMPAIGN"
    target_campaign_id = "camp_1"
    tier = "TIER_1"
    requires_approval = True
    rationale = "지출 과다"


@pytest.mark.asyncio
async def test_management_maps_askresult_and_suggested_action():
    async def fake_ask(req):
        assert req.question == "캠페인 멈춰"
        return _FakeAskResult(sa=_SA())

    sub = ManagementSubAgent(ask=fake_ask)
    out = await sub.run(
        SubAgentRequest(question="캠페인 멈춰", context_ids={"campaign_id": "camp_1"})
    )
    assert out.route is Route.MANAGEMENT and "양호" in out.answer
    assert out.used_tools == ["live_campaigns"]
    assert out.proposed_action is not None
    assert out.proposed_action.action_type == "PAUSE_CAMPAIGN"
    assert out.proposed_action.requires_approval is True


@pytest.mark.asyncio
async def test_management_no_suggested_action():
    async def fake_ask(req):
        return _FakeAskResult(sa=None)

    sub = ManagementSubAgent(ask=fake_ask)
    out = await sub.run(SubAgentRequest(question="성과 어때?"))
    assert out.proposed_action is None


@pytest.mark.asyncio
async def test_management_graceful_error():
    async def boom(req):
        raise RuntimeError("vendor 503")

    sub = ManagementSubAgent(ask=boom)
    out = await sub.run(SubAgentRequest(question="x"))
    assert out.route is Route.MANAGEMENT and out.error is not None and "503" in out.error


# ---- simulation ----
class _FakeSimService:
    def __init__(self):
        self.started = None

    async def start(self, req):
        self.started = req
        return "run-123"

    def get_result(self, run_id):
        if run_id != "run-xyz":
            return None
        return {
            "aggregate": {
                "click_intent_rate": 0.12,
                "purchase_intent": 3.4,
                "trust_avg": 3.1,
                "rejection_rate": 0.2,
                "ci_low": 0.1,
                "ci_high": 0.15,
            }
        }


@pytest.mark.asyncio
async def test_simulation_read_existing():
    svc = _FakeSimService()
    sub = SimulationSubAgent(service=svc)
    out = await sub.run(
        SubAgentRequest(question="시뮬 결과 어때?", context_ids={"simulation_id": "run-xyz"})
    )
    assert out.route is Route.SIMULATION
    assert out.structured.get("kind") == "simulation_aggregate"
    assert out.structured["data"]["click_intent_rate"] == 0.12


@pytest.mark.asyncio
async def test_simulation_trigger_async():
    svc = _FakeSimService()
    sub = SimulationSubAgent(service=svc)
    out = await sub.run(
        SubAgentRequest(
            question="이 광고 시뮬 돌려줘", context_ids={"ad_id": "ad_9"}, knobs={"sample_size": 30}
        )
    )
    assert svc.started is not None and svc.started.ad_id == "ad_9"
    assert "run-123" in out.answer  # async start: run_id 안내


# ---- generator ----
@pytest.mark.asyncio
async def test_generator_trigger():
    captured = {}

    async def fake_start(req, created_by=None):
        captured["req"] = req
        return "gen-1"

    async def fake_detail(gid):
        return None

    sub = GeneratorSubAgent(start_fn=fake_start, detail_fn=fake_detail)
    out = await sub.run(
        SubAgentRequest(
            question="시안 만들어줘",
            knobs={
                "product_name": "비타민",
                "product_description": "건강",
                "target_audience": "20대",
            },
        )
    )
    assert captured["req"].product_name == "비타민" and "gen-1" in out.answer


@pytest.mark.asyncio
async def test_generator_read_existing():
    async def fake_start(req, created_by=None):
        return "x"

    async def fake_detail(gid):
        return {
            "schema_version": "1",
            "status": "completed",
            "candidates": [{"candidate_id": "c1", "idx": 0, "qa_passed": True}],
        }

    sub = GeneratorSubAgent(start_fn=fake_start, detail_fn=fake_detail)
    out = await sub.run(
        SubAgentRequest(question="시안 보여줘", context_ids={"generation_id": "gen-1"})
    )
    assert out.structured.get("kind") == "generation_detail"
    assert out.route is Route.GENERATION


@pytest.mark.asyncio
async def test_simulation_trigger_without_ad_id_is_graceful():
    sub = SimulationSubAgent(service=_FakeSimService())
    out = await sub.run(SubAgentRequest(question="시뮬 돌려줘"))  # simulation_id·ad_id 모두 없음
    assert out.route is Route.SIMULATION and out.error is not None and "ad_id" in out.error


@pytest.mark.asyncio
async def test_generator_trigger_missing_fields_is_graceful():
    async def fake_start(req, created_by=None):
        raise AssertionError("필수 필드 누락이면 start_fn 호출되면 안 됨")

    async def fake_detail(gid):
        return None

    sub = GeneratorSubAgent(start_fn=fake_start, detail_fn=fake_detail)
    out = await sub.run(
        SubAgentRequest(question="시안 만들어줘")
    )  # product 필드 누락 → ValidationError
    assert out.route is Route.GENERATION and out.error is not None
