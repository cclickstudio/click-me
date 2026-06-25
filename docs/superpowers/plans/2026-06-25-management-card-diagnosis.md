# 매니지먼트 카드 진단 풍부화 구현 계획 (스펙 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매니지먼트 챗에 실제 detection 진단(`DiagnosisResult`)과 진단용 제안 미리보기(proposal_preview)를 `live_diagnosis` 툴 하나로 꽂아, 카드에 anomaly_type·confidence·hypothesis·severity·예산델타를 표시한다. "이상 없음"과 "진단 불가(unavailable/failed)"를 분리하고, 실행 정본·집행은 스펙 3으로 미룬다.

**Architecture:** typed `DiagnosticResult`(4-case validator)가 운반 계약. `live_diagnosis` 어댑터 툴이 `build_reader().fetch_hourly_metrics → run_detection`으로 진단하고, 정본 `ActionProposal`을 만들지 않고 `DiagnosisResult`에서 직접 preview dict를 조립한다. composer가 상태별로 카드를 결정적으로 조립(diagnosis 섹션·severity·empty_state). 프론트는 섹션 레지스트리에 diagnosis 렌더러를 한 개 등록한다.

**Tech Stack:** Python 3.12 · Pydantic v2 · pytest(`pytest-asyncio`) · uv · ruff / Next.js(TS) · pnpm.

설계 근거 — `docs/superpowers/specs/2026-06-25-management-card-diagnosis-design.md`.

**커밋 정책** — Task 끝 커밋은 권장 체크포인트(한 PR로 묶어도 무방). 커밋 메시지 끝에 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

**현재 코드 사실(확인됨)**
- `run_detection(tenant_id, campaign_id, snapshots, *, daily_budget_krw=DAILY_BUDGET_KRW, ...) -> DetectionOutcome(guard, diagnosis: DiagnosisResult|None, expected)` — `from domain.management.detection.service.detection_service import run_detection`.
- `DiagnosisResult`(schemas.py): `diagnosis_id, tenant_id, campaign_id, anomaly_type: AnomalyType, source, hypothesis, confidence: float, evidence_metrics: dict, metrics_as_of, status: DiagnosisStatus`.
- `DiagnosisStatus`(enums.py): `CONFIRMED="confirmed"`, `INCONCLUSIVE="inconclusive"`.
- reader(mock·실측 둘 다): `async def fetch_hourly_metrics(self, campaign_id: str, day: datetime, ...)`. `build_reader(settings)` from `domain.management.wiring`(mock↔실측=`use_mock`).
- mock fault 주입: `MockAdPlatform(seed).fetch_hourly_metrics(cid, day, fault=FaultConfig(mode=FaultMode.X, probability=1.0))` — `from domain.management.adapters.mock import MockAdPlatform`, `from domain.management.contracts.fault_injection import FaultConfig, FaultMode`.
- `DAILY_BUDGET_KRW` from `domain.management.contracts.policy`.
- `AskResult`(assistant/contracts.py): `answer, citations, used_tools, evidence: dict, suggested_action, requires_approval, thread_id`.
- composer `compose_card(res, *, turn_id) -> ChatCard`(스펙 1) · chat_cards 섹션 union(summary/metrics/entity/proposal/review/evidence/empty_state).

---

## Task 1: `DiagnosticResult` 계약 + `AskResult.diagnostic`

**Files:**
- Modify: `backend/domain/management/assistant/contracts.py`
- Test: `backend/tests/management/test_diagnostic_result.py` (생성)

- [ ] **Step 1: 실패 테스트 작성** — `backend/tests/management/test_diagnostic_result.py`:

```python
# DiagnosticResult 4-case validator + 중첩 typed 모델(ProposalPreview/DiagnosisView) — 불법 조합/값 거부
import pytest
from pydantic import ValidationError

from domain.management.assistant.contracts import (
    AskResult,
    DiagnosisView,
    DiagnosticResult,
    ProposalPreview,
)


def _view():
    return DiagnosisView(anomaly_type="bid_loss", status="confirmed", confidence=1.0, hypothesis="입찰 패배")


def _preview():
    return ProposalPreview(preview_id="preview_1", action_type="INCREASE_BUDGET", budget_before_krw=100, budget_after_krw=150)


def test_ok_anomaly_requires_diagnosis_and_proposal():
    d = DiagnosticResult(diagnostic_status="ok", anomaly=True, diagnosis=_view(), proposal_preview=_preview())
    assert d.anomaly is True


def test_ok_anomaly_without_proposal_rejected():
    with pytest.raises(ValidationError):
        DiagnosticResult(diagnostic_status="ok", anomaly=True, diagnosis=_view(), proposal_preview=None)


def test_ok_anomaly_without_diagnosis_rejected():
    with pytest.raises(ValidationError):
        DiagnosticResult(diagnostic_status="ok", anomaly=True, diagnosis=None, proposal_preview=_preview())


def test_ok_no_anomaly_forbids_payload():
    ok = DiagnosticResult(diagnostic_status="ok", anomaly=False)
    assert ok.diagnosis is None and ok.proposal_preview is None
    with pytest.raises(ValidationError):
        DiagnosticResult(diagnostic_status="ok", anomaly=False, proposal_preview=_preview())


def test_unavailable_forbids_payload_requires_reason():
    u = DiagnosticResult(diagnostic_status="unavailable", reason="데이터 없음")
    assert u.diagnosis is None and u.anomaly is False
    with pytest.raises(ValidationError):
        DiagnosticResult(diagnostic_status="unavailable", reason="")
    with pytest.raises(ValidationError):
        DiagnosticResult(diagnostic_status="unavailable", reason="x", diagnosis=_view())


def test_failed_requires_reason():
    f = DiagnosticResult(diagnostic_status="failed", reason="툴 오류")
    assert f.proposal_preview is None
    with pytest.raises(ValidationError):
        DiagnosticResult(diagnostic_status="failed", reason="")


def test_proposal_preview_locks_safety_invariants():
    # executable=True·proposal_id·임의 키는 타입/extra=forbid로 거부(정본/실행 가능 오인 차단)
    with pytest.raises(ValidationError):
        ProposalPreview(preview_id="p", action_type="X", executable=True)
    with pytest.raises(ValidationError):
        ProposalPreview(preview_id="p", action_type="X", proposal_id="prop_1")
    pv = _preview()
    assert pv.executable is False and pv.finalized is False and pv.persisted is False


def test_askresult_diagnostic_optional_default_none():
    assert AskResult(answer="x").diagnostic is None
```

