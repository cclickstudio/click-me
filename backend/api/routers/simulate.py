"""Simulation router — SQS 비동기 큐 연동."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class SimulationRequest(BaseModel):
    ad_id: str
    persona_count: int = Field(default=20, ge=1, le=1000)


class SimulationJobResponse(BaseModel):
    job_id: str
    status: str


@router.post("/", response_model=SimulationJobResponse)
async def start_simulation(body: SimulationRequest) -> SimulationJobResponse:
    # TODO: SQS에 시뮬레이션 작업 enqueue → job_id 반환
    raise NotImplementedError


@router.get("/{job_id}/status")
async def get_simulation_status(job_id: str) -> dict:
    # TODO: 시뮬레이션 진행 상태 조회 (SSE 또는 polling)
    raise NotImplementedError


@router.get("/{job_id}/result")
async def get_simulation_result(job_id: str) -> dict:
    # TODO: 완료된 시뮬레이션 결과 (분포 데이터) 반환
    raise NotImplementedError
