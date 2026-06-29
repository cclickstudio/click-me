# 채팅 어시스턴트 공통 계약 — 오케스트레이터↔도메인 서브에이전트 seam(중립 위치)
"""도메인(generator/management/...)과 전송계층(api/assistant)이 함께 쓰는 입출력 계약.

core에 두는 이유 — 도메인이 api를 import하면 의존 방향이 역전(domain→api)된다.
순수 스키마만 두어 api→core, domain→core(둘 다 하향)를 지킨다.
management의 AskRequest/AskResult를 일반화한 형태.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from core.schemas import ChatMessage


class Intent(StrEnum):
    """최상위 의도 — 도메인 라우팅 키. 레지스트리 등록 키와 1:1."""

    GENERATE = "generate"
    SIMULATE = "simulate"
    MANAGE = "manage"
    RETRIEVE = "retrieve"
    ADVISE = "advise"  # 일반 조언(폴백)


class Action(StrEnum):
    """서브에이전트가 한 턴에서 취한 행동."""

    ASK = "ask"  # 정보가 부족 — 사용자에게 되묻는다(message가 질문)
    TRIGGER = "trigger"  # 백그라운드 잡을 시작 — started_event 동봉
    ANSWER = "answer"  # 즉답 완료


class ProjectRef(BaseModel):
    """프로젝트 되묻기용 후보(id+이름)."""

    id: str
    name: str


class StartedEvent(BaseModel):
    """백그라운드 잡 핸드오프 — 프론트가 stream_url을 구독한다."""

    event: str  # 예: generation_started
    job_id: str
    stream_url: str
    domain: str  # generator | simulation | ...


class SubagentRequest(BaseModel):
    """오케스트레이터 → 서브에이전트 표준 입력."""

    messages: list[ChatMessage] = Field(default_factory=list)  # 대화 히스토리(무상태 재전송)
    session_id: str = ""  # LangSmith thread 상관키
    user_id: str | None = None  # 인증 유저(없으면 미인증 채팅)
    org_id: str | None = None
    project_id: str | None = None  # 프론트가 활성 프로젝트를 줬다면(현재는 보통 None)
    context_ad_id: str | None = None  # 특정 광고 맥락(management 시뮬 예측 연결)
    improve_context: dict | None = (
        None  # 개선 모드 컨텍스트 {s3_key, simulation_summary, product_name?}
    )
    # 세션 넘는 장기기억 회수 결과(로그인 사용자만, chat.py가 recall→포맷해 주입). 비로그인은 None.
    memory_context: str | None = None
    available_projects: list[ProjectRef] = Field(
        default_factory=list
    )  # 되묻기용 — 오케스트레이터가 generate 라우팅 시 채운다

    @property
    def last_user_text(self) -> str:
        for m in reversed(self.messages):
            if m.role == "user":
                return m.content
        return ""


class SubagentResult(BaseModel):
    """서브에이전트 → 오케스트레이터 표준 출력."""

    action: Action
    message: str = ""  # 사용자에게 보일 텍스트(되묻기 질문 or 확인 메시지)
    meta: dict = Field(default_factory=dict)  # 출처/엔진/인용 등 프론트 표시용
    started_event: StartedEvent | None = None  # action=TRIGGER일 때 잡 핸드오프