- [ ] **Step 2: 실패 확인** — `cd backend && uv run pytest tests/management/test_diagnostic_result.py -v` → FAIL(`ImportError: DiagnosticResult`).

- [ ] **Step 3: 구현** — `backend/domain/management/assistant/contracts.py` 상단 import 보강: `from pydantic import BaseModel, ConfigDict, Field, model_validator`, `from typing import Literal`. `AskResult` 클래스 **위**에 추가:

```python
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
    def _legal_combo(self) -> "DiagnosticResult":
        if self.diagnostic_status != "ok":
            if self.diagnosis is not None or self.proposal_preview is not None:
                raise ValueError("unavailable/failed은 diagnosis·proposal_preview를 가질 수 없다")
            if not self.reason:
                raise ValueError("unavailable/failed은 reason이 필요하다")
            if self.anomaly:
                raise ValueError("unavailable/failed은 anomaly=False여야 한다")
        elif self.anomaly:
            # ok+anomaly ⇒ diagnosis AND proposal_preview 둘 다 필수(카드 계약 일치)
            if self.diagnosis is None or self.proposal_preview is None:
                raise ValueError("ok+anomaly는 diagnosis와 proposal_preview가 모두 필요하다")
        else:
            if self.diagnosis is not None or self.proposal_preview is not None:
                raise ValueError("ok+no-anomaly는 diagnosis·proposal_preview를 가질 수 없다")
        return self
```

그리고 `AskResult`에 필드 한 줄 추가(기존 필드 뒤, 예 `thread_id` 위):

```python
    diagnostic: DiagnosticResult | None = None  # 진단 4-case 결과(없으면 v0 경로)
```

- [ ] **Step 4: 통과 확인** — `cd backend && uv run pytest tests/management/test_diagnostic_result.py -v` → PASS(8 passed).

- [ ] **Step 5: Ruff + 커밋**
```bash
(cd backend && uv run ruff format domain/management/assistant/contracts.py tests/management/test_diagnostic_result.py && uv run ruff check domain/management/assistant/contracts.py tests/management/test_diagnostic_result.py --fix)
git add backend/domain/management/assistant/contracts.py backend/tests/management/test_diagnostic_result.py
git commit -m "add: DiagnosticResult 4-case 계약 + AskResult.diagnostic

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `live_diagnosis` 툴 + `build_proposal_preview_from_diagnosis`

**Files:**
- Modify: `backend/domain/management/assistant/tools.py`
- Test: `backend/tests/management/test_live_diagnosis.py` (생성)

- [ ] **Step 1: 실패 테스트 작성** — `backend/tests/management/test_live_diagnosis.py`:

```python
# live_diagnosis 4-case + preview(정본 미생성) — mock reader로 앱·DB 없이
import pytest

from domain.management.adapters.mock import MockAdPlatform
from domain.management.assistant import tools as t
from domain.management.contracts.fault_injection import FaultConfig, FaultMode


class _Settings:
    use_mock = True


def _patch_reader(monkeypatch, reader):
    monkeypatch.setattr(t, "build_reader", lambda settings: reader)


@pytest.mark.asyncio
async def test_anomaly_returns_ok_anomaly_with_preview(monkeypatch):
    reader = MockAdPlatform(seed=1)
    # bid_loss fault를 항상 주입하도록 fetch_hourly_metrics를 래핑
    orig = reader.fetch_hourly_metrics

    async def faulted(campaign_id, day, fault=None):
        return await orig(campaign_id, day, fault=FaultConfig(mode=FaultMode.BID_LOSS, probability=1.0))

    monkeypatch.setattr(reader, "fetch_hourly_metrics", faulted)
    _patch_reader(monkeypatch, reader)

    res = await t.live_diagnosis(_Settings(), "camp_1")
    assert res.diagnostic_status == "ok"
    assert res.anomaly is True
    assert res.diagnosis is not None
    assert res.proposal_preview is not None
    assert res.proposal_preview.executable is False  # ProposalPreview 타입(불변식 잠금)
    assert res.proposal_preview.preview_id.startswith("preview_")


