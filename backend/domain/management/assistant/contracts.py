# 매니지먼트 어시스턴트 I/O 계약 — 질문/근거+인용 답변
"""오케스트레이터·엔드포인트가 주고받는 입출력. 도메인 공유 계약(A↔B)이 아니라 어시스턴트 로컬."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AskRequest(BaseModel):
    question: str
    campaign_id: str | None = None  # 특정 캠페인 맥락(있으면 상세 우선)
    ad_id: str | None = None  # 시뮬 예측 연결 맥락
    thread_id: str | None = None  # 멀티턴 키 — 같은 세션이면 같은 값(없으면 새로 생성)


class Citation(BaseModel):
    kind: str  # "kb"(문서) | "live"(실측 툴)
    source: str  # 문서 파일명 또는 툴 이름
    title: str = ""


class SuggestedAction(BaseModel):
    """행동 의도가 감지됐을 때의 추천 액션 — 어시스턴트는 제안만, 실행은 승인 경로로.

    어시스턴트가 직접 writer/executor를 호출하지 않는다. 이 제안을 받은 화면/오케스트레이터가
    기존 approval→executor 경로(Tier 게이트)로 사람 승인 후 실행한다.
    """

    action_type: str  # PAUSE_CAMPAIGN / ACTIVATE_CAMPAIGN / INCREASE_BUDGET ...
    target_campaign_id: str | None = None
    tier: str  # TIER_1 / TIER_3 ...
    requires_approval: bool  # Tier가 자동승인 한도(Tier1) 초과면 True(사람 승인 필요)
    rationale: str


class DiagnosisView(BaseModel):
    """카드용 진단 뷰 — DiagnosisResult에서 표시 필드만 추림(정보 최소화)."""

    anomaly_type: str
    status: str
    confidence: float
    hypothesis: str = ""


class ProposalPreview(BaseModel):
    """진단용 제안 미리보기 — 정본 아님/실행 불가를 타입으로 잠근다(불변식 1·2).

    executable/finalized/persisted는 Literal[False]로 고정, extra=forbid로 proposal_id 등
    정본 키 주입을 거부한다.
    """

    model_config = ConfigDict(extra="forbid")

    preview_id: str
    action_type: str
    campaign_id: str | None = None  # 진단 대상 캠페인(스펙3 finalize 결선용, additive)
    tier: str | None = None
    budget_before_krw: int | None = None
    budget_after_krw: int | None = None
    hypothesis: str = ""
    executable: Literal[False] = False
    finalized: Literal[False] = False
    persisted: Literal[False] = False
    source: Literal["diagnostic_preview"] = "diagnostic_preview"


class DiagnosticResult(BaseModel):
    """live_diagnosis 4-case 결과 — 불법 조합을 validator로 거부(이상없음/진단불가/실패 구분)."""

    diagnostic_status: Literal["ok", "unavailable", "failed"]
    anomaly: bool = False  # diagnostic_status == "ok"일 때만 의미
    diagnosis: DiagnosisView | None = None
    proposal_preview: ProposalPreview | None = None
    reason: str = ""  # unavailable/failed 안전 문구

    @model_validator(mode="after")
    def _legal_combo(self) -> DiagnosticResult:
        if self.diagnostic_status != "ok":
            if self.diagnosis is not None or self.proposal_preview is not None:
                raise ValueError("unavailable/failed은 diagnosis·proposal_preview를 가질 수 없다")
            if not self.reason:
                raise ValueError("unavailable/failed은 reason이 필요하다")
            if self.anomaly:
                raise ValueError("unavailable/failed은 anomaly=False여야 한다")
        elif self.anomaly:
            if self.diagnosis is None or self.proposal_preview is None:
                raise ValueError("ok+anomaly는 diagnosis와 proposal_preview가 모두 필요하다")
        else:
            if self.diagnosis is not None or self.proposal_preview is not None:
                raise ValueError("ok+no-anomaly는 diagnosis·proposal_preview를 가질 수 없다")
        return self


class AskResult(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    used_tools: list[str] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)  # 답에 쓰인 실측 수치(디버그·검증용)
    suggested_action: SuggestedAction | None = None  # 행동 의도 시 추천(실행은 승인 경로)
    requires_approval: bool = False  # write 제안이 사람 승인 게이트에서 멈췄는가(HITL)
    diagnostic: DiagnosticResult | None = None  # 진단 4-case 결과(없으면 v0 경로)
    thread_id: str | None = None  # interrupt로 멈춘 그래프의 재개 키(승인 경로에서 사용)


class FinalizeResult(BaseModel):
    """finalize 응답 — 정본 본문(ActionProposal) 미포함(서버 DB에만)."""

    status: Literal["finalized", "unavailable", "no_anomaly"]
    proposal_id: str | None = None
    action_type: str | None = None
    tier: str | None = None
    requires_external_approval: bool = False
    budget_before_krw: int | None = None
    budget_after_krw: int | None = None
    summary: str | None = None
    expires_at: str | None = None  # ISO8601
    drift: bool = False
    reason: str = ""  # unavailable/no_anomaly 안전 문구
