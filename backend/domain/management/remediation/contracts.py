# 이상 조치 상담 고정 계약 — 옵션 어휘·형태를 잠근다 (스튜어드: 🅱, 합의 §2 공통 규칙 준수)
from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

#: consult meta 스키마 버전 — 구조 변경 시 올린다(모든 계약은 schema_version 포함).
CONSULT_SCHEMA_VERSION = 1

#: 채팅에 실제 등록된 도구명만 tool_hint로 허용(오타·미등록 도구 차단).
ALLOWED_TOOL_HINTS = frozenset({"run_generation", "run_simulation", "manage_campaign"})


class OptionKind(StrEnum):
    PLATFORM = "platform"  # 플랫폼 내부 기능(시뮬·생성) — 승인 불필요
    SPEND = "spend"  # Meta 지출 조작 — 기존 제안·승인 경로(HITL)
    OBSERVE = "observe"  # 관망


class RemediationAction(StrEnum):
    """상담 옵션 어휘 — spend는 TIER_POLICY 키와 일치, platform은 remediation 전용."""

    REGENERATE_CREATIVE = "REGENERATE_CREATIVE"  # platform: 새 시안 생성
    VERIFY_SIM = "VERIFY_SIM"  # platform: 시뮬로 검증
    PAUSE_CAMPAIGN = "PAUSE_CAMPAIGN"  # spend
    INCREASE_BUDGET = "INCREASE_BUDGET"  # spend
    DECREASE_BUDGET = "DECREASE_BUDGET"  # spend
    OBSERVE = "OBSERVE"


class RemediationOption(BaseModel):
    index: int = Field(ge=1)
    kind: OptionKind
    action: RemediationAction
    label: str
    rationale: str = ""
    tool_hint: str | None = None

    @model_validator(mode="after")
    def _check_tool_hint(self) -> RemediationOption:
        if self.tool_hint is not None and self.tool_hint not in ALLOWED_TOOL_HINTS:
            raise ValueError(f"미등록 도구: {self.tool_hint}")
        return self


class ConsultResult(BaseModel):
    """advisor 산출 — status=normal이면 options는 빈 목록(정상 확인 응답)."""

    status: Literal["anomaly", "normal"]
    campaign_id: str
    campaign_name: str = ""
    anomaly_type: str = ""
    confidence: float = 0.0
    diagnosed_at: str = ""  # ISO8601 UTC
    message: str = ""
    options: list[RemediationOption] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_indices(self) -> ConsultResult:
        got = [o.index for o in self.options]
        if got != list(range(1, len(self.options) + 1)):
            raise ValueError("옵션 index는 1부터 연속이어야 한다")
        return self

    @model_validator(mode="after")
    def _check_status_rules(self) -> ConsultResult:
        """status별 불변식 — normal은 옵션 금지, anomaly는 옵션·anomaly_type 필수."""
        if self.status == "normal":
            if self.options:
                raise ValueError("normal 상태는 options를 가질 수 없다")
        else:
            if not self.options:
                raise ValueError("anomaly 상태는 options가 최소 1개 필요하다")
            if not self.anomaly_type:
                raise ValueError("anomaly 상태는 anomaly_type이 필요하다")
        return self

    def to_meta(self, org_id: str | None = None) -> dict:
        """chat_messages.meta에 심을 고정 스키마 — 주입·스팸 방지 판정이 읽는다."""
        return {
            "kind": "remediation_consult",
            "schema_version": CONSULT_SCHEMA_VERSION,
            "campaign_id": self.campaign_id,
            "org_id": org_id,
            "diagnosed_at": self.diagnosed_at,
            "anomaly_type": self.anomaly_type,
            "confidence": self.confidence,
            "options": [
                {
                    "index": o.index,
                    "action": o.action.value,
                    "tool_hint": o.tool_hint,
                    "label": o.label,
                }
                for o in self.options
            ],
        }
