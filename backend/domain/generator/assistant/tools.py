# 광고 생성 어시스턴트 결과조회 도구 — 저장된 생성 결과를 후보·전략 요약으로
"""숫자·사실(후보·전략·QA)은 여기(저장된 결과)서만 가져온다. 전략·원칙은 KB(retriever)로 분리."""

from __future__ import annotations


async def fetch_generation_result(generation_id: str) -> dict:
    """generation_id로 저장된 생성 결과의 후보·전략·선택 요약. 없으면 error 키."""
    # lazy import — generator_service는 이미지 생성 파이프라인을 모듈 로드 시 끌어와 무겁다.
    from domain.generator.service import generator_service  # noqa: PLC0415

    detail = await generator_service.get_detail(generation_id)
    if detail is None:
        return {"error": "not_found"}
    cands = detail.get("candidates") or []
    return {
        "generation_id": detail.get("generation_id"),
        "status": detail.get("status"),
        "candidate_count": len(cands),
        "selected_candidate_id": detail.get("selected_candidate_id"),
        "candidates": [
            {
                "candidate_id": c.get("candidate_id"),
                "strategy": c.get("strategy"),
                "headline": (c.get("copy") or {}).get("headline"),
                "qa_passed": c.get("qa_passed"),
            }
            for c in cands
        ],
        "error_message": detail.get("error_message"),
    }


async def run_generation(
    product_name: str,
    product_description: str,
    target_audience: str,
    campaign_objective: str = "conversion",
    project_id: str | None = None,
) -> dict:
    """채팅에서 광고 시안 생성을 시작한다(백그라운드). generation_id 반환.

    mode는 기본 CREATE, created_by 생략(anonymous), project_id 없으면 프로젝트 미귀속.
    생성은 오래 걸려 동기 대기하지 않고 generation_id만 돌려준다(결과는 추후 조회).
    """
    from domain.generator.contracts.schemas import GenerationCreateRequest  # noqa: PLC0415
    from domain.generator.service import generator_service  # noqa: PLC0415

    req = GenerationCreateRequest(
        product_name=product_name,
        product_description=product_description,
        target_audience=target_audience,
        campaign_objective=campaign_objective,
        project_id=project_id,
    )
    generation_id = await generator_service.start_generation(req)
    return {
        "generation_id": generation_id,
        "stream_url": f"/api/generator/generations/{generation_id}/stream",
    }