@pytest.mark.asyncio
async def test_normal_returns_ok_no_anomaly(monkeypatch):
    reader = MockAdPlatform(seed=1)  # fault 없음 → 정상 게재
    _patch_reader(monkeypatch, reader)
    res = await t.live_diagnosis(_Settings(), "camp_1")
    assert res.diagnostic_status == "ok"
    assert res.anomaly is False
    assert res.diagnosis is None


@pytest.mark.asyncio
async def test_insufficient_data_maps_to_unavailable(monkeypatch):
    # guard가 INSUFFICIENT_DATA면 "이상 없음"이 아니라 "진단 불가"(불변식 3).
    from domain.management.detection.guardrails import GuardResult, GuardVerdict
    from domain.management.detection.service.detection_service import DetectionOutcome

    reader = MockAdPlatform(seed=1)
    _patch_reader(monkeypatch, reader)
    monkeypatch.setattr(
        t, "run_detection",
        lambda *a, **k: DetectionOutcome(GuardResult(GuardVerdict.INSUFFICIENT_DATA, reason="부족"), None, []),
    )
    res = await t.live_diagnosis(_Settings(), "camp_1")
    assert res.diagnostic_status == "unavailable"


@pytest.mark.asyncio
async def test_missing_campaign_returns_unavailable(monkeypatch):
    reader = MockAdPlatform(seed=1)
    _patch_reader(monkeypatch, reader)
    res = await t.live_diagnosis(_Settings(), "")
    assert res.diagnostic_status == "unavailable"
    assert res.reason


@pytest.mark.asyncio
async def test_real_mode_without_budget_is_unavailable(monkeypatch):
    class _Real:
        use_mock = False

    reader = MockAdPlatform(seed=1)
    _patch_reader(monkeypatch, reader)
    res = await t.live_diagnosis(_Real(), "camp_1")
    assert res.diagnostic_status == "unavailable"  # 실측 일예산 소싱 없음 → 합성 금지


@pytest.mark.asyncio
async def test_exception_returns_failed_without_raw(monkeypatch):
    class _Boom:
        async def fetch_hourly_metrics(self, campaign_id, day, fault=None):
            raise RuntimeError("SECRET reader down")

    _patch_reader(monkeypatch, _Boom())
    res = await t.live_diagnosis(_Settings(), "camp_1")
    assert res.diagnostic_status == "failed"
    assert "SECRET" not in res.reason


def test_preview_builder_makes_no_canonical_proposal():
    from domain.management.contracts.enums import AnomalyType, DiagnosisSource, DiagnosisStatus
    from domain.management.contracts.schemas import DiagnosisResult
    from datetime import UTC, datetime

    dx = DiagnosisResult(
        diagnosis_id="dx1", tenant_id="org_eval", campaign_id="c1",
        anomaly_type=AnomalyType.BUDGET_EXHAUSTED, source=DiagnosisSource.DETERMINISTIC,
        hypothesis="예산 소진", confidence=1.0, evidence_metrics={}, metrics_as_of=datetime.now(UTC),
        status=DiagnosisStatus.CONFIRMED,
    )
    preview = t.build_proposal_preview_from_diagnosis(dx, 100_000)  # ProposalPreview 반환
    assert preview.preview_id.startswith("preview_")
    assert preview.action_type == "INCREASE_BUDGET"
    assert preview.budget_before_krw == 100_000
    assert preview.executable is False and preview.persisted is False
    assert preview.source == "diagnostic_preview"
```

- [ ] **Step 2: 실패 확인** — `cd backend && uv run pytest tests/management/test_live_diagnosis.py -v` → FAIL(`AttributeError: live_diagnosis`).

- [ ] **Step 3: 구현** — `backend/domain/management/assistant/tools.py` 상단 import에 추가:

```python
from uuid import uuid4

from domain.management.assistant.contracts import DiagnosisView, DiagnosticResult, ProposalPreview
from domain.management.contracts.policy import DAILY_BUDGET_KRW
from domain.management.detection.service.detection_service import run_detection
```

파일 끝(INTENT_TOOLS 정의 **위**)에 추가:

```python
# anomaly_type → 표시용 추천 액션(정책 판정 아님). v1 단순 매핑, 미지정은 REPLACE_CREATIVE.
_ANOMALY_ACTION = {
    "budget_exhausted": ("INCREASE_BUDGET", "TIER_2"),
    "bid_loss": ("INCREASE_BUDGET", "TIER_2"),
    "audience_too_narrow": ("EXPAND_AUDIENCE", "TIER_2"),
    "quality_degraded": ("REPLACE_CREATIVE", "TIER_2"),
    "performance_below_target": ("REPLACE_CREATIVE", "TIER_2"),
    "review_rejected": ("REPLACE_CREATIVE", "TIER_3"),
}


def build_proposal_preview_from_diagnosis(dx, daily_budget_krw: int) -> ProposalPreview:
    """정본 ActionProposal을 만들지 않고(불변식 1) DiagnosisResult에서 직접 ProposalPreview 조립."""
    action_type, tier = _ANOMALY_ACTION.get(str(dx.anomaly_type), ("REPLACE_CREATIVE", "TIER_2"))
    budget_after = round(daily_budget_krw * 1.5) if action_type == "INCREASE_BUDGET" else daily_budget_krw
    return ProposalPreview(
        preview_id=f"preview_{uuid4().hex[:8]}",
        action_type=action_type,
        tier=tier,
        budget_before_krw=daily_budget_krw,
        budget_after_krw=budget_after,
        hypothesis=dx.hypothesis,
    )


