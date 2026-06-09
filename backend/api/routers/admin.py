"""Admin router — 관리자 전용 엔드포인트."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/inquiries")
async def list_inquiries() -> list:
    # TODO: 고객 문의 목록 조회
    raise NotImplementedError


@router.post("/inquiries")
async def create_inquiry() -> dict:
    # TODO: 고객 문의 저장
    raise NotImplementedError


@router.get("/stats")
async def get_stats() -> dict:
    # TODO: 시뮬레이션 실행 수, 광고 수 등 집계
    raise NotImplementedError
