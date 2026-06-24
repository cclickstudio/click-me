# ChatOrchestratorService — 슈퍼바이저 그래프를 구동하고 SSE 프레임을 생성한다.
"""astream(updates) → SSE 프레임 변환·HITL approval_request·resume 지원."""

from __future__ import annotations

import contextlib
import json
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from domain.chat.contracts.agent_io import ChatTurnRequest, Route

if TYPE_CHECKING:
    from domain.chat.contracts.ports import ChatRepo

# 라우트 → SSE meta 레이블 맵
_ROUTE_LABEL: dict[str, str] = {
    Route.MANAGEMENT: "광고 매니지먼트",
    Route.SIMULATION: "광고 시뮬레이터",
    Route.GENERATION: "광고 생성",
    Route.GENERAL: "일반 답변",
}

_ROUTE_ENGINE: dict[str, str] = {
    Route.MANAGEMENT: "management_subagent",
    Route.SIMULATION: "simulation_subagent",
    Route.GENERATION: "generator_subagent",
    Route.GENERAL: "direct",
}

# synthesize 답변을 토큰 청크로 분할하는 크기
_CHUNK_SIZE = 24


def _chunks(text: str, size: int = _CHUNK_SIZE) -> list[str]:
    """텍스트를 size 단위로 분할한다."""
    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]


def _frame(obj: dict) -> str:
    """dict → SSE data 프레임 문자열."""
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


