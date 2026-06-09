from fastapi import APIRouter

from tools.persona.factory import run_persona_factory

router = APIRouter()


@router.post("/generate")
async def generate_personas(body: dict):
    simulation_id = body.get("simulation_id", "")
    count = body.get("count", 20)
    ad_analysis = body.get("ad_analysis", {})
    segment_distribution = body.get("segment_distribution", {})

    personas = await run_persona_factory(
        simulation_id=simulation_id,
        count=count,
        ad_analysis=ad_analysis,
        segment_distribution=segment_distribution,
    )

    return {
        "simulation_id": simulation_id,
        "personas": [p.model_dump() for p in personas],
    }
