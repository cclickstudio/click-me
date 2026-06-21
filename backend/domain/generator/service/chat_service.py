# 챗봇 세션 관리 — 인메모리, 새로고침 시 초기화 (DB 전환은 팀 조율 후)
from __future__ import annotations

import uuid
from uuid import UUID

from domain.generator.chat.agent import run_agent
from domain.generator.chat.state import ChatSession
from domain.generator.contracts.schemas import GenerationCreateRequest
from domain.generator.service import generator_service

_REQUIRED = ("product_name", "product_description", "target_audience")

_sessions: dict[str, ChatSession] = {}


def create_session(project_id: str | None = None) -> str:
    """새 챗봇 세션 생성 — session_id 반환."""
    session_id = str(uuid.uuid4())
    _sessions[session_id] = ChatSession(session_id=session_id, project_id=project_id)
    return session_id


def get_session(session_id: str) -> ChatSession | None:
    return _sessions.get(session_id)


async def handle_message(
    session_id: str,
    content: str,
    created_by: UUID | None = None,
    extra_fields: dict | None = None,
) -> dict:
    """사용자 메시지 처리 — AI 응답 + 상태 반환.

    반환: {response, partial_request, status, generation_id}
    """
    session = _sessions.get(session_id)
    if not session:
        raise KeyError(f"세션을 찾을 수 없습니다: {session_id}")

    if session.status == "generating":
        return {
            "response": "이미 광고 생성이 진행 중이에요.",
            "partial_request": session.partial_request,
            "status": session.status,
            "generation_id": session.generation_id,
        }

    # 파일 업로드 키 등 프론트에서 직접 전달된 필드 병합
    if extra_fields:
        for key, value in extra_fields.items():
            if value:
                session.partial_request[key] = value

    session.messages.append({"role": "user", "content": content})

    result = await run_agent(session.messages, session.partial_request)

    # 이번 턴에서 새로 추출된 필드 병합
    for key, value in (result.get("extracted") or {}).items():
        if value:
            session.partial_request[key] = value

    response_text = result.get("response", "")
    generation_id: str | None = None

    if result.get("ready_to_generate"):
        missing = [f for f in _REQUIRED if not (session.partial_request.get(f) or "").strip()]
        if missing:
            # 필드가 부족하면 생성하지 않고 다시 수집 단계로
            response_text = f"아직 {', '.join(missing)} 정보가 필요해요. 알려주시겠어요?"
        else:
            try:
                req_data = {**session.partial_request}
                if session.project_id:
                    req_data["project_id"] = session.project_id
                req = GenerationCreateRequest(**req_data)
                generation_id = await generator_service.start_generation(req, created_by)
                session.status = "generating"
                session.generation_id = generation_id
            except Exception as e:
                response_text = f"생성 시작 중 문제가 생겼어요: {e}"

    session.messages.append({"role": "assistant", "content": response_text})

    return {
        "response": response_text,
        "partial_request": session.partial_request,
        "status": session.status,
        "generation_id": generation_id,
    }