async def live_diagnosis(settings, campaign_id: str, tenant_id: str | None = None) -> DiagnosticResult:
    """시간별 스냅샷으로 detection을 돌려 4-case 진단 결과를 낸다. detection 코어는 호출만(불변식 5).

    기준 시각은 UTC(`datetime.now(UTC)`). 데이터 부족·부분일은 guard가 INSUFFICIENT_DATA로 잡아
    `unavailable`로 분리한다(이상 없음과 혼동 금지, 불변식 3). 계정 타임존 정렬은 스펙 3+ 후속.
    """
    if not campaign_id:
        return DiagnosticResult(diagnostic_status="unavailable", reason="대상 캠페인을 특정할 수 없어요.")
    # 일예산 소싱(외부 I/O 아님) — 데모(mock)만 고정값 허용. 실측은 소스 없으면 진단 불가(합성 금지, 불변식 4).
    daily_budget = DAILY_BUDGET_KRW if getattr(settings, "use_mock", True) else None
    if not daily_budget:
        return DiagnosticResult(
            diagnostic_status="unavailable", reason="캠페인 일예산을 확인할 수 없어 진단을 건너뛰었어요."
        )

    # 외부 호출만 try로 — reader/detection I/O 실패만 failed. 계약 위반·빌더 버그는 아래에서 raise되게 둔다.
    try:
        reader = build_reader(settings)
        snapshots = await reader.fetch_hourly_metrics(campaign_id, datetime.now(UTC))
        outcome = run_detection(tenant_id or "org_eval", campaign_id, snapshots, daily_budget_krw=daily_budget)
    except Exception as exc:  # noqa: BLE001 — 외부(reader/detection) 실패만. raw 미노출.
        print(f"[live_diagnosis] external failure: {exc!r}")
        return DiagnosticResult(diagnostic_status="failed", reason="진단 중 문제가 발생해 건너뛰었어요.")

    # 이하 결정적 — validator·빌더 버그는 raise(테스트·모니터링에서 잡힘).
    if not snapshots or str(outcome.guard.verdict) == "insufficient_data":
        return DiagnosticResult(diagnostic_status="unavailable", reason="데이터가 부족해 진단을 보류했어요.")
    if outcome.diagnosis is None:  # NORMAL → 이상 없음
        return DiagnosticResult(diagnostic_status="ok", anomaly=False)
    dx = outcome.diagnosis  # DELIVERY_ANOMALY
    return DiagnosticResult(
        diagnostic_status="ok",
        anomaly=True,
        diagnosis=DiagnosisView(
            anomaly_type=str(dx.anomaly_type),
            status=str(dx.status),
            confidence=dx.confidence,
            hypothesis=dx.hypothesis,
        ),
        proposal_preview=build_proposal_preview_from_diagnosis(dx, daily_budget),
    )
```

그리고 `INTENT_TOOLS`에 한 줄 추가:
```python
    "diagnosis": ("live_diagnosis", live_diagnosis),
```

- [ ] **Step 4: 통과 확인** — `cd backend && uv run pytest tests/management/test_live_diagnosis.py -v` → PASS(7 passed).

- [ ] **Step 5: Ruff + 커밋**
```bash
(cd backend && uv run ruff format domain/management/assistant/tools.py tests/management/test_live_diagnosis.py && uv run ruff check domain/management/assistant/tools.py tests/management/test_live_diagnosis.py --fix)
git add backend/domain/management/assistant/tools.py backend/tests/management/test_live_diagnosis.py
git commit -m "add: live_diagnosis 툴 + 진단 preview(정본 미생성)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: chat_cards — `DiagnosisSection` + `ProposalSection` preview 필드

**Files:**
- Modify: `backend/domain/management/assistant/chat_cards/models.py`
- Modify: `backend/domain/management/assistant/chat_cards/__init__.py`
- Test: `backend/tests/management/test_chat_cards.py` (보강)

- [ ] **Step 1: 실패 테스트 추가** — `backend/tests/management/test_chat_cards.py` 끝에 추가:

```python
def test_diagnosis_section_round_trips():
    from domain.management.assistant.chat_cards import ChatCard, DiagnosisSection

    card = ChatCard(
        sections=[DiagnosisSection(anomaly_type="bid_loss", status="confirmed", confidence=1.0, hypothesis="입찰 패배")]
    )
    d = card.model_dump(mode="json")["sections"][0]
    assert d["kind"] == "diagnosis"
    assert d["anomaly_type"] == "bid_loss" and d["confidence"] == 1.0


def test_proposal_section_preview_fields():
    from domain.management.assistant.chat_cards import ProposalSection

    p = ProposalSection(action_type="INCREASE_BUDGET", preview_id="preview_x", budget_before_krw=100, budget_after_krw=150)
    dumped = p.model_dump(mode="json")
    assert dumped["preview_id"] == "preview_x"
    assert dumped["budget_before_krw"] == 100 and dumped["executable"] is False
```

- [ ] **Step 2: 실패 확인** — `cd backend && uv run pytest tests/management/test_chat_cards.py -k "diagnosis_section or preview_fields" -v` → FAIL.

- [ ] **Step 3: 구현** — `backend/domain/management/assistant/chat_cards/models.py`에서 `ProposalSection`에 필드 추가:

