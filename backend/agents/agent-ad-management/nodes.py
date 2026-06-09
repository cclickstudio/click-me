"""Ad Management Agent — LangGraph 노드 함수."""

from agents.agent_ad_management.state import ManagementState


async def validate_ad(state: ManagementState) -> ManagementState:
    """광고 집행 전 유효성 검증 (S3 파일 존재 여부, 플랫폼 스펙 등)."""
    # TODO: 플랫폼별 광고 규격 검증
    return state


async def dispatch_to_platforms(state: ManagementState) -> ManagementState:
    """각 플랫폼 API에 광고 게시 / 내리기 요청."""
    # TODO: 플랫폼별 API 툴 병렬 호출
    return state


async def record_result(state: ManagementState) -> ManagementState:
    """집행 결과 DB 저장."""
    # TODO: DB 기록
    return state
