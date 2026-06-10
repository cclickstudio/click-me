from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from core.schemas import SimulationRequest, SimulationTaskResponse
from domain.simulation.service import simulation_service

router = APIRouter()


@router.post("/reactions", response_model=SimulationTaskResponse)
async def start_simulation(body: SimulationRequest, request: Request):
    ssr_scorer = request.app.state.ssr_scorer
    task_id = await simulation_service.start_simulation(body, ssr_scorer)
    return SimulationTaskResponse(
        task_id=task_id,
        stream_url=f"/api/simulate/{task_id}/stream",
    )


@router.get("/{task_id}/stream")
async def stream_simulation(task_id: str):
    return StreamingResponse(
        simulation_service.stream_events(task_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{task_id}/result")
async def get_result(task_id: str):
    result = simulation_service.get_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found or simulation not completed")
    return result


@router.post("/debate")
async def debate_stub():
    raise HTTPException(status_code=501, detail="Debate Agent는 7.8 목표 기능입니다.")