```python
class ProposalSection(BaseModel):
    kind: Literal["proposal"] = "proposal"
    title: str | None = None
    action_type: str
    rationale: str | None = None
    proposal_id: str | None = None
    # 스펙 2 — 미리보기(실행 미연결). 정본 ID(proposal_id) 아님.
    preview_id: str | None = None
    budget_before_krw: int | None = None
    budget_after_krw: int | None = None
    tier: str | None = None
    executable: bool = False
```

그리고 `EmptyStateSection` 정의 **뒤**에 `DiagnosisSection` 추가:

```python
class DiagnosisSection(BaseModel):
    kind: Literal["diagnosis"] = "diagnosis"
    title: str | None = None
    anomaly_type: str
    status: str
    confidence: float
    hypothesis: str = ""
```

`CardSection` union에 `DiagnosisSection` 추가(union 멤버 목록에 한 줄):
```python
        DiagnosisSection,
```

`backend/domain/management/assistant/chat_cards/__init__.py`의 import·`__all__`에 `DiagnosisSection` 추가.

- [ ] **Step 4: 통과 확인** — `cd backend && uv run pytest tests/management/test_chat_cards.py -v` → PASS(전체).

- [ ] **Step 5: Ruff + 커밋**
```bash
(cd backend && uv run ruff format domain/management/assistant/chat_cards tests/management/test_chat_cards.py && uv run ruff check domain/management/assistant/chat_cards tests/management/test_chat_cards.py --fix)
git add backend/domain/management/assistant/chat_cards backend/tests/management/test_chat_cards.py
git commit -m "add: DiagnosisSection + ProposalSection preview 필드

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: composer — `derive_severity` + diagnostic 상태별 분기

**Files:**
- Modify: `backend/domain/management/assistant/composer.py`
- Test: `backend/tests/management/test_composer_diagnosis.py` (생성)

- [ ] **Step 1: 실패 테스트 작성** — `backend/tests/management/test_composer_diagnosis.py`:

```python
# compose_card diagnostic 상태별 분기 + severity 파생
from domain.management.assistant.composer import compose_card, derive_severity
from domain.management.assistant.contracts import AskResult, DiagnosticResult


def _kinds(card):
    return [s.kind for s in card.sections]


def _ok_anomaly():
    return DiagnosticResult(
        diagnostic_status="ok", anomaly=True,
        diagnosis={"anomaly_type": "bid_loss", "status": "confirmed", "confidence": 1.0, "hypothesis": "입찰 패배"},
        proposal_preview={"preview_id": "preview_1", "action_type": "INCREASE_BUDGET", "tier": "TIER_2",
                          "budget_before_krw": 100000, "budget_after_krw": 150000, "hypothesis": "입찰 패배",
                          "executable": False},
    )


def test_severity_critical_for_confirmed_high_confidence():
    assert derive_severity(_ok_anomaly()) == "critical"


def test_severity_warning_for_confirmed_low_confidence():
    d = DiagnosticResult(diagnostic_status="ok", anomaly=True,
                         diagnosis={"anomaly_type": "schedule_gap", "status": "confirmed", "confidence": 0.4, "hypothesis": "h"})
    assert derive_severity(d) == "warning"


def test_severity_neutral_for_inconclusive_and_unavailable():
    inc = DiagnosticResult(diagnostic_status="ok", anomaly=True,
                           diagnosis={"anomaly_type": "x", "status": "inconclusive", "confidence": 0.4, "hypothesis": "h"})
    assert derive_severity(inc) == "neutral"
    assert derive_severity(DiagnosticResult(diagnostic_status="unavailable", reason="r")) == "neutral"


def test_ok_anomaly_builds_diagnosis_and_proposal_sections():
    card = compose_card(AskResult(answer="이상 감지", diagnostic=_ok_anomaly()), turn_id="t")
    assert "diagnosis" in _kinds(card)
    assert "proposal" in _kinds(card)
    assert card.status == "critical"
    proposal = next(s for s in card.sections if s.kind == "proposal")
    assert proposal.preview_id == "preview_1" and proposal.executable is False


def test_ok_no_anomaly_summary_metrics_only():
    card = compose_card(
        AskResult(answer="정상입니다.", evidence={"this_month_spent_krw": 100},
                  diagnostic=DiagnosticResult(diagnostic_status="ok", anomaly=False)),
        turn_id="t",
    )
    assert "diagnosis" not in _kinds(card)
    assert card.status == "neutral"


def test_unavailable_renders_empty_state_neutral():
    card = compose_card(
        AskResult(answer="진단 시도", diagnostic=DiagnosticResult(diagnostic_status="unavailable", reason="데이터 없음")),
        turn_id="t",
    )
    assert "empty_state" in _kinds(card)
    assert card.status == "neutral"


def test_failed_renders_empty_state_neutral():
    card = compose_card(
        AskResult(answer="진단 시도", diagnostic=DiagnosticResult(diagnostic_status="failed", reason="툴 오류")),
        turn_id="t",
    )
    assert "empty_state" in _kinds(card)


def test_no_diagnostic_keeps_v0_path():
    card = compose_card(AskResult(answer="일반 답변", evidence={"this_month_spent_krw": 100}), turn_id="t")
    assert _kinds(card) == ["summary", "metrics"]
    assert card.status is None
