# 생성(generator) 서브에이전트 어댑터 — 읽기(상세 조회)·트리거(비동기 시작) 매핑.
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from pydantic import ValidationError

from domain.chat.contracts.agent_io import Route, SubAgentResult

if TYPE_CHECKING:
    from domain.chat.contracts.agent_io import SubAgentRequest


class GeneratorSubAgent:
    """generator 도메인 진입점을 감싸는 서브에이전트 어댑터.

    - context_ids["generation_id"] 있으면 읽기(get_detail)
    - 없으면 트리거(비동기 start_generation, generation_id 안내)
    - start_fn/detail_fn=None 이면 사용 시점에 lazy-import (테스트는 fake 주입).
    """

    route: str = Route.GENERATION

    def __init__(
        self,
        start_fn: Callable | None = None,
        detail_fn: Callable | None = None,
    ) -> None:
        self._start_fn = start_fn
        self._detail_fn = detail_fn

    def _get_fns(self) -> tuple[Callable, Callable]:
        # 한쪽만 주입된 경우 주입분을 덮어쓰지 않도록 독립 체크.
        if self._start_fn is None or self._detail_fn is None:
            from domain.generator.service.generator_service import (
                get_detail,
                start_generation,
            )

            if self._start_fn is None:
                self._start_fn = start_generation
            if self._detail_fn is None:
                self._detail_fn = get_detail
        return self._start_fn, self._detail_fn

    async def run(self, req: SubAgentRequest) -> SubAgentResult:  # type: ignore[name-defined]
        try:
            return await self._dispatch(req)
        except Exception as exc:
            return SubAgentResult(route=Route.GENERATION, error=str(exc))

    async def _dispatch(self, req: SubAgentRequest) -> SubAgentResult:  # type: ignore[name-defined]
        start_fn, detail_fn = self._get_fns()
        generation_id = req.context_ids.get("generation_id")

        # --- 읽기 경로: 기존 generation_id로 상세 조회 ---
        if generation_id:
            detail = await detail_fn(generation_id)
            if detail is None:
                return SubAgentResult(
                    route=Route.GENERATION,
                    answer="해당 생성 결과를 찾지 못했어요. generation_id를 다시 확인해 주세요.",
                )
            candidates = detail.get("candidates", [])
            passed = sum(1 for c in candidates if c.get("qa_passed"))
            answer = (
                f"생성 결과 (상태: {detail.get('status', '알 수 없음')}) — "
                f"후보 {len(candidates)}개 중 QA 통과 {passed}개."
            )
            return SubAgentResult(
                route=Route.GENERATION,
                answer=answer,
                structured={"kind": "generation_detail", "data": detail},
            )

        # --- 트리거 경로: 새 시안 생성 비동기 시작 ---
        from domain.generator.contracts.enums import GenerationMode
        from domain.generator.contracts.schemas import GenerationCreateRequest

        try:
            gen_req = GenerationCreateRequest(
                mode=GenerationMode.CREATE,
                product_name=req.knobs.get("product_name", ""),
                product_description=req.knobs.get("product_description", ""),
                target_audience=req.knobs.get("target_audience", ""),
                campaign_objective=req.knobs.get("campaign_objective", "conversion"),
                project_id=req.context_ids.get("project_id"),
            )
        except ValidationError as exc:
            first_msg = exc.errors()[0].get("msg", "")
            return SubAgentResult(
                route=Route.GENERATION,
                error=(f"상품 정보가 필요해요. 누락된 필드: {exc.error_count()}개. {first_msg}"),
            )

        gid: str = await start_fn(gen_req, created_by=None)
        return SubAgentResult(
            route=Route.GENERATION,
            answer=(
                f"시안 생성을 시작했어요 (id: {gid}). 잠시 후 generation_id로 결과를 조회해 주세요."
            ),
        )
