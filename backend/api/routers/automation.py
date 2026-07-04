# 자동화 실행 결과 조회 API — APScheduler 워커가 남긴 결과를 프론트가 읽는다(3도메인 공용)
"""워커(감지·진단·집계)가 automation_runs에 남긴 결과를 프론트가 조회하는 읽기 전용 API.

탭이 열려 있지 않아도 서버가 이미 해둔 결과를 화면이 읽는 구조. 승인이 필요한 write는
여기서 안 다룬다(워커 밖) — suggested_action은 승인 플로로 가는 힌트일 뿐.
"""

from fastapi import APIRouter, Depends

from core.auth import get_current_user_optional
from core.automation import recent_automation_runs
from core.models import User

router = APIRouter()


@router.get("/runs")
async def list_automation_runs(
    project_id: str | None = None,
    domain: str | None = None,
    unresolved: bool = False,
    limit: int = 20,
    _user: User | None = Depends(get_current_user_optional),
) -> dict:
    """워커 자동화 결과 최신순 조회.

    domain=management|generation|simulation(선택), project_id 필터(선택), unresolved=미해결만.
    """
    runs = await recent_automation_runs(
        project_id=project_id,
        domain=domain,
        limit=min(max(limit, 1), 100),
        unresolved_only=unresolved,
    )
    return {"runs": runs, "count": len(runs)}