```

- [ ] **Step 2: 실패 확인** — `cd backend && uv run pytest tests/management/test_composer_diagnosis.py -v` → FAIL(`ImportError: derive_severity`).

- [ ] **Step 3: 구현** — `backend/domain/management/assistant/composer.py`의 import에 섹션 추가:

```python
from .chat_cards import (
    Badge,
    ChatCard,
    Citation,
    DiagnosisSection,
    EmptyStateSection,
    EvidenceSection,
    MetricItem,
    MetricsSection,
    ProposalSection,
    SummarySection,
    TraceInfo,
)
```

`compose_card` **위**에 추가:

```python
def derive_severity(diagnostic) -> str:
    """진단만으로 severity 파생(tier 미사용). 계약상 info 없음 → neutral."""
    if diagnostic is None or diagnostic.diagnostic_status != "ok" or not diagnostic.anomaly:
        return "neutral"
    dx = diagnostic.diagnosis  # DiagnosisView
    if dx is not None and dx.status == "confirmed":
        return "critical" if dx.confidence >= 0.8 else "warning"
    return "neutral"


def _diagnosis_section(dx) -> DiagnosisSection:  # dx: DiagnosisView
    return DiagnosisSection(
        title="진단",
        anomaly_type=dx.anomaly_type,
        status=dx.status,
        confidence=dx.confidence,
        hypothesis=dx.hypothesis,
    )


def _proposal_preview_section(pv) -> ProposalSection:  # pv: ProposalPreview
    return ProposalSection(
        title="제안(미리보기)",
        action_type=pv.action_type,
        rationale=pv.hypothesis or None,
        preview_id=pv.preview_id,
        tier=pv.tier,
        budget_before_krw=pv.budget_before_krw,
        budget_after_krw=pv.budget_after_krw,
        executable=False,
    )
```

`compose_card` 함수에서, `SummarySection`(결론)과 `metrics`를 만든 **직후**, 기존 `suggested_action` 분기 **앞**에 diagnostic 분기를 넣는다. 즉 `compose_card` 본문을 다음 구조로 교체:

```python
def compose_card(res: AskResult, *, turn_id: str) -> ChatCard:
    sections: list = [SummarySection(title="결론", text=_descriptive_conclusion(res.answer))]
    metrics = _metrics_section(res.evidence or {})
    if metrics is not None:
        sections.append(metrics)

    diag = res.diagnostic
    status = derive_severity(diag)
    badges = []

    if diag is not None and diag.diagnostic_status in ("unavailable", "failed"):
        # 진단 불가/실패 — composer 결정적(empty_state + neutral). LLM 미경유.
        sections.append(EmptyStateSection(title="진단", text=diag.reason or "진단 데이터를 가져올 수 없어요."))
        return ChatCard(type="management", status="neutral", badges=[], sections=sections, trace=TraceInfo(turn_id=turn_id))

    if diag is not None and diag.diagnostic_status == "ok" and diag.anomaly and diag.diagnosis:
        sections.append(_diagnosis_section(diag.diagnosis))
        if diag.proposal_preview:
            sections.append(_proposal_preview_section(diag.proposal_preview))
        badges = [Badge(label=diag.diagnosis.anomaly_type, tone="warning")]
        return ChatCard(type="management", status=status, badges=badges, sections=sections, trace=TraceInfo(turn_id=turn_id))

    # diag None(일반 질문) 또는 ok+no-anomaly → 기존 v0 경로(suggested_action/evidence)
    sa = res.suggested_action
    if sa is not None:
        sections.append(_proposal_section(sa))
        sections.append(_review_section(sa))
    evidence = _evidence_section(res)
    if evidence is not None:
        sections.append(evidence)
    return ChatCard(
        type="management",
        status=(status if diag is not None else None),  # v0(diag None)은 status 미설정
        badges=_badges(sa),
        sections=sections,
        trace=TraceInfo(turn_id=turn_id),
    )
```

> 기존 헬퍼 `_metrics_section`·`_proposal_section`·`_review_section`·`_evidence_section`·`_badges`·`_descriptive_conclusion`·`stream_card`·`format_sse`는 그대로 둔다.

- [ ] **Step 4: 통과 확인 + 회귀** — `cd backend && uv run pytest tests/management/test_composer_diagnosis.py tests/management/test_composer.py -v` → PASS(스펙 1 composer 테스트 무회귀 포함).

- [ ] **Step 5: Ruff + 커밋**
```bash
(cd backend && uv run ruff format domain/management/assistant/composer.py tests/management/test_composer_diagnosis.py && uv run ruff check domain/management/assistant/composer.py tests/management/test_composer_diagnosis.py --fix)
git add backend/domain/management/assistant/composer.py backend/tests/management/test_composer_diagnosis.py
git commit -m "add: composer 진단 분기 + derive_severity + empty_state

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 어시스턴트 배선 — 무키 폴백 + 그래프 툴

**Files:**
- Modify: `backend/domain/management/assistant/agent.py` (무키 폴백에 diagnosis intent)
- Modify: `backend/domain/management/assistant/graph.py` (풀모드 LLM 툴 + to_result에 diagnostic 전달)
- Test: `backend/tests/management/test_assistant_diagnosis_wiring.py` (생성)

> 무키 폴백은 결정적이라 단위 테스트로, 풀모드 그래프는 LLM 의존이라 배선만(스모크).

- [ ] **Step 1: 실패 테스트 작성** — `backend/tests/management/test_assistant_diagnosis_wiring.py`:

