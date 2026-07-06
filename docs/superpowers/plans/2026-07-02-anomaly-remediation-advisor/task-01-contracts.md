# Task 1: 고정 계약 — `remediation/contracts.py`

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-02-anomaly-remediation-advisor.md` · 스펙: `docs/superpowers/specs/2026-07-02-anomaly-remediation-advisor-design.md`
> **실행 규칙**: 모든 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 .py 첫 줄 한국어 헤더 주석 · 🅰 소유 파일(detection/, approval.py, agents/diagnosis*) 수정 금지(읽기만).
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.

---

**Files:**
- Create: `backend/domain/management/remediation/__init__.py`
- Create: `backend/domain/management/remediation/contracts.py`
- Test: `test/backend/management/test_remediation_contracts.py`

- [ ] **Step 1: 패키지 초기화 파일 생성**

`backend/domain/management/remediation/__init__.py`:
```python
# 이상 조치 상담(remediation advisor) — 감지 후 사용자에게 먼저 묻고 조치를 제안하는 모듈 (🅱)
```

- [ ] **Step 2: 실패하는 테스트 작성**

`test/backend/management/test_remediation_contracts.py`:
```python
# remediation 고정 계약 테스트 — 옵션 스키마(어휘·index 연속·tool_hint·schema_version) 검증
from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.management.remediation.contracts import (
    CONSULT_SCHEMA_VERSION,
    ConsultResult,
    OptionKind,
    RemediationAction,
    RemediationOption,
)


def _opt(index: int, action: RemediationAction = RemediationAction.OBSERVE, **kw):
    defaults = {"kind": OptionKind.OBSERVE, "label": "관망", "tool_hint": None}
    defaults.update(kw)
    return RemediationOption(index=index, action=action, **defaults)


def test_option_rejects_unregistered_tool_hint():
    with pytest.raises(ValidationError):
        RemediationOption(
            index=1,
            kind=OptionKind.PLATFORM,
            action=RemediationAction.VERIFY_SIM,
            label="시뮬 검증",
            tool_hint="launch_rocket",  # 미등록 도구
        )


def test_option_accepts_registered_tool_hints():
    o = RemediationOption(
        index=1,
        kind=OptionKind.PLATFORM,
        action=RemediationAction.REGENERATE_CREATIVE,
        label="새 시안",
        tool_hint="run_generation",
    )
    assert o.tool_hint == "run_generation"


def test_consult_result_requires_contiguous_indices_from_1():
    # status 규칙은 전부 충족시켜 index 규칙만 위반 — 잘못된 이유로 통과하지 않게 격리
    with pytest.raises(ValidationError, match="index"):
        ConsultResult(
            status="anomaly",
            campaign_id="c1",
            anomaly_type="no_delivery",
            options=[_opt(1), _opt(3)],  # 2 건너뜀
        )
    with pytest.raises(ValidationError):
        ConsultResult(
            status="anomaly",
            campaign_id="c1",
            anomaly_type="no_delivery",
            options=[_opt(2)],  # 1부터 아님
        )


def test_consult_result_normal_allows_empty_options():
    r = ConsultResult(status="normal", campaign_id="c1", message="정상 범위")
    assert r.options == []


def test_status_rules_are_enforced():
    # normal은 options 금지
    with pytest.raises(ValidationError):
        ConsultResult(status="normal", campaign_id="c1", options=[_opt(1)])
    # anomaly는 options 최소 1개 + anomaly_type 필수
    with pytest.raises(ValidationError):
        ConsultResult(status="anomaly", campaign_id="c1", anomaly_type="no_delivery", options=[])
    with pytest.raises(ValidationError):
        ConsultResult(status="anomaly", campaign_id="c1", options=[_opt(1)])  # anomaly_type 누락


def test_to_meta_shape_is_fixed():
    r = ConsultResult(
        status="anomaly",
        campaign_id="c1",
        campaign_name="여름 캠페인",
        anomaly_type="no_delivery",
        confidence=0.9,
        diagnosed_at="2026-07-02T00:00:00+00:00",
        message="노출 0",
        options=[
            _opt(
                1,
                RemediationAction.VERIFY_SIM,
                kind=OptionKind.PLATFORM,
                label="시뮬 검증",
                tool_hint="run_simulation",
            ),
            _opt(2),
        ],
    )
    meta = r.to_meta(org_id="org-1")
    assert meta["kind"] == "remediation_consult"
    assert meta["schema_version"] == CONSULT_SCHEMA_VERSION
    assert meta["campaign_id"] == "c1"
    assert meta["org_id"] == "org-1"
    assert meta["anomaly_type"] == "no_delivery"
    assert meta["options"][0] == {
        "index": 1,
        "action": "VERIFY_SIM",
        "tool_hint": "run_simulation",
        "label": "시뮬 검증",
    }
```

- [ ] **Step 3: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_remediation_contracts.py -v`
Expected: FAIL — `ModuleNotFoundError: domain.management.remediation.contracts`

- [ ] **Step 4: 구현**

`backend/domain/management/remediation/contracts.py`:
```python
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
```

빈 options로 `_check_indices`가 통과해야 함 — `[] == list(range(1, 1))` → True, OK.

- [ ] **Step 5: 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_remediation_contracts.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: 커밋**

```bash
git add backend/domain/management/remediation/ test/backend/management/test_remediation_contracts.py
git commit -m "add: remediation 상담 고정 계약(옵션 어휘·index·tool_hint·schema_version)"
```
