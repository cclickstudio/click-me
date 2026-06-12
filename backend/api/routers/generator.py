from fastapi import APIRouter

from domain.generator.contracts.schemas import GenerateRequest, GenerateResult, ImproveRequest
from domain.generator.service.generator_service import generate_ad, improve_ad

router = APIRouter()


@router.post("/generate", response_model=GenerateResult)
async def generate(body: GenerateRequest) -> GenerateResult:
    return await generate_ad(body)


@router.post("/improve", response_model=GenerateResult)
async def improve(body: ImproveRequest) -> GenerateResult:
    return await improve_ad(body)