```python
# 무키 폴백에서 진단 질문 → AskResult.diagnostic 채워짐(앱·DB·LLM 없이)
import pytest

from domain.management.assistant import tools as t
from domain.management.assistant.agent import build_management_agent
from domain.management.assistant.contracts import AskRequest, DiagnosticResult


class _Settings:
    use_mock = True
    gemini_api_key = None
    openai_api_key = None
    anthropic_api_key = None


@pytest.mark.asyncio
async def test_keyless_fallback_diagnosis_sets_diagnostic(monkeypatch):
    async def fake_diag(settings, campaign_id, tenant_id=None):
        return DiagnosticResult(diagnostic_status="unavailable", reason="테스트")

    monkeypatch.setattr(t, "live_diagnosis", fake_diag)
    ask = build_management_agent(_Settings())
    res = await ask(AskRequest(question="이 캠페인 진단해줘", campaign_id="camp_1"))
    assert res.diagnostic is not None
    assert res.diagnostic.diagnostic_status == "unavailable"
```

- [ ] **Step 2: 실패 확인** — `cd backend && uv run pytest tests/management/test_assistant_diagnosis_wiring.py -v` → FAIL(폴백이 diagnostic 미설정).

- [ ] **Step 3: 무키 폴백 수정** — `backend/domain/management/assistant/agent.py`의 `_keyword_intent`에 진단 키워드를 추가하고(`"진단"`·`"왜"`·`"이상"`·`"노출"` 등이 있으면 `"diagnosis"` 반환), `_ask_fallback` 안에서 intent가 `"diagnosis"`면 `live_diagnosis`를 호출해 `AskResult.diagnostic`에 싣는다.

`_keyword_intent` 함수에 분기 추가(함수 맨 위, 기존 로직 앞):
```python
    if any(k in q for k in ("진단", "이상", "왜", "노출이 안", "게재가 안")):
        return "diagnosis"
```

`_ask_fallback` 내부, 기존 `name, fn = INTENT_TOOLS[intent]` 분기를 diagnosis와 분리:
```python
            intent = _keyword_intent(req.question, req.campaign_id)
            if intent == "diagnosis":
                from domain.management.assistant.tools import live_diagnosis  # noqa: PLC0415

                diagnostic = await live_diagnosis(settings, req.campaign_id or "")
                return AskResult(
                    answer=_summarize_diagnostic(diagnostic),
                    used_tools=["live_diagnosis"],
                    diagnostic=diagnostic,
                )
            name, fn = INTENT_TOOLS[intent]
```

그리고 `agent.py`에 `_summarize_diagnostic` 헬퍼 추가(파일 내 `_summarize` 근처):
```python
def _summarize_diagnostic(d) -> str:
    if d.diagnostic_status != "ok":
        return d.reason or "진단을 완료하지 못했어요."
    if not d.anomaly:
        return "현재 이상 징후는 발견되지 않았어요."
    dx = d.diagnosis or {}
    return f"{dx.get('hypothesis') or '이상이 감지됐어요.'} (신뢰도 {dx.get('confidence', 0):.0%})"
```

- [ ] **Step 4: 풀모드 그래프 툴 배선** — `backend/domain/management/assistant/graph.py`에서 기존 `live_budget` 등 툴 래퍼 옆에 `live_diagnosis` 래퍼를 추가하고 `read_tools` 목록에 포함:
```python
    async def live_diagnosis(campaign_id: str) -> dict:
        """캠페인 시간별 데이터로 이상 진단(anomaly_type·confidence·hypothesis). 수치는 실측."""
        result = await live_tools.live_diagnosis(settings, campaign_id)
        return result.model_dump(mode="json")
```
`read_tools = [live_campaigns, live_budget, live_campaign_detail, live_before_after, search_kb]` 에 `live_diagnosis` 추가.

그리고 `_State`에 `diagnostic: dict`(state) 필드를 두고, `tools_node`에서 `live_diagnosis` 결과를 state에 보존, `to_result`가 `AskResult(diagnostic=DiagnosticResult(**state["diagnostic"]))`로 전달하도록 한다. (graph state 누적 패턴은 기존 `live_evidence`와 동일하게 따른다. `to_result`에서 `diagnostic` state가 있으면 `DiagnosticResult.model_validate(state["diagnostic"])`.)

> 풀모드는 LLM 의존이라 단위 테스트 대신 import·스모크로 검증(Step 5). 무키 폴백 경로가 결정적 회귀 테스트를 책임진다.

- [ ] **Step 5: 통과 + 스모크 + 회귀**
```bash
cd backend && uv run pytest tests/management/test_assistant_diagnosis_wiring.py -v
uv run python -c "import domain.management.assistant.graph; import domain.management.assistant.agent; print('wiring import OK')"
uv run pytest tests/management/ tests/orchestration/ -q
```
Expected: 폴백 테스트 PASS, import OK, 전체 PASS(무회귀).

