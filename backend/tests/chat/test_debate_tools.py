# 챗 토론(debate) 툴 — 조회(list/detail)·트리거(start_debate) hermetic 검증.
import pytest


@pytest.mark.asyncio
async def test_sim_debate_list_maps(monkeypatch):
    from domain.chat.adapters import sim_tools
    from domain.simulation.repositories.debate_repository import DebateRepository

    async def fake_list(self, sim_id):
        return [{"debate_id": "d1", "topic": "T"}]

    monkeypatch.setattr(DebateRepository, "list_by_simulation", fake_list)
    out = await sim_tools.sim_debate_list("sim-1")
    assert out["count"] == 1 and out["simulation_id"] == "sim-1"
    assert out["debates"][0]["debate_id"] == "d1"


@pytest.mark.asyncio
async def test_sim_debate_list_need_id():
    from domain.chat.adapters import sim_tools

    assert await sim_tools.sim_debate_list("") == {"error": "need_simulation_id"}


@pytest.mark.asyncio
async def test_sim_debate_detail_not_found(monkeypatch):
    from domain.chat.adapters import sim_tools
    from domain.simulation.repositories.debate_repository import DebateRepository

    async def fake_detail(self, debate_id):
        return None

    monkeypatch.setattr(DebateRepository, "get_detail", fake_detail)
    assert await sim_tools.sim_debate_detail("d-x") == {"error": "not_found", "debate_id": "d-x"}


@pytest.mark.asyncio
async def test_start_debate_sim_not_ready(monkeypatch):
    from domain.chat.adapters import sim_tools

    async def fake_full(sim_id):
        return None  # 완료 시뮬 없음

    monkeypatch.setattr(sim_tools, "_full_result", fake_full)
    out = await sim_tools.start_debate("sim-1")
    assert out["error"] == "sim_not_ready"


@pytest.mark.asyncio
async def test_start_debate_triggers(monkeypatch):
    from domain.chat.adapters import sim_tools
    from domain.simulation.contracts import schemas as simschemas

    async def fake_full(sim_id):
        return {
            "reactions": [{"x": 1}],
            "ad_analysis": None,
            "personas": [],
            "rubric_scores": [],
            "objective_fit": None,
        }

    monkeypatch.setattr(sim_tools, "_full_result", fake_full)
    # 스키마 검증 우회 — 트리거 배선(반응→svc.start)만 검증.
    monkeypatch.setattr(simschemas.PersonaReaction, "model_validate", classmethod(lambda cls, d: d))

    started = {}

    class FakeSvc:
        async def start(
            self, reactions, ad_analysis, *, simulation_id, personas, rubric, objective_fit
        ):
            started["sim"] = simulation_id
            started["reactions"] = reactions
            return "run-xyz"

    import domain.simulation.wiring as simwiring

    monkeypatch.setattr(simwiring, "build_debate_service", lambda settings: FakeSvc())

    out = await sim_tools.start_debate("sim-1")
    assert out["run_id"] == "run-xyz"
    assert started["sim"] == "sim-1"
    assert started["reactions"] == [{"x": 1}]
