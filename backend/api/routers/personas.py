from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.access import assert_simulation_access
from core.auth import get_current_user
from core.db import get_db
from core.models import User
from tools.persona.factory import run_persona_factory

router = APIRouter()


@router.post("/generate")
async def generate_personas(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    simulation_id = body.get("simulation_id", "")
    if simulation_id:
        await assert_simulation_access(db, simulation_id, current_user)
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
