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
async def test_simulation_no_ids_is_graceful():
    # id 없음 + 풀모드 에이전트 없음 + org 맥락 없음 → 에러 대신 안내 답변(컨시어지 지향).
    sub = SimulationSubAgent(service=_FakeSimService())
    sub._agent = None  # 풀모드 ReAct 미구성 강제(폴백 경로)
    out = await sub.run(SubAgentRequest(question="시뮬 돌려줘"))  # sim_id·ad_id·org 모두 없음
    assert out.route is Route.SIMULATION
    assert out.error is None and out.answer


@pytest.mark.asyncio
async def test_simulation_fallback_lists_org_sims(monkeypatch):
    # id 없음 + org 맥락 → sim_list 폴백으로 현황 나열(키없음/mock, 실 DB 대신 모킹).
    import domain.chat.adapters.sim_tools as st

    async def fake_list(limit=10, org_id=None, status=None):
        assert org_id == "org-1"
        return {
            "simulations": [
                {
                    "simulation_id": "abcd1234-0000",
                    "ad_title": "냐오옹 캠페인",
                    "status": "COMPLETED",
                    "kpi": {"click_intent_rate": 0.12},
                }
            ],
            "count": 1,
        }

    monkeypatch.setattr(st, "sim_list", fake_list)
    sub = SimulationSubAgent(service=_FakeSimService())
    sub._agent = None  # 폴백 경로 강제
    out = await sub.run(
        SubAgentRequest(question="현재 시뮬레이션 현황", context_ids={"organization_id": "org-1"})
    )
    assert out.route is Route.SIMULATION and out.error is None
    assert "냐오옹 캠페인" in out.answer
    assert out.structured.get("kind") == "simulation_list"


def test_build_simulation_agent_none_without_key():
    # 키 없음/use_mock이면 ReAct 미구성(None) → 서브에이전트가 구조화 폴백을 쓴다.
    from types import SimpleNamespace

    from domain.chat.adapters.sim_agent import build_simulation_agent

    assert build_simulation_agent(SimpleNamespace(use_mock=True, anthropic_api_key="sk-x")) is None
    assert build_simulation_agent(SimpleNamespace(use_mock=False, anthropic_api_key=None)) is None


def _react_settings():
    # ReAct 빌드용 최소 settings(Claude 호출·모델 로드 없음 — 그래프 컴파일만 검증).
    from types import SimpleNamespace

    return SimpleNamespace(
        use_mock=False,
        anthropic_api_key="sk-test",
        chat_orchestrator_model="claude-sonnet-4-6",
        chat_orchestrator_provider="anthropic",
        embedding_provider="bge_m3_local",
        embedding_dim=1024,
        embedding_base_url="http://localhost:8080",
    )


def test_build_simulation_agent_compiles_with_key():
    # 회귀 가드 — ReAct 그래프 컴파일 성공. route(state: _State) 로컬클래스 주석이
    # langgraph get_type_hints에서 NameError를 내던 빌드 실패의 재발 방지.
    from domain.chat.adapters.sim_agent import build_simulation_agent

    assert callable(build_simulation_agent(_react_settings()))


def test_build_generator_agent_compiles_with_key():
    # 회귀 가드 — gen ReAct 그래프 컴파일 성공(동일 _State NameError 재발 방지).
    from domain.chat.adapters.gen_agent import build_generator_agent

    assert callable(build_generator_agent(_react_settings()))


@pytest.mark.asyncio
async def test_generator_no_product_no_id_is_graceful():
    # product 정보·generation_id 모두 없음 → 트리거 대신 안내 답변(컨시어지 지향).
    async def fake_start(req, created_by=None):
        raise AssertionError("상품정보 없으면 트리거되면 안 됨")

    async def fake_detail(gid):
        return None

    sub = GeneratorSubAgent(start_fn=fake_start, detail_fn=fake_detail)
    out = await sub.run(SubAgentRequest(question="시안 만들어줘"))
    assert out.route is Route.GENERATION
    assert out.error is None and out.answer  # start_fn 미호출 + 안내


def test_build_generator_agent_none_without_key():
    # 키 없음/use_mock이면 ReAct 미구성(None) → 서브에이전트가 구조화 폴백을 쓴다.
    from types import SimpleNamespace

    from domain.chat.adapters.gen_agent import build_generator_agent

    assert build_generator_agent(SimpleNamespace(use_mock=True, anthropic_api_key="sk-x")) is None
    assert build_generator_agent(SimpleNamespace(use_mock=False, anthropic_api_key=None)) is None


def test_simulation_subagent_get_service_import_path(monkeypatch):
    # 회귀 가드 — _get_service의 build_simulation_service import 경로 유효성.
    # 잘못된 모듈이면 ImportError. 키 없으면 RuntimeError(정상 — import는 성공).
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    sub = SimulationSubAgent()
    try:
        sub._get_service()
    except ImportError as e:  # noqa: TRY203
        raise AssertionError(f"build_simulation_service import 경로 오류: {e}") from e
    except Exception:  # noqa: BLE001  키 없음 등 — import 성공을 의미
        pass
