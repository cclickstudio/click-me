# 페르소나 토론 파이프라인(조각 8~11) 전용 DTO — 반응분석·선발·배정·토론산출 계약
#
# contracts/schemas.py(도메인 공용)와 분리. 조각 8(반응분석)·9(KPI)·10(선발/배정/토론)·11(리포트)이
# 주고받는 내부 스키마를 한 곳에 모은다. 8·9·10-a·10-b는 결정론(LLM✗), 10-c·11만 LLM.
from __future__ import annotations

from pydantic import BaseModel, Field

# AISAS 5단계 — 퍼널 순서 고정(이 순서로만 인접 비교).
AISAS_STAGES: list[str] = ["attention", "interest", "search", "action", "share"]


class FunnelStage(BaseModel):
    """AISAS 단계별 통과 현황 — 인원 카운트 기반(qa_passed 표본만)."""

    stage: str
    passed: int  # 이 단계 flag == true 인 인원 수
    pass_rate: float  # passed / total_n (총원 대비, 0~1)


class Bottleneck(BaseModel):
    """최대 이탈 구간 — 인접 단계 간 인원 감소가 가장 큰 곳(토론 주제 근거)."""

    from_stage: str
    to_stage: str
    dropped: int  # from.passed - to.passed (양수)
    drop_rate: float  # dropped / from.passed (직전 단계 대비 이탈률)


class GroupMembers(BaseModel):
    """소비자 그룹별 멤버(persona_id) — 조각 10-a 선발의 후보 풀.

    한 사람이 여러 그룹에 동시 소속 가능(겹침 허용). 배타 배정은 선발(10-a) 책임.
    """

    finishers: list[str] = Field(default_factory=list)  # 완주자: action == true
    undecided: list[str] = Field(default_factory=list)  # 미온 다수: interest and not action
    rejectors: list[str] = Field(default_factory=list)  # 거부자: rejected == true
    distrusters: list[str] = Field(default_factory=list)  # 불신자: emotion_tag == distrust
    early_drop: list[str] = Field(default_factory=list)  # 초기이탈: drop_stage == interest


class RejectionBreakdown(BaseModel):
    """거부·불신 분해 — 거부율 + 사유 + 불신 인원."""

    rejected_count: int
    rejection_rate: float  # rejected_count / total_n (인원 기반, 9의 가중 거부율과 별개)
    by_rejection_reason_tag: dict[str, int] = Field(default_factory=dict)
    distrust_count: int = 0  # emotion_tag == distrust 인원


class ReactionAnalysis(BaseModel):
    """조각 8 산출 — 반응 데이터의 구조적 분석(결정론, LLM✗).

    funnel/bottleneck = 어디서 새는가, groups = 누가 어떤 무리인가(선발 후보 풀),
    breakdown/emotion_dist = 왜 새는가. 조각 10-a(선발)·11(리포트)이 소비한다.
    """

    total_n: int  # qa_passed 표본 수
    funnel: list[FunnelStage]
    bottleneck: Bottleneck | None = None  # 표본 0 또는 이탈 없음이면 None
    by_drop_stage: dict[str, int] = Field(default_factory=dict)
    by_drop_reason_tag: dict[str, int] = Field(default_factory=dict)
    emotion_dist: dict[str, int] = Field(default_factory=dict)
    rejection: RejectionBreakdown
    groups: GroupMembers


class SelectedParticipant(BaseModel):
    """조각 10-a 선발 1명 — 슬롯·역할·입장점수. 배타 배정(한 사람 1슬롯)."""

    persona_id: str
    slot: int  # 1~6 (1완주자 2피벗 3거부자 4불신자 5초기이탈 6미온다수2)
    role: str  # 한글 역할 라벨
    stance_score: float  # ③ 모델 배정 전용 입장 점수(피벗 선정엔 안 씀)
    is_fallback: bool = False  # 해당 슬롯 후보 없어 다음 우선순위에서 보충됐는지


class SelectedPanel(BaseModel):
    """조각 10-a 산출 — 토론 패널(기본 6명). groups 후보 풀에서 결정론 규칙으로 선발."""

    participants: list[SelectedParticipant]
    pivot_id: str | None = None  # 피벗 persona_id(10-b 엔진 배정에서 Haiku 고정)
    critic_secured: bool = False  # 비판자(부정 입장) 최소 1명 확보 여부


class DebateParticipant(BaseModel):
    """조각 10-b 산출 1명 — 선발 결과 + 엔진·이름·프로필. 토론·DB·리포트 입력."""

    persona_id: str
    slot: int
    role: str
    stance_score: float
    is_fallback: bool = False
    engine: str  # haiku / gpt / gemini (토론자). 입장순 교차 배정, 피벗은 haiku 고정.
    persona_name: str  # 결정론 부여 이름(운영은 factory 이름 승계). 리포트 표시용.
    persona_profile: str  # 역할 기반 한 줄 프로필(더미엔 인구정보 없음)


class AssignedPanel(BaseModel):
    """조각 10-b 산출 — 엔진·이름 배정 끝난 토론 패널. judge는 별도 고정(Opus)."""

    participants: list[DebateParticipant]
    pivot_id: str | None = None
    judge_engine: str = "opus"
    critic_secured: bool = False


class DebateTopic(BaseModel):
    """조각 9 산출 — 토론 주제(결정론). 8의 병목 + 9의 KPI + 캠페인 목표에서 파생.

    LLM 토론(10-c)의 시드 문장. 항상 실제 수치에 grounded(지어내지 않음).
    """

    headline: str  # 토론 제시 문장 ("신뢰 높은데 클릭 안 됨 — 무엇이 막나?")
    diagnosis: str  # 진단부(수치 근거)
    question: str  # 질문부(토론이 풀 것)
    primary_signal: (
        str  # 주신호 종류: rejection / trust_action_gap / early_attrition / mid_attrition
    )
    focus: dict[str, float | str | None] = Field(default_factory=dict)  # 근거 수치(병목·KPI)
    objective: str | None = None  # detected_objective(캠페인 목표)