- [ ] **Step 6: Ruff + 커밋**
```bash
(cd backend && uv run ruff format domain/management/assistant/agent.py domain/management/assistant/graph.py tests/management/test_assistant_diagnosis_wiring.py && uv run ruff check domain/management/assistant/agent.py domain/management/assistant/graph.py tests/management/test_assistant_diagnosis_wiring.py --fix)
git add backend/domain/management/assistant/agent.py backend/domain/management/assistant/graph.py backend/tests/management/test_assistant_diagnosis_wiring.py
git commit -m "add: 진단 툴 어시스턴트 배선(무키 폴백 + 그래프)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: 프론트 — diagnosis 섹션 렌더러 + proposal preview + severity

**Files:**
- Modify: `frontend/src/lib/chatCard.ts`
- Modify: `frontend/src/components/chat/sections.tsx`
- Modify: `frontend/src/components/chat/ChatCardView.tsx`

- [ ] **Step 1: 타입 추가** — `frontend/src/lib/chatCard.ts`의 `CardSection` union에 diagnosis 변종 추가, `proposal`에 preview 필드 추가:
```ts
  | { kind: 'proposal'; title?: string; action_type: string; rationale?: string; proposal_id?: string;
      preview_id?: string; tier?: string; budget_before_krw?: number; budget_after_krw?: number; executable?: boolean }
  | { kind: 'diagnosis'; title?: string; anomaly_type: string; status: string; confidence: number; hypothesis?: string }
```
(기존 `proposal` 줄을 위 확장 버전으로 교체, `evidence`/`empty_state` 위에 `diagnosis` 추가.)

- [ ] **Step 2: 렌더러 추가** — `frontend/src/components/chat/sections.tsx`의 `SECTION_RENDERERS`에 `diagnosis` 추가, `proposal` 렌더러에 preview 정보:
```tsx
  diagnosis: (s) => (
    <div>
      <Title title={s.title} />
      <p className="text-sm text-[#191F28] dark:text-[#F2F4F6]">
        {s.anomaly_type} · 신뢰도 {Math.round(s.confidence * 100)}%
      </p>
      {s.hypothesis && <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-0.5">{s.hypothesis}</p>}
    </div>
  ),
```
`proposal` 렌더러 본문에 예산델타·draft 뱃지 추가:
```tsx
  proposal: (s) => (
    <div>
      <Title title={s.title} />
      <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">
        {s.action_type}
        {s.executable === false && (
          <span className="ml-2 text-[10px] font-normal text-[#8B95A1]">draft · 실행 미연결</span>
        )}
      </p>
      {typeof s.budget_before_krw === 'number' && typeof s.budget_after_krw === 'number' && (
        <p className="text-xs text-[#4E5968] dark:text-[#9CA3AF] mt-0.5">
          예산 {s.budget_before_krw.toLocaleString()}원 → {s.budget_after_krw.toLocaleString()}원
        </p>
      )}
      {s.rationale && <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-0.5">근거: {s.rationale}</p>}
    </div>
  ),
```

- [ ] **Step 3: severity 헤더 강조(선택)** — `ChatCardView.tsx`는 이미 `card.status`/badges를 헤더에 받는다. status가 `critical`/`warning`이면 헤더에 작은 점/색을 더하려면 badges에 이미 anomaly_type이 실리므로 추가 변경 불필요. (변경 없음 — 확인만.)

- [ ] **Step 4: 빌드·린트** — `cd frontend && pnpm lint && pnpm build` → 통과.

- [ ] **Step 5: 커밋**
```bash
git add frontend/src/lib/chatCard.ts frontend/src/components/chat/sections.tsx
git commit -m "add: 프론트 diagnosis 섹션 렌더러 + proposal preview

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: 엔드투엔드 확인

**Files:** 없음(검증만).

- [ ] **Step 1: 백엔드 전체 회귀 + Ruff** — `cd backend && uv run pytest tests/management/ tests/orchestration/ -q` (전부 PASS), `uv run ruff check .` (All checks passed).
- [ ] **Step 2: 프론트 빌드** — `cd frontend && pnpm build` (성공).
- [ ] **Step 3: 서버·프론트 기동 후(USE_MOCK=true) 확인** — 매니지먼트 진단 질문("이 캠페인 진단해줘", campaign 컨텍스트) → 카드에 진단 섹션(anomaly_type·신뢰도)·제안 미리보기(draft·예산델타)·severity 표시. mock 정상 캠페인 → "이상 없음". 일반 질문 → v0 카드/CLIO 무변경.

---

## Self-Review (요약)

- **Spec 커버리지** — §2 불변식(preview 정본 미생성 T2·executable=false T3/T6) · §3 4-case(T1 validator·T2 툴·T4 분기) · §4.1 툴/preview(T2) · §4.2 계약(T1) · §4.3 composer(T4) · §5 프론트(T6) · §6 severity(T4 derive_severity 진단만) · unavailable/failed 결정적(T4). §10 실측 일예산 한계는 T2에서 `unavailable`로 정직 반영.
- **타입 일관성** — `DiagnosticResult(diagnostic_status, anomaly, diagnosis, proposal_preview, reason)` · `live_diagnosis(settings, campaign_id, tenant_id=None) -> DiagnosticResult` · `build_proposal_preview_from_diagnosis(dx, daily_budget_krw) -> dict` · `derive_severity(diagnostic) -> str` · `DiagnosisSection(anomaly_type, status, confidence, hypothesis)` · `ProposalSection(... preview_id, budget_before_krw, budget_after_krw, executable)` 전 Task 동일. 프론트 타입(T6) ↔ 백엔드 필드명 일치.
- **플레이스홀더 없음.** 모든 코드 스텝 실제 코드 포함. 정본 ActionProposal 미생성(불변식 1)·합성 금지(불변식 4)는 T2 코드·테스트로 강제.
```
