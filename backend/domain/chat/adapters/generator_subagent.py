# 생성(generator) 서브에이전트 어댑터 — ReAct(자연어 질의)·읽기·트리거(비동기 시작) 매핑.
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from domain.chat.contracts.agent_io import Citation, Route, SubAgentResult

if TYPE_CHECKING:
    from domain.chat.contracts.agent_io import SubAgentRequest

_UNSET = object()


class GeneratorSubAgent:
    """generator 도메인 진입점을 감싸는 서브에이전트 어댑터.

    - 풀모드(키 있음): gen_agent ReAct가 자연어 질문을 gen_detail/gen_list/search_kb로 답함.
    - 폴백(use_mock/키 없음): generation_id면 상세 요약, 상품정보(product_name)면 트리거.
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
        self._agent: Any = _UNSET

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

    def _get_agent(self) -> Any:
        """ReAct 에이전트(풀모드) 또는 None(폴백). 1회 lazy-build."""
        if self._agent is _UNSET:
            from core.config import settings
            from domain.chat.adapters.gen_agent import build_generator_agent

            self._agent = build_generator_agent(settings)
        return self._agent

    async def run(self, req: SubAgentRequest) -> SubAgentResult:  # type: ignore[name-defined]
        try:
            return await self._dispatch(req)
        except Exception as exc:  # noqa: BLE001
            return SubAgentResult(route=Route.GENERATION, error=str(exc))

    async def _dispatch(self, req: SubAgentRequest) -> SubAgentResult:  # type: ignore[name-defined]
        generation_id = req.context_ids.get("generation_id")
        product_name = (req.knobs or {}).get("product_name")

        # --- 풀모드 ReAct: 조회 + 트리거(슬롯필링 start_generation)를 모두 처리 ---
        # (상품정보를 자연어로 받아 확인 후 start_generation으로 실행 — knobs 의존 없음)
        agent = self._get_agent()
        if agent is not None:
            from domain.chat.adapters.history import history_to_preamble  # noqa: PLC0415

            question = history_to_preamble(req.history) + req.question
            out = await agent(question, req.context_ids)
            triggered = out.get("triggered") or {}
            gen_data = out.get("gen_data") or {}
            detail = gen_data.get("detail") if isinstance(gen_data, dict) else None
            # 트리거(진행률 위젯) 우선, 없으면 조회 상세를 structured로 노출.
            if triggered:
                structured = {"kind": "generation_started", "data": triggered}
            elif detail:
                structured = {"kind": "generation_detail", "data": detail}
            else:
                structured = {}
            return SubAgentResult(
                route=Route.GENERATION,
                answer=out.get("answer") or "결과를 가져왔어요.",
                citations=[
                    Citation(kind="kb", source=c.get("source", ""), title=c.get("title", ""))
                    for c in out.get("kb_citations", [])
                ],
                used_tools=list(out.get("used_tools", [])),
                structured=structured,
            )

        # --- 폴백(키 없음/mock): 구조화(트리거는 knobs 상품정보 기반) ---
        if product_name and not generation_id:
            return await self._start(req)
        if generation_id:
            return await self._fallback_detail(generation_id)
        return SubAgentResult(
            route=Route.GENERATION,
            answer=(
                "어떤 생성 작업이 궁금하신가요? generation_id를 알려주시거나, "
                "새로 만들려면 상품 정보(이름·설명·타깃)를 주세요."
            ),
        )

    async def _start(self, req: SubAgentRequest) -> SubAgentResult:  # type: ignore[name-defined]
        from domain.generator.contracts.enums import GenerationMode
        from domain.generator.contracts.schemas import GenerationCreateRequest

        start_fn, _ = self._get_fns()
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

    async def _fallback_detail(self, generation_id: str) -> SubAgentResult:
        _, detail_fn = self._get_fns()
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
