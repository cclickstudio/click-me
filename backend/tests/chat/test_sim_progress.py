# 챗 시뮬 진행/완료 가시성 — 싱글톤 런타임 + 트리거 structured(simulation_started) 매핑.
import pytest


def test_norm_gender_maps_and_drops():
    from domain.chat.adapters.sim_agent import _norm_gender

    assert _norm_gender("female") == "F"
    assert _norm_gender("여성") == "F"
    assert _norm_gender("male") == "M"
    assert _norm_gender("남성") == "M"
    # '전체/all/무관'은 None → target_filter에서 빠져 전 인구(엔진은 'M'/'F'만 매칭).
    assert _norm_gender("전체") is None
    assert _norm_gender("all") is None
    assert _norm_gender(None) is None
    assert _norm_gender("") is None


def test_sim_runtime_last_run_id():
    from domain.chat.adapters import sim_runtime

    sim_runtime.set_last_run_id("r-1")
    assert sim_runtime.get_last_run_id() == "r-1"


def test_get_chat_sim_service_caches(monkeypatch):
    import domain.simulation.wiring as simwiring
    from domain.chat.adapters import sim_runtime

    sim_runtime._state.pop("svc", None)  # 싱글톤 상태 초기화
    calls = {"n": 0}

    class FakeSvc:
        pass

    def fake_build(settings):
        calls["n"] += 1
        return FakeSvc()

    monkeypatch.setattr(simwiring, "build_simulation_service", fake_build)
    a = sim_runtime.get_chat_sim_service(None)
    b = sim_runtime.get_chat_sim_service(None)
    assert a is b and calls["n"] == 1  # 1회만 빌드(같은 인스턴스 공유)
    sim_runtime._state.pop("svc", None)  # 정리(다른 테스트 오염 방지)


@pytest.mark.asyncio
async def test_simulation_subagent_triggered_to_started():
    from domain.chat.adapters.simulation_subagent import SimulationSubAgent
    from domain.chat.contracts.agent_io import SubAgentRequest

    async def fake_agent(question, context_ids):
        return {
            "answer": "시뮬레이션이 시작됐어요",
            "used_tools": ["start_simulation"],
            "kb_citations": [],
            "sim_data": {},
            "triggered": {"run_id": "r-9", "stream_url": "/api/chat/sim/r-9/stream"},
        }

    sub = SimulationSubAgent()
    sub._agent = fake_agent
    res = await sub.run(SubAgentRequest(question="이 광고 시뮬 돌려줘"))
    assert res.structured["kind"] == "simulation_started"
    assert res.structured["data"]["run_id"] == "r-9"


@pytest.mark.asyncio
async def test_simulation_subagent_query_stays_aggregate():
    from domain.chat.adapters.simulation_subagent import SimulationSubAgent
    from domain.chat.contracts.agent_io import SubAgentRequest

    async def fake_agent(question, context_ids):
        return {
            "answer": "집계",
            "used_tools": ["sim_result"],
            "kb_citations": [],
            "sim_data": {"click_intent_rate": 0.12},
            "triggered": {},
        }

    sub = SimulationSubAgent()
    sub._agent = fake_agent
    res = await sub.run(SubAgentRequest(question="결과 보여줘"))
    assert res.structured["kind"] == "simulation_aggregate"  # 트리거 없으면 조회 집계 유지


def test_get_chat_debate_service_caches(monkeypatch):
    import domain.simulation.wiring as simwiring
    from domain.chat.adapters import sim_runtime

    sim_runtime._state.pop("debate_svc", None)
    calls = {"n": 0}

    class FakeSvc:
        pass

    def fake_build(settings):
        calls["n"] += 1
        return FakeSvc()

    monkeypatch.setattr(simwiring, "build_debate_service", fake_build)
    a = sim_runtime.get_chat_debate_service(None)
    b = sim_runtime.get_chat_debate_service(None)
    assert a is b and calls["n"] == 1  # 1회만 빌드(같은 인스턴스 공유)
    sim_runtime._state.pop("debate_svc", None)


@pytest.mark.asyncio
async def test_simulation_subagent_debate_triggered_to_started():
    from domain.chat.adapters.simulation_subagent import SimulationSubAgent
    from domain.chat.contracts.agent_io import SubAgentRequest

    async def fake_agent(question, context_ids):
        return {
            "answer": "토론이 시작됐어요",
            "used_tools": ["start_debate"],
            "kb_citations": [],
            "sim_data": {},
            "triggered": {},
            "debate_triggered": {"run_id": "d-1", "stream_url": "/api/chat/debate/d-1/stream"},
        }

    sub = SimulationSubAgent()
    sub._agent = fake_agent
    res = await sub.run(SubAgentRequest(question="토론까지 진행해"))
    assert res.structured["kind"] == "debate_started"
    assert res.structured["data"]["run_id"] == "d-1"


@pytest.mark.asyncio
async def test_generator_subagent_triggered_to_started():
    from domain.chat.adapters.generator_subagent import GeneratorSubAgent
    from domain.chat.contracts.agent_io import SubAgentRequest

    async def fake_agent(question, context_ids):
        return {
            "answer": "시안 생성이 시작됐어요",
            "used_tools": ["start_generation"],
            "kb_citations": [],
            "gen_data": {},
            "triggered": {"generation_id": "g-1", "stream_url": "/api/chat/gen/g-1/stream"},
        }

    sub = GeneratorSubAgent()
    sub._agent = fake_agent
    res = await sub.run(SubAgentRequest(question="광고 생성해줘"))
    assert res.structured["kind"] == "generation_started"
    assert res.structured["data"]["generation_id"] == "g-1"
