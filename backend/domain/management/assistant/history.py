# 어시스턴트 대화·에이전트 실행 기록 — management_chat_*/agent_runs 적재(관측·평가 기반).
"""한 턴(user 질문 → assistant 답변 + 도구/인용/HITL)을 DB에 영속한다.

best-effort: 적재 실패가 채팅 응답을 끊지 않는다. 멀티턴은 thread_id로 한 세션에 묶인다.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from core.db import AsyncSessionLocal
from core.models import ManagementAgentRun, ManagementChatMessage, ManagementChatSession

logger = logging.getLogger("clickme")


async def record_turn(
    *,
    thread_id: str,
    question: str,
    answer: str,
    model: str | None = None,
    latency_ms: int | None = None,
    used_tools: list | None = None,
    citations: list | None = None,
    suggested_action: dict | None = None,
    requires_approval: bool = False,
    campaign_id: str | None = None,
    ad_id: str | None = None,
) -> None:
    """한 턴을 세션·메시지·에이전트 실행으로 적재. 실패는 로그만(채팅 유지)."""
    try:
        async with AsyncSessionLocal() as db:
            sess = (
                await db.execute(
                    select(ManagementChatSession).where(
                        ManagementChatSession.thread_id == thread_id
                    )
                )
            ).scalars().first()
            if sess is None:
                sess = ManagementChatSession(
                    thread_id=thread_id, campaign_id=campaign_id, ad_id=ad_id
                )
                db.add(sess)
                await db.flush()
            else:
                sess.last_active_at = datetime.now(UTC)
            db.add(
                ManagementChatMessage(
                    session_id=sess.id,
                    thread_id=thread_id,
                    role="user",
                    content=question,
                    campaign_id=campaign_id,
                )
            )
            amsg = ManagementChatMessage(
                session_id=sess.id,
                thread_id=thread_id,
                role="assistant",
                content=answer,
                model=model,
                latency_ms=latency_ms,
                campaign_id=campaign_id,
            )
            db.add(amsg)
            await db.flush()
            db.add(
                ManagementAgentRun(
                    session_id=sess.id,
                    thread_id=thread_id,
                    message_id=amsg.id,
                    tools_used=used_tools or [],
                    citations=citations or [],
                    suggested_action=suggested_action,
                    interrupt_state={"requires_approval": True} if requires_approval else None,
                )
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001 — 관측 적재 실패가 채팅을 막지 않게
        logger.warning("어시스턴트 턴 적재 실패(무시): %s", exc)