class ChatOrchestratorService:
    """슈퍼바이저 그래프를 구동하고 SSE 프레임을 생성하는 서비스."""

    def __init__(self, *, graph, repo: ChatRepo, settings=None) -> None:
        self._graph = graph
        self._repo = repo
        self._settings = settings

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────────

    async def _ensure_session(self, req: ChatTurnRequest) -> None:
        """세션이 없으면 생성한다(best-effort)."""
        try:
            session = await self._repo.get_session(req.session_id)
            if session is None:
                await self._repo.create_session(
                    session_id=req.session_id,
                    project_id=req.project_id,
                    user_id=req.user_id,
                    organization_id=req.organization_id,
                    title="새 채팅",
                )
        except Exception:  # noqa: BLE001
            pass

    async def _persist_user(self, req: ChatTurnRequest) -> None:
        """사용자 메시지를 영속한다(best-effort)."""
        with contextlib.suppress(Exception):
            await self._repo.append_message(
                session_id=req.session_id,
                role="user",
                content=req.user_text,
                route=None,
                meta={},
            )

    async def _persist_assistant(
        self,
        session_id,
        content: str,
        route: str | None,
        meta: dict,
    ) -> None:
        """어시스턴트 메시지를 영속한다(best-effort)."""
        with contextlib.suppress(Exception):
            await self._repo.append_message(
                session_id=session_id,
                role="assistant",
                content=content,
                route=route,
                meta=meta,
            )

    # ── 공개 API ─────────────────────────────────────────────────────────────

    async def stream(self, req: ChatTurnRequest) -> AsyncGenerator[str, None]:
        """한 챗 턴을 실행하고 SSE 프레임을 yield한다."""
        thread_id = str(req.session_id)
        config = {"configurable": {"thread_id": thread_id}}

        # 세션·사용자 메시지 영속 (best-effort)
        await self._ensure_session(req)
        await self._persist_user(req)

        # 초기 상태
        initial: dict = {
            "messages": [HumanMessage(content=req.user_text)],
            "context_ids": {
                "session_id": str(req.session_id),
                "ad_id": req.context_ad_id,
                "campaign_id": req.context_campaign_id,
                "simulation_id": req.context_simulation_id,
            },
            "project_id": str(req.project_id) if req.project_id else None,
            "user_id": str(req.user_id) if req.user_id else None,
            "organization_id": str(req.organization_id) if req.organization_id else None,
        }

        # 라우트·답변 상태 추적
        current_route: str | None = None
        final_answer: str = ""

        try:
            # meta 프레임을 첫 번째로 emit (route 미확정 단계)
            yield _frame(
                {
                    "meta": {
                        "route": None,
                        "source": None,
                        "label": None,
                        "engine": None,
                        "thread_id": thread_id,
                        "requires_approval": False,
                    }
                }
            )

            async for update in self._graph.astream(initial, config, stream_mode="updates"):
                # ── interrupt 감지 ──────────────────────────────────────────
                if "__interrupt__" in update:
                    interrupts = update["__interrupt__"]
                    # (Interrupt(value={...}), ) 형태 — 첫 번째 항목 사용
                    intr = interrupts[0]
                    intr_value = intr.value if hasattr(intr, "value") else intr
                    ar = intr_value.get("approval_request", {})
                    yield _frame(
                        {
                            "approval_request": {
                                "tier": ar.get("tier"),
                                "action_type": ar.get("action_type"),
                                "target_campaign_id": ar.get("target_campaign_id"),
                                "thread_id": thread_id,
                                "rationale": ar.get("rationale"),
                            }
                        }
                    )
                    yield _frame({"done": {"finish_reason": "awaiting_approval"}})
                    return

                # ── supervisor 노드 ─────────────────────────────────────────
                if "supervisor" in update:
                    sup_update = update["supervisor"]
                    current_route = sup_update.get("route")
                    label = _ROUTE_LABEL.get(current_route, current_route or "")
                    engine = _ROUTE_ENGINE.get(current_route, "direct")
                    # route 확정 후 meta 재emit — 두 번째 meta가 canonical(프론트가 덮어씀).
                    yield _frame(
                        {
                            "meta": {
                                "route": current_route,
                                "source": current_route,
                                "label": label,
                                "engine": engine,
                                "thread_id": thread_id,
                                "requires_approval": False,
                            }
                        }
                    )

                # ── delegate 노드 ───────────────────────────────────────────
                if "delegate" in update:
                    del_update = update["delegate"]
                    label = _ROUTE_LABEL.get(current_route or "", current_route or "서브에이전트")
                    yield _frame(
                        {
                            "tool_status": {
                                "agent": current_route,
                                "state": "running",
                                "label": label,
                            }
                        }
                    )
                    # structured 결과 emit
                    for sr in del_update.get("sub_results") or []:
                        structured = sr.get("structured") or {}
                        if (
                            structured
                            and structured.get("kind")
                            and structured.get("data") is not None
                        ):
                            yield _frame(
                                {
                                    "result": {
                                        "kind": structured["kind"],
                                        "data": structured["data"],
                                    }
                                }
                            )

                # ── synthesize 노드 ─────────────────────────────────────────
                if "synthesize" in update:
                    syn_update = update["synthesize"]
                    final_answer = syn_update.get("final_answer") or ""
                    for chunk in _chunks(final_answer):
                        yield _frame({"token": {"text": chunk}})

            # 루프 정상 종료 — 어시스턴트 메시지 영속
            await self._persist_assistant(
                session_id=req.session_id,
                content=final_answer,
                route=current_route,
                # TODO(v2): sub_results citations/used_tools를 meta에 저장(현재 리플레이 시 유실).
                meta={},
            )
            yield _frame({"done": {"finish_reason": "stop"}})

        except Exception as exc:  # noqa: BLE001
            yield _frame({"error": {"message": str(exc)}})
            yield _frame({"done": {"finish_reason": "error"}})

    async def resume(self, thread_id: str, decision: dict) -> AsyncGenerator[str, None]:
        """HITL 승인/거부 후 그래프를 재개하고 SSE 프레임을 yield한다."""
        config = {"configurable": {"thread_id": thread_id}}
        final_answer: str = ""
        current_route: str | None = None

        try:
            # 인터럽트 없는 thread에 resume하면 빈 스트림/예외 — outer except가 error 프레임 처리.
            async for update in self._graph.astream(
                Command(resume=decision), config, stream_mode="updates"
            ):
                # ── execute 노드 ────────────────────────────────────────────
                if "execute" in update:
                    exec_update = update["execute"]
                    execution_result = exec_update.get("execution_result")
                    if execution_result:
                        yield _frame(
                            {
                                "result": {
                                    "kind": "execution_result",
                                    "data": execution_result,
                                }
                            }
                        )

                # ── synthesize 노드 ─────────────────────────────────────────
                if "synthesize" in update:
                    syn_update = update["synthesize"]
                    final_answer = syn_update.get("final_answer") or ""
                    for chunk in _chunks(final_answer):
                        yield _frame({"token": {"text": chunk}})

                # ── supervisor (재개 후 라우트 확인용) ─────────────────────
                if "supervisor" in update:
                    current_route = update["supervisor"].get("route")

            # 어시스턴트 메시지 영속 (session_id 복원 불가 시 무시)
            with contextlib.suppress(Exception):
                session_id_val = config["configurable"].get("thread_id")
                if session_id_val:
                    await self._persist_assistant(
                        session_id=uuid.UUID(session_id_val),
                        content=final_answer,
                        route=current_route,
                        # TODO(v2): citations/used_tools를 meta 저장(현재 리플레이 시 유실).
                        meta={},
                    )

            yield _frame({"done": {"finish_reason": "stop"}})

        except Exception as exc:  # noqa: BLE001
            yield _frame({"error": {"message": str(exc)}})
            yield _frame({"done": {"finish_reason": "error"}})
