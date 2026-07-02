# 이상 감지 선제 제안(remediation advisor) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이상 감지 시 에이전트가 채팅 벨(N5)로 먼저 사용자에게 묻고("어떻게 하실래요?") 조치 옵션을 제안하는 경로 신설. 스펙: `docs/superpowers/specs/2026-07-02-anomaly-remediation-advisor-design.md`.

**Architecture:** `domain/management/remediation/`(🅱 소유)에 advisor(진단 재검증+옵션)·chat_sink(세션 심기+스팸 방지)·resolver(캠페인→프로젝트)를 신설. 기존 코드 터치는 3곳뿐 — `notifications.py` sink 분기 1줄, `chat.py` 컨텍스트 주입 몇 줄, `subagent_tools.py` 도구 1개 append. detection·scheduler·프론트 무변경.

**Tech Stack:** FastAPI + SQLAlchemy(async) + pydantic v2 + pytest(asyncio). 커밋 컨벤션 `타입: 한국어 설명`. 모든 새 .py 첫 줄에 한국어 헤더 주석.

**실행 규칙:**
- 모든 명령은 `cd backend` 후 실행. 테스트: `uv run pytest <path> -v`.
- 각 태스크 커밋 전 `uv run ruff format . && uv run ruff check . --fix`.
- 타임스탬프는 UTC-aware(`datetime.now(UTC)`), naive 금지.
- 🅰 소유 파일(detection/, approval.py, agents/diagnosis*) 수정 금지 — 읽기(import)만.

---

### Task 1: 고정 계약 — `remediation/contracts.py`

**Files:**
- Create: `backend/domain/management/remediation/__init__.py`
- Create: `backend/domain/management/remediation/contracts.py`
- Test: `backend/tests/management/test_remediation_contracts.py`

- [ ] **Step 1: 패키지 초기화 파일 생성**

`backend/domain/management/remediation/__init__.py`:
```python
# 이상 조치 상담(remediation advisor) — 감지 후 사용자에게 먼저 묻고 조치를 제안하는 모듈 (🅱)
```

- [ ] **Step 2: 실패하는 테스트 작성**

`backend/tests/management/test_remediation_contracts.py`:
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
    with pytest.raises(ValidationError):
        ConsultResult(
            status="anomaly",
            campaign_id="c1",
            options=[_opt(1), _opt(3)],  # 2 건너뜀
        )
    with pytest.raises(ValidationError):
        ConsultResult(status="anomaly", campaign_id="c1", options=[_opt(2)])  # 1부터 아님


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

Run: `cd backend && uv run pytest tests/management/test_remediation_contracts.py -v`
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

Run: `cd backend && uv run pytest tests/management/test_remediation_contracts.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: 커밋**

```bash
git add backend/domain/management/remediation/ backend/tests/management/test_remediation_contracts.py
git commit -m "add: remediation 상담 고정 계약(옵션 어휘·index·tool_hint·schema_version)"
```

---

### Task 2: 두뇌 — `remediation/advisor.py`

**Files:**
- Create: `backend/domain/management/remediation/advisor.py`
- Test: `backend/tests/management/test_remediation_advisor.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/management/test_remediation_advisor.py`:
```python
# advisor 테스트 — 재검증(정상/이상)·옵션 풀 고정 스키마·조회 실패 폴백
from __future__ import annotations

from types import SimpleNamespace

import pytest

from domain.management.remediation.advisor import OPTION_POOLS, build_options, consult
from domain.management.remediation.contracts import ConsultResult


class FakeReader:
    """list_campaigns/get_metrics만 흉내 — advisor는 이 두 개만 읽는다."""

    def __init__(self, impressions: int = 1000, fail: bool = False):
        self._impressions = impressions
        self._fail = fail

    async def list_campaigns(self):
        if self._fail:
            raise RuntimeError("meta down")
        return [SimpleNamespace(campaign_id="camp_1", name="여름 캠페인")]

    async def get_metrics(self, campaign_id, now):
        if self._fail:
            raise RuntimeError("meta down")
        return SimpleNamespace(impressions=self._impressions)


class _Settings:
    openai_api_key = None  # LLM polish 비활성 → 결정론 문구


@pytest.mark.asyncio
async def test_consult_verified_normal_when_impressions_positive():
    res = await consult(_Settings(), "camp_1", reader=FakeReader(impressions=500))
    assert isinstance(res, ConsultResult)
    assert res.status == "normal"
    assert res.options == []
    assert "정상" in res.message


@pytest.mark.asyncio
async def test_consult_anomaly_when_no_delivery():
    res = await consult(_Settings(), "camp_1", reader=FakeReader(impressions=0))
    assert res.status == "anomaly"
    assert res.anomaly_type == "no_delivery"
    assert res.campaign_name == "여름 캠페인"
    assert res.diagnosed_at.endswith("+00:00")  # UTC-aware ISO
    assert len(res.options) >= 2
    # 메시지에 번호 옵션이 렌더링돼 있어야 한다
    assert "①" in res.message or "1)" in res.message


@pytest.mark.asyncio
async def test_consult_returns_none_on_reader_failure():
    res = await consult(_Settings(), "camp_1", reader=FakeReader(fail=True))
    assert res is None  # 조회 실패 = 판단 불가(sink는 skip 처리)


def test_all_option_pools_emit_contract_compliant_options():
    """모든 anomaly_type 풀이 고정 계약 준수 — enum 어휘·index 1부터 연속·tool_hint."""
    for anomaly_type in OPTION_POOLS:
        options = build_options(anomaly_type)
        # ConsultResult validator가 status 규칙·index 연속·tool_hint 등록 여부를 강제
        ConsultResult(
            status="anomaly", campaign_id="c", anomaly_type=anomaly_type, options=options
        )
        assert options[-1].action.value == "OBSERVE"  # 관망은 항상 마지막
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_remediation_advisor.py -v`
Expected: FAIL — `ModuleNotFoundError: domain.management.remediation.advisor`

- [ ] **Step 3: 구현**

`backend/domain/management/remediation/advisor.py`:
```python
# 이상 조치 advisor — 서버에서 실측 재검증 후 상황 설명 + 조치 옵션을 만든다 (🅱)
"""클라이언트가 넘긴 진단은 신뢰하지 않는다 — 항상 reader로 재조회해 재검증한다.

v1 검증 신호는 스케줄러 스캐너와 동일(impressions==0 → no_delivery). 그 외는 정상 응답.
설명 문구는 LLM(gpt-4o-mini)로 다듬되, 키 없음/실패 시 결정론 템플릿 폴백(채팅 안 죽음).
옵션 구조는 contracts.py 고정 계약 — LLM은 문구만 만지고 옵션은 절대 변형 못 한다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from domain.management.remediation.contracts import (
    ConsultResult,
    OptionKind,
    RemediationAction,
    RemediationOption,
)
from domain.management.wiring import build_reader

_CIRCLED = "①②③④⑤"

#: anomaly_type → (kind, action, label, tool_hint) 튜플 풀. 관망은 항상 마지막.
OPTION_POOLS: dict[str, list[tuple[OptionKind, RemediationAction, str, str | None]]] = {
    "no_delivery": [
        (OptionKind.PLATFORM, RemediationAction.VERIFY_SIM, "시뮬레이션으로 소재 점검", "run_simulation"),
        (OptionKind.PLATFORM, RemediationAction.REGENERATE_CREATIVE, "새 시안 생성해 교체 준비", "run_generation"),
        (OptionKind.SPEND, RemediationAction.PAUSE_CAMPAIGN, "일시중지(승인 필요)", "manage_campaign"),
        (OptionKind.OBSERVE, RemediationAction.OBSERVE, "관망(추가 관측)", None),
    ],
    "quality_degraded": [
        (OptionKind.PLATFORM, RemediationAction.REGENERATE_CREATIVE, "새 시안 생성해 교체 준비", "run_generation"),
        (OptionKind.PLATFORM, RemediationAction.VERIFY_SIM, "시뮬레이션으로 먼저 검증", "run_simulation"),
        (OptionKind.SPEND, RemediationAction.PAUSE_CAMPAIGN, "일시중지(승인 필요)", "manage_campaign"),
        (OptionKind.OBSERVE, RemediationAction.OBSERVE, "관망(추가 관측)", None),
    ],
    "budget_exhausted": [
        (OptionKind.SPEND, RemediationAction.INCREASE_BUDGET, "예산 증액(승인 필요)", "manage_campaign"),
        (OptionKind.SPEND, RemediationAction.PAUSE_CAMPAIGN, "일시중지(승인 필요)", "manage_campaign"),
        (OptionKind.OBSERVE, RemediationAction.OBSERVE, "관망(추가 관측)", None),
    ],
}

_HYPOTHESIS: dict[str, str] = {
    "no_delivery": "활성 캠페인인데 노출이 0이에요. 심사·예산·타깃 문제일 수 있어요.",
    "quality_degraded": "CTR이 지속 하락 중이에요. 크리에이티브 품질 저하로 보여요.",
    "budget_exhausted": "예산이 일찍 소진되고 있어요.",
}


def build_options(anomaly_type: str) -> list[RemediationOption]:
    """풀 → 고정 계약 옵션 목록(index 1부터 부여). 미등록 anomaly는 no_delivery 풀."""
    pool = OPTION_POOLS.get(anomaly_type, OPTION_POOLS["no_delivery"])
    return [
        RemediationOption(index=i, kind=kind, action=action, label=label, tool_hint=hint)
        for i, (kind, action, label, hint) in enumerate(pool, start=1)
    ]


def _render_message(name: str, anomaly_type: str, options: list[RemediationOption]) -> str:
    """결정론 메시지 템플릿 — LLM 폴백의 최종 형태이기도 하다."""
    lines = [
        f"{_CIRCLED[o.index - 1] if o.index <= len(_CIRCLED) else o.index} {o.label}"
        for o in options
    ]
    hypothesis = _HYPOTHESIS.get(anomaly_type, "성과 이상이 감지됐어요.")
    return (
        f"**{name}** 캠페인에 이상이 감지됐어요.\n{hypothesis}\n\n"
        "어떻게 하실래요?\n" + "\n".join(lines) + "\n\n번호로 답해 주세요."
    )


async def _polish(settings: Any, draft: str) -> str:
    """LLM으로 어조만 다듬는다 — 옵션 번호·구조는 유지 지시. 실패 시 draft 그대로."""
    api_key = getattr(settings, "openai_api_key", None)
    if not api_key:
        return draft
    try:
        from langchain_openai import ChatOpenAI  # noqa: PLC0415 — 키 없는 환경 보호

        llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.3)
        resp = await llm.ainvoke(
            [
                (
                    "system",
                    "광고 운영 어시스턴트의 알림 문구를 자연스럽게 다듬어라. "
                    "번호 옵션(①②…)과 그 순서·내용은 절대 바꾸지 말 것. 한국어, 간결하게.",
                ),
                ("human", draft),
            ],
            config={"run_name": "management:consult_polish", "tags": ["management"]},
        )
        text = resp.content if isinstance(resp.content, str) else ""
        return text or draft
    except Exception:  # noqa: BLE001 — LLM 실패는 결정론 문구 폴백
        return draft


async def find_campaign_id(settings: Any, name: str, *, reader: Any = None) -> str | None:
    """이름 부분일치(대소문자 무시)로 campaign_id 해소 — 다건이면 첫 건."""
    reader = reader or build_reader(settings)
    try:
        for c in await reader.list_campaigns():
            if name and name.lower() in (c.name or "").lower():
                return c.campaign_id
    except Exception:  # noqa: BLE001 — 조회 실패는 미해소
        return None
    return None


async def consult(
    settings: Any, campaign_id: str, *, reader: Any = None, now: datetime | None = None
) -> ConsultResult | None:
    """실측 재조회 → 재검증 → ConsultResult. 조회 실패면 None(호출자가 skip 처리)."""
    reader = reader or build_reader(settings)
    now = now or datetime.now(UTC)
    try:
        name = campaign_id
        for c in await reader.list_campaigns():
            if c.campaign_id == campaign_id:
                name = c.name or campaign_id
                break
        metrics = await reader.get_metrics(campaign_id, now)
    except Exception:  # noqa: BLE001 — 실측 조회 실패 = 판단 불가
        return None

    if getattr(metrics, "impressions", 0) != 0:
        return ConsultResult(
            status="normal",
            campaign_id=campaign_id,
            campaign_name=name,
            diagnosed_at=now.isoformat(),
            message=f"{name} 캠페인을 다시 확인했어요 — 지금은 정상 범위로 보여요.",
        )

    anomaly_type = "no_delivery"
    options = build_options(anomaly_type)
    message = await _polish(settings, _render_message(name, anomaly_type, options))
    return ConsultResult(
        status="anomaly",
        campaign_id=campaign_id,
        campaign_name=name,
        anomaly_type=anomaly_type,
        confidence=0.9,
        diagnosed_at=now.isoformat(),
        message=message,
        options=options,
    )
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_remediation_advisor.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 커밋**

```bash
git add backend/domain/management/remediation/advisor.py backend/tests/management/test_remediation_advisor.py
git commit -m "add: remediation advisor — 실측 재검증·옵션 풀·결정론 문구(LLM 폴백)"
```

---

### Task 3: 캠페인→프로젝트 resolver — `remediation/resolver.py`

**Files:**
- Create: `backend/domain/management/remediation/resolver.py`
- Test: `backend/tests/management/test_remediation_resolver.py`

스펙 §7 체인 1(AdCampaignLog 역추적)만 구현. 체인 2(생성 제안 링크)는 실행된 Meta
campaign_id ↔ proposal 연계 저장 위치가 미확인이라 **후속 PR**(§7-2 열린 결정) — resolver를
순서 리스트 구조로 만들어 꽂을 자리를 남긴다. 실패는 None(호출자가 skip).

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/management/test_remediation_resolver.py`:
```python
# resolver 테스트 — AdCampaignLog 역추적(raw SQL, SQLite 검증)·org 불일치 fail-closed·실패 None
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from domain.management.remediation.resolver import resolve_project


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # resolver의 raw SQL이 쓰는 세 테이블만 최소 DDL로 생성
        await conn.execute(
            text("CREATE TABLE projects (id TEXT PRIMARY KEY, organization_id TEXT)")
        )
        await conn.execute(
            text(
                "CREATE TABLE ad_generations ("
                "id TEXT PRIMARY KEY, project_id TEXT)"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE ad_campaign_logs ("
                "id TEXT PRIMARY KEY, generation_id TEXT, campaign_id TEXT, "
                "created_at TEXT DEFAULT '2026-07-02T00:00:00')"
            )
        )
        await conn.execute(text("INSERT INTO projects VALUES ('proj-77', 'org-9')"))
        await conn.execute(
            text("INSERT INTO ad_generations VALUES ('gen-1', 'proj-77')")
        )
        await conn.execute(
            text(
                "INSERT INTO ad_campaign_logs (id, generation_id, campaign_id) "
                "VALUES ('log-1', 'gen-1', 'camp_meta_123')"
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_resolves_project_and_org_via_ad_campaign_log(session_factory):
    resolved = await resolve_project("camp_meta_123", session_factory=session_factory)
    assert resolved == ("proj-77", "org-9")


@pytest.mark.asyncio
async def test_fail_closed_on_org_mismatch(session_factory):
    # 기대 org와 다르면 매핑 폐기(None) — 오배정=기밀 노출이므로 fail-closed
    resolved = await resolve_project(
        "camp_meta_123", expected_org_id="org-other", session_factory=session_factory
    )
    assert resolved is None


@pytest.mark.asyncio
async def test_passes_when_expected_org_matches(session_factory):
    resolved = await resolve_project(
        "camp_meta_123", expected_org_id="org-9", session_factory=session_factory
    )
    assert resolved == ("proj-77", "org-9")


@pytest.mark.asyncio
async def test_returns_none_when_no_link(session_factory):
    assert await resolve_project("unknown_camp", session_factory=session_factory) is None


@pytest.mark.asyncio
async def test_returns_none_on_db_failure():
    def broken_factory():
        raise RuntimeError("db down")

    assert await resolve_project("camp_meta_123", session_factory=broken_factory) is None
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_remediation_resolver.py -v`
Expected: FAIL — `ModuleNotFoundError: domain.management.remediation.resolver`

- [ ] **Step 3: 구현**

`backend/domain/management/remediation/resolver.py`:
```python
# 캠페인→프로젝트 역추적 — 오배정=기밀 노출이므로 결정론 체인 + org fail-closed (🅱)
"""스펙 §7. 체인 1: AdCampaignLog(campaign_id) → generation → project(+org).
- expected_org_id가 주어지면 불일치 시 None(fail-closed). 스케줄러 tenant="global"이면 미검증.
- 반환 (project_id, organization_id) — 해석된 org는 consult meta의 org_id 정본이 된다.
체인 2(생성 제안 링크)는 campaign_id↔proposal 연계 저장 확인 후 후속 — _CHAIN에 추가.
타 도메인 테이블 raw SQL 읽기는 SimPredictionReader 선례와 동일 성격(읽기 전용).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

_VIA_CAMPAIGN_LOG = text(
    """
    SELECT g.project_id, p.organization_id
    FROM ad_campaign_logs l
    JOIN ad_generations g ON g.id = l.generation_id
    JOIN projects p ON p.id = g.project_id
    WHERE l.campaign_id = :cid AND g.project_id IS NOT NULL
    ORDER BY l.created_at DESC
    LIMIT 1
    """
)


async def _via_campaign_log(
    campaign_id: str, session_factory: Any
) -> tuple[str, str] | None:
    async with session_factory() as db:
        row = (await db.execute(_VIA_CAMPAIGN_LOG, {"cid": campaign_id})).first()
        if row is None:
            return None
        return str(row[0]), str(row[1])


#: 순서 리스트 — 체인 2(생성 제안 링크)는 연계 확인 후 여기 추가한다.
_CHAIN = (_via_campaign_log,)


async def resolve_project(
    campaign_id: str, *, expected_org_id: str | None = None, session_factory: Any = None
) -> tuple[str, str] | None:
    """체인 순서대로 시도 → (project_id, org_id). org 불일치·전부 실패면 None(예외 안 나감)."""
    if session_factory is None:
        from core.db import AsyncSessionLocal  # noqa: PLC0415 — 테스트 주입 지원

        session_factory = AsyncSessionLocal
    for step in _CHAIN:
        try:
            resolved = await step(campaign_id, session_factory)
        except Exception:  # noqa: BLE001 — 역추적 실패는 다음 체인/skip
            continue
        if resolved is None:
            continue
        if expected_org_id is not None and resolved[1] != expected_org_id:
            return None  # fail-closed — 다른 org의 프로젝트로는 절대 배달하지 않는다
        return resolved
    return None
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_remediation_resolver.py -v`
Expected: PASS (5 tests). `aiosqlite` 미설치로 에러 나면 dev 의존성 확인:
`uv run python -c "import aiosqlite"` — 없으면 기존 테스트가 SQLite를 어떻게 쓰는지
`grep -r "aiosqlite" backend/tests` 확인 후 동일 방식 사용(없으면 `uv add --dev aiosqlite`).

- [ ] **Step 5: 커밋**

```bash
git add backend/domain/management/remediation/resolver.py backend/tests/management/test_remediation_resolver.py
git commit -m "add: 캠페인-프로젝트 역추적 resolver(AdCampaignLog 체인, org fail-closed)"
```

---

### Task 4: 채팅 알림 sink — `remediation/chat_sink.py`

**Files:**
- Create: `backend/domain/management/remediation/chat_sink.py`
- Test: `backend/tests/management/test_remediation_chat_sink.py`

스팸 방지 판정표(§5) + composite 폴백(§7-1) + 배달 요약. 영속 접근은 store 포트로 분리해
단위 테스트는 fake로. `deliver()`가 결과를 반환하고 `notify()`(Protocol 준수)는 감싼다.

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/management/test_remediation_chat_sink.py`:
```python
# chat sink 테스트 — 판정표 4분기·매핑 skip·race 방어·composite 폴백·요약·실패 격리
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from domain.management.remediation.chat_sink import ChatNotificationSink
from domain.management.remediation.contracts import ConsultResult


def _consult(status="anomaly", campaign_id="camp_1", anomaly="no_delivery"):
    from domain.management.remediation.advisor import build_options

    return ConsultResult(
        status=status,
        campaign_id=campaign_id,
        campaign_name="여름 캠페인",
        anomaly_type=anomaly if status == "anomaly" else "",
        diagnosed_at=datetime.now(UTC).isoformat(),
        message="테스트 메시지 ①②",
        options=build_options(anomaly) if status == "anomaly" else [],
    )


class Store:
    """세션·메시지 영속 포트 fake — last_read_at/기존 consult 시각을 시나리오별로 주입.

    latest_consult_at에 yield 지점(sleep 0)을 둬 race 테스트가 실제 인터리빙을 만들고,
    append가 latest_at을 갱신해 잠금 직렬화 후 두 번째 deliver가 dedup에 걸리게 한다.
    """

    def __init__(self, last_read_at=None, latest_at=None):
        self.last_read_at = last_read_at
        self.latest_at = latest_at
        self.appended: list[tuple[str, str, dict]] = []

    async def find_or_create_session(self, project_id, title):
        return "sess-1", self.last_read_at

    async def latest_consult_at(self, session_id, campaign_id, anomaly_type):
        await asyncio.sleep(0)  # 이벤트 루프 양보 — 잠금 없으면 이중 insert 재현
        return self.latest_at

    async def append_consult(self, session_id, content, meta):
        self.appended.append((session_id, content, meta))
        self.latest_at = datetime.now(UTC)


class FakeFallback:
    def __init__(self):
        self.calls: list[dict] = []

    async def notify(self, tenant_id, title, body, *, meta=None):
        self.calls.append({"tenant_id": tenant_id, "title": title, "meta": meta})


class _Settings:
    openai_api_key = None
    management_consult_cooldown_hours = 24


def _sink(store, *, resolver=None, consult_result="anomaly", fallback=None):
    async def _resolver(campaign_id, *, expected_org_id=None):
        return None if resolver == "none" else ("proj-1", "org-9")

    async def _consult_fn(settings, campaign_id, **kw):
        if consult_result == "fail":
            return None
        return _consult(status=consult_result)

    return ChatNotificationSink(
        _Settings(),
        fallback=fallback or FakeFallback(),
        store=store,
        resolver=_resolver,
        consult=_consult_fn,
    )


NOW = datetime.now(UTC)


@pytest.mark.asyncio
async def test_delivers_on_new_anomaly():
    store = Store()
    sink = _sink(store)
    out = await sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "delivered"
    assert len(store.appended) == 1
    _, content, meta = store.appended[0]
    assert meta["kind"] == "remediation_consult"
    assert meta["schema_version"] == 1
    assert meta["org_id"] == "org-9"  # tenant("global")가 아니라 해석된 org가 정본


@pytest.mark.asyncio
async def test_concurrent_delivers_for_same_campaign_insert_once():
    # 스케줄 틱 + 수동 스캔 동시 배달 race — 모듈 잠금으로 정확히 1건만 insert
    store = Store()
    sink = _sink(store)
    o1, o2 = await asyncio.gather(
        sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"}),
        sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"}),
    )
    assert sorted([o1.status, o2.status]) == ["delivered", "skipped"]
    assert len(store.appended) == 1


@pytest.mark.asyncio
async def test_skips_when_no_project_mapping():
    fb = FakeFallback()
    sink = _sink(Store(), resolver="none", fallback=fb)
    out = await sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "skipped" and out.reason == "no_project_mapping"
    assert len(fb.calls) == 1  # composite 폴백 — 로그 sink로 위임


@pytest.mark.asyncio
async def test_skips_when_verified_normal():
    sink = _sink(Store(), consult_result="normal")
    out = await sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "skipped" and out.reason == "verified_normal"


@pytest.mark.asyncio
async def test_skips_when_bell_pending():
    # 기존 consult 있음 + 세션 미열람(last_read_at이 consult보다 과거/None) → 생략
    store = Store(last_read_at=None, latest_at=NOW - timedelta(hours=1))
    out = await _sink(store).deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "skipped" and out.reason == "bell_pending"


@pytest.mark.asyncio
async def test_skips_within_cooldown_after_read():
    latest = NOW - timedelta(hours=2)
    store = Store(last_read_at=NOW - timedelta(hours=1), latest_at=latest)  # 열람함
    out = await _sink(store).deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "skipped" and out.reason == "cooldown"


@pytest.mark.asyncio
async def test_followup_after_cooldown_with_changed_tone():
    latest = NOW - timedelta(hours=30)  # cooldown 24h 경과
    store = Store(last_read_at=NOW - timedelta(hours=25), latest_at=latest)
    out = await _sink(store).deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "delivered"
    _, content, _ = store.appended[0]
    assert "아직 계속" in content  # 후속 어조


@pytest.mark.asyncio
async def test_one_failure_does_not_break_loop_and_summary_aggregates():
    class BrokenStore(Store):
        async def append_consult(self, *a):
            raise RuntimeError("db down")

    fb = FakeFallback()
    sink = _sink(BrokenStore(), fallback=fb)
    out1 = await sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out1.status == "failed"  # 예외가 밖으로 안 나감
    assert len(fb.calls) == 1
    s = sink.summary()
    assert s["failed"][0]["campaign_id"] == "camp_1"
    assert s["delivered"] == 0
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_remediation_chat_sink.py -v`
Expected: FAIL — `ModuleNotFoundError: domain.management.remediation.chat_sink`

- [ ] **Step 3: 구현**

`backend/domain/management/remediation/chat_sink.py`:
```python
# 채팅 알림 sink — 이상 발견 시 advisor 상담 메시지를 프로젝트 세션에 먼저 심는다 (🅱)
"""NotificationSink 포트 준수(notify). deliver()는 배달 결과를 반환해 수동 스캔 요약에 쓴다.

스팸 방지 판정표(스펙 §5): 신규→통지 / 미열람→생략(bell_pending) / 열람+쿨다운 내→생략 /
열람+쿨다운 경과+이상 지속→후속 통지(어조 변경). 매핑 실패·저장 실패는 사용자에게 안 보이고
fallback(LogNotificationSink)으로 고정 스키마 이벤트만 남긴다. 1건 실패가 루프를 안 죽인다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from domain.management.remediation import advisor as _advisor
from domain.management.remediation.resolver import resolve_project

logger = logging.getLogger("clickme")

_SESSION_TITLE = "⚠ 캠페인 이상 알림"
_FOLLOWUP_PREFIX = "지난번 알려드린 건이 아직 계속되고 있어요.\n\n"

#: (campaign_id:anomaly) 배달 잠금 — 스케줄 틱·수동 스캔이 겹쳐도 이중 insert 방지.
#: 모듈 레벨인 이유: sink 인스턴스가 경로마다 따로 생성돼 인스턴스 잠금은 무효.
#: 단일 프로세스 전제(단일 EC2) — 멀티워커는 DB 유니크 제약 필요(범위 밖).
_delivery_locks: dict[str, asyncio.Lock] = {}


@dataclass(frozen=True)
class DeliveryOutcome:
    campaign_id: str
    status: str  # delivered | skipped | failed
    reason: str | None = None
    session_id: str | None = None


class DbConsultStore:
    """실제 영속 — 세션 확보는 core 모델, 메시지 심기는 chat의 공개 함수 재사용."""

    async def find_or_create_session(
        self, project_id: str, title: str
    ) -> tuple[str, datetime | None]:
        from uuid import UUID  # noqa: PLC0415

        from sqlalchemy import select  # noqa: PLC0415

        from core.db import AsyncSessionLocal  # noqa: PLC0415
        from core.models import ChatSession  # noqa: PLC0415

        async with AsyncSessionLocal() as db:
            row = await db.execute(
                select(ChatSession)
                .where(ChatSession.project_id == UUID(project_id), ChatSession.title == title)
                .order_by(ChatSession.created_at.desc())
                .limit(1)
            )
            s = row.scalars().first()
            if s is None:
                s = ChatSession(project_id=UUID(project_id), title=title)
                db.add(s)
                await db.commit()
                await db.refresh(s)
            return str(s.id), s.last_read_at

    async def latest_consult_at(
        self, session_id: str, campaign_id: str, anomaly_type: str
    ) -> datetime | None:
        from uuid import UUID  # noqa: PLC0415

        from sqlalchemy import select  # noqa: PLC0415

        from core.db import AsyncSessionLocal  # noqa: PLC0415
        from core.models import ChatMessage  # noqa: PLC0415

        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == UUID(session_id))
                .order_by(ChatMessage.created_at.desc())
                .limit(50)
            )
            # JSONB 연산자 비의존(파이썬 필터) — SQLite 테스트·이식성 우선, 세션당 최근 50건이면 충분
            for m in rows.scalars():
                meta = m.meta or {}
                if (
                    meta.get("kind") == "remediation_consult"
                    and meta.get("campaign_id") == campaign_id
                    and meta.get("anomaly_type") == anomaly_type
                ):
                    return m.created_at
        return None

    async def append_consult(self, session_id: str, content: str, meta: dict) -> None:
        from domain.chat.history import append_widget_messages  # noqa: PLC0415

        saved = await append_widget_messages(session_id, [{"content": content, "meta": meta}])
        if not saved:
            raise RuntimeError("consult 메시지 저장 실패")


class ChatNotificationSink:
    def __init__(
        self,
        settings: Any,
        *,
        fallback: Any,
        store: Any = None,
        resolver: Any = None,
        consult: Any = None,
        clock: Any = None,
    ) -> None:
        self._settings = settings
        self._fallback = fallback
        self._store = store or DbConsultStore()
        self._resolve = resolver or resolve_project
        self._consult = consult or _advisor.consult
        self._clock = clock or (lambda: datetime.now(UTC))
        self._outcomes: list[DeliveryOutcome] = []

    # NotificationSink 포트 준수 — 스케줄러는 이 시그니처만 안다.
    async def notify(
        self, tenant_id: str, title: str, body: str, *, meta: dict | None = None
    ) -> None:
        await self.deliver(tenant_id, title, body, meta=meta)

    async def deliver(
        self, tenant_id: str, title: str, body: str, *, meta: dict | None = None
    ) -> DeliveryOutcome:
        campaign_id = (meta or {}).get("campaign_id") or ""
        try:
            outcome = await self._deliver(tenant_id, title, body, campaign_id)
        except Exception as exc:  # noqa: BLE001 — 1건 실패가 스캔 루프를 안 죽임
            await self._log_event(
                "notify_failed", tenant_id, title, body, campaign_id, "error",
                error=f"{type(exc).__name__}: {exc}",
            )
            outcome = DeliveryOutcome(campaign_id=campaign_id, status="failed", reason="error")
        self._outcomes.append(outcome)
        return outcome

    async def _deliver(
        self, tenant_id: str, title: str, body: str, campaign_id: str
    ) -> DeliveryOutcome:
        if not campaign_id:
            await self._log_event("notify_skipped", tenant_id, title, body, "", "no_campaign_id")
            return DeliveryOutcome(campaign_id="", status="skipped", reason="no_campaign_id")

        # 스케줄러 tenant("global")는 org 미상 — 실제 org tenant일 때만 fail-closed 대조.
        expected_org = None if tenant_id in ("", "global") else tenant_id
        resolved = await self._resolve(campaign_id, expected_org_id=expected_org)
        if resolved is None:
            await self._log_event(
                "notify_skipped", tenant_id, title, body, campaign_id, "no_project_mapping"
            )
            return DeliveryOutcome(
                campaign_id=campaign_id, status="skipped", reason="no_project_mapping"
            )
        project_id, resolved_org = resolved

        consult = await self._consult(self._settings, campaign_id)
        if consult is None:
            await self._log_event(
                "notify_skipped", tenant_id, title, body, campaign_id, "consult_failed"
            )
            return DeliveryOutcome(
                campaign_id=campaign_id, status="skipped", reason="consult_failed"
            )
        if consult.status == "normal":
            return DeliveryOutcome(
                campaign_id=campaign_id, status="skipped", reason="verified_normal"
            )

        # race 방어 — dedup 판정과 insert를 (campaign, anomaly) 단위로 직렬화.
        lock = _delivery_locks.setdefault(
            f"{campaign_id}:{consult.anomaly_type}", asyncio.Lock()
        )
        async with lock:
            session_id, last_read_at = await self._store.find_or_create_session(
                project_id, _SESSION_TITLE
            )
            now = self._clock()
            latest = await self._store.latest_consult_at(
                session_id, campaign_id, consult.anomaly_type
            )
            followup = False
            if latest is not None:
                latest_aware = latest if latest.tzinfo else latest.replace(tzinfo=UTC)
                read = last_read_at if last_read_at is None or last_read_at.tzinfo else (
                    last_read_at.replace(tzinfo=UTC)
                )
                if read is None or read < latest_aware:
                    return DeliveryOutcome(
                        campaign_id=campaign_id, status="skipped", reason="bell_pending",
                        session_id=session_id,
                    )
                cooldown = timedelta(
                    hours=getattr(self._settings, "management_consult_cooldown_hours", 24)
                )
                if now - latest_aware < cooldown:
                    return DeliveryOutcome(
                        campaign_id=campaign_id, status="skipped", reason="cooldown",
                        session_id=session_id,
                    )
                followup = True

            content = (_FOLLOWUP_PREFIX if followup else "") + consult.message
            # meta의 org 정본 = 역추적으로 해석된 org(스케줄러 tenant "global" 오염 방지).
            await self._store.append_consult(
                session_id, content, consult.to_meta(org_id=resolved_org)
            )
        return DeliveryOutcome(
            campaign_id=campaign_id, status="delivered", session_id=session_id
        )

    async def _log_event(
        self,
        event: str,
        tenant_id: str,
        title: str,
        body: str,
        campaign_id: str,
        reason: str,
        *,
        session_id: str | None = None,
        error: str | None = None,
    ) -> None:
        """고정 스키마 관측 이벤트 — 운영 디버깅용 필드 포함(기밀·예산·크리에이티브 제외)."""
        logger.info(
            '{"event": "management.%s", "campaign_id": "%s", "tenant": "%s", '
            '"reason": "%s", "session_id": "%s", "error": "%s"}',
            event,
            campaign_id,
            tenant_id,
            reason,
            session_id or "",
            (error or "")[:120],
        )
        try:
            await self._fallback.notify(
                tenant_id, title, body,
                meta={"campaign_id": campaign_id, "reason": reason},
            )
        except Exception:  # noqa: BLE001 — 폴백 실패까지는 삼킨다
            pass

    def summary(self) -> dict:
        """수동 스캔 응답용 배달 요약 — {delivered, skipped[], failed[]}."""
        return {
            "delivered": sum(1 for o in self._outcomes if o.status == "delivered"),
            "skipped": [
                {"campaign_id": o.campaign_id, "reason": o.reason}
                for o in self._outcomes
                if o.status == "skipped"
            ],
            "failed": [
                {"campaign_id": o.campaign_id, "reason": o.reason}
                for o in self._outcomes
                if o.status == "failed"
            ],
        }
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_remediation_chat_sink.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: 커밋**

```bash
git add backend/domain/management/remediation/chat_sink.py backend/tests/management/test_remediation_chat_sink.py
git commit -m "add: 채팅 알림 sink — 판정표 스팸 방지·race 잠금·composite 폴백·배달 요약"
```

---

### Task 5: seam 분기 — `notifications.py` (⚠ 공통 성격 파일, 사전 공지)

**Files:**
- Modify: `backend/domain/management/notifications.py:32-34` (`build_notification_sink`)
- Test: `backend/tests/management/test_remediation_wiring.py`

⚠ notifications.py는 소유 미표기 파일 — 이 분기 1줄 추가를 🅰에게 공지(스펙 §7-2).
설정 `management_chat_notify_enabled`(getattr, 기본 False)로 기존 동작 완전 보존.

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/management/test_remediation_wiring.py`:
```python
# sink seam 분기 테스트 — 설정 off면 기존 로그 sink, on이면 chat sink
from __future__ import annotations

from domain.management.notifications import LogNotificationSink, build_notification_sink
from domain.management.remediation.chat_sink import ChatNotificationSink


class _Off:
    management_chat_notify_enabled = False


class _On:
    management_chat_notify_enabled = True


def test_default_stays_log_sink():
    assert isinstance(build_notification_sink(_Off()), LogNotificationSink)


def test_enabled_returns_chat_sink_with_log_fallback():
    sink = build_notification_sink(_On())
    assert isinstance(sink, ChatNotificationSink)
    assert isinstance(sink._fallback, LogNotificationSink)  # noqa: SLF001 — 배선 검증
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_remediation_wiring.py -v`
Expected: FAIL — `test_enabled_returns_chat_sink_with_log_fallback`에서 LogNotificationSink 반환

- [ ] **Step 3: 분기 추가**

`backend/domain/management/notifications.py`의 `build_notification_sink`를 다음으로 교체:
```python
def build_notification_sink(settings) -> NotificationSink:
    """기본은 로그 sink. management_chat_notify_enabled면 채팅 sink(로그 폴백 내장)."""
    if getattr(settings, "management_chat_notify_enabled", False):
        from domain.management.remediation.chat_sink import ChatNotificationSink  # noqa: PLC0415

        return ChatNotificationSink(settings, fallback=LogNotificationSink())
    return LogNotificationSink()
```

- [ ] **Step 4: 통과 확인 + 기존 스케줄러 테스트 회귀 확인**

Run: `cd backend && uv run pytest tests/management/test_remediation_wiring.py -v`
Expected: PASS (2 tests)
Run: `cd backend && uv run pytest tests/ -k "scheduler or notification" -v`
Expected: 기존 테스트 전부 PASS (기본 off라 동작 불변)

- [ ] **Step 5: 커밋**

```bash
git add backend/domain/management/notifications.py backend/tests/management/test_remediation_wiring.py
git commit -m "edit: 알림 sink seam에 채팅 sink 분기 추가(기본 off, 기존 동작 보존)"
```

---

### Task 6: 컨텍스트 왕복 — `remediation/context.py` + `chat.py` 주입

**Files:**
- Create: `backend/domain/management/remediation/context.py`
- Modify: `backend/api/routers/chat.py:410-412` (memory_context 회수 직후)
- Test: `backend/tests/management/test_remediation_context.py`

주입 3조건(스펙 §4): TTL 24h 내 + 최근 K=10 메시지 내 + 최신 1건만. 판정은 순수 함수로
분리해 단위 테스트, chat.py에는 얇은 async 래퍼 호출만 추가.

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/management/test_remediation_context.py`:
```python
# 컨텍스트 주입 판정 테스트 — 3조건(TTL·근접성·최신 1건) 각각 미충족 시 None
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from domain.management.remediation.context import pick_consult_context

NOW = datetime.now(UTC)


def _meta(campaign="camp_1", diagnosed_at=None):
    return {
        "kind": "remediation_consult",
        "schema_version": 1,
        "campaign_id": campaign,
        "anomaly_type": "no_delivery",
        "diagnosed_at": (diagnosed_at or NOW).isoformat(),
        "options": [
            {"index": 1, "action": "VERIFY_SIM", "tool_hint": "run_simulation", "label": "시뮬 검증"},
            {"index": 2, "action": "OBSERVE", "tool_hint": None, "label": "관망"},
        ],
    }


def test_injects_for_fresh_consult_in_recent_messages():
    msgs = [(None, NOW), (_meta(), NOW - timedelta(hours=1))]  # (meta, created_at) 최신순
    ctx = pick_consult_context(msgs, now=NOW, ttl_hours=24, recent_k=10)
    assert ctx is not None
    assert "camp_1" in ctx and "run_simulation" in ctx
    assert "직접 실행하지" in ctx  # HITL 지시 포함


def test_no_injection_when_ttl_expired():
    msgs = [(_meta(diagnosed_at=NOW - timedelta(hours=30)), NOW - timedelta(hours=30))]
    assert pick_consult_context(msgs, now=NOW, ttl_hours=24, recent_k=10) is None


def test_no_injection_when_consult_outside_recent_k():
    filler = [(None, NOW)] * 10  # 최근 10개가 전부 일반 메시지
    msgs = filler + [(_meta(), NOW - timedelta(hours=1))]
    assert pick_consult_context(msgs, now=NOW, ttl_hours=24, recent_k=10) is None


def test_latest_consult_wins_when_multiple():
    old = _meta(campaign="camp_old", diagnosed_at=NOW - timedelta(hours=2))
    new = _meta(campaign="camp_new", diagnosed_at=NOW - timedelta(hours=1))
    msgs = [(new, NOW - timedelta(hours=1)), (old, NOW - timedelta(hours=2))]
    ctx = pick_consult_context(msgs, now=NOW, ttl_hours=24, recent_k=10)
    assert "camp_new" in ctx and "camp_old" not in ctx


def test_no_injection_after_widget_shown():
    # consult 이후 위젯 메시지 존재 = 옵션 진행됨 → 낡은 상담 재주입 중단
    msgs = [
        ({"widget": {"type": "gen_form"}}, NOW),
        (_meta(), NOW - timedelta(hours=1)),
    ]
    assert pick_consult_context(msgs, now=NOW, ttl_hours=24, recent_k=10) is None


def test_none_when_no_consult():
    assert pick_consult_context([(None, NOW)], now=NOW, ttl_hours=24, recent_k=10) is None
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_remediation_context.py -v`
Expected: FAIL — `ModuleNotFoundError: domain.management.remediation.context`

- [ ] **Step 3: 구현**

`backend/domain/management/remediation/context.py`:
```python
# consult 컨텍스트 주입 — 세션의 최근 상담 meta를 LLM 지시문으로 복원한다 (🅱)
"""프론트는 role/content만 재전송하므로 meta는 DB에서 서버가 회수·주입한다(스펙 §4).
3조건: diagnosed_at TTL 내 · 최근 K 메시지 내 · 최신 1건만 — 미충족이면 주입 안 함.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def _build_instruction(meta: dict) -> str:
    lines = []
    for o in meta.get("options", []):
        hint = f" → 도구 {o['tool_hint']}" if o.get("tool_hint") else " (도구 호출 없음 — 관망)"
        lines.append(f"{o['index']}) {o['label']}{hint}")
    return (
        "[진행 중인 이상 조치 상담]\n"
        f"campaign_id={meta.get('campaign_id')} · anomaly={meta.get('anomaly_type')} · "
        f"진단시각={meta.get('diagnosed_at')}\n"
        "옵션:\n" + "\n".join(lines) + "\n"
        "사용자가 번호나 옵션명으로 답하면 위 표의 도구를 campaign_id와 함께 호출해 진행하라. "
        "지출 조치(manage_campaign)는 확인 카드로만 제안하고 직접 실행하지 않는다."
    )


def pick_consult_context(
    messages: list[tuple[dict | None, datetime]],
    *,
    now: datetime,
    ttl_hours: int,
    recent_k: int = 10,
) -> str | None:
    """(meta, created_at) 최신순 목록에서 주입할 컨텍스트를 고른다 — 조건 미충족이면 None.

    4조건: TTL 내 · 최근 K 내 · 최신 1건만 · consult보다 새 위젯 메시지 없음(진행됨 프록시).
    실행 완료는 세션에 안 남지만(스펙 §4) 위젯 '표시'는 meta.widget으로 남는다 — 그걸 쓴다.
    """
    for meta, _created in messages[:recent_k]:
        if meta and "widget" in meta:
            return None  # consult보다 새로운 위젯 = 옵션 진행됨 → 재주입 중단
        if not meta or meta.get("kind") != "remediation_consult":
            continue
        # 최신 1건만 — 첫 매치에서 판정하고 끝낸다(더 과거 consult는 무시).
        try:
            diagnosed = datetime.fromisoformat(str(meta.get("diagnosed_at", "")))
        except ValueError:
            return None
        if now - diagnosed > timedelta(hours=ttl_hours):
            return None
        return _build_instruction(meta)
    return None


async def recall_consult_context(session_id: str, settings: Any) -> str | None:
    """세션 최근 메시지에서 consult 컨텍스트 회수 — 실패는 None(채팅 안 막음)."""
    from datetime import UTC  # noqa: PLC0415

    try:
        from uuid import UUID  # noqa: PLC0415

        from sqlalchemy import select  # noqa: PLC0415

        from core.db import AsyncSessionLocal  # noqa: PLC0415
        from core.models import ChatMessage  # noqa: PLC0415

        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(ChatMessage.meta, ChatMessage.created_at)
                .where(ChatMessage.session_id == UUID(session_id))
                .order_by(ChatMessage.created_at.desc())
                .limit(10)
            )
            messages = [(m, c) for m, c in rows.all()]
    except Exception:  # noqa: BLE001 — 회수 실패가 답변을 막지 않게
        return None
    return pick_consult_context(
        messages,
        now=datetime.now(UTC),
        ttl_hours=getattr(settings, "management_consult_context_ttl_hours", 24),
    )
```

- [ ] **Step 4: 판정 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_remediation_context.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: chat.py 주입 (공통부 최소 터치 — 사전 공지 대상)**

`backend/api/routers/chat.py`의 `generate()` 안, 이 줄 바로 아래:
```python
        memory_context = await _recall_memory_context(body, last_message, current_user)
```
다음을 추가:
```python
        # 진행 중 이상 조치 상담 컨텍스트(management) — meta는 왕복 안 되므로 서버가 회수·주입.
        try:
            from domain.management.remediation.context import (  # noqa: PLC0415
                recall_consult_context,
            )

            consult_ctx = await recall_consult_context(body.session_id, settings)
        except Exception:  # noqa: BLE001 — 회수 실패가 채팅을 막지 않게
            consult_ctx = None
        if consult_ctx:
            memory_context = f"{memory_context}\n\n{consult_ctx}" if memory_context else consult_ctx
```

- [ ] **Step 6: 회귀 확인**

Run: `cd backend && uv run pytest tests/ -k "chat" -v`
Expected: 기존 chat 테스트 전부 PASS

- [ ] **Step 7: 커밋**

```bash
git add backend/domain/management/remediation/context.py backend/tests/management/test_remediation_context.py backend/api/routers/chat.py
git commit -m "add: consult 컨텍스트 서버측 주입(TTL·근접성·최신 1건 조건)"
```

---

### Task 7: 보조 진입 — `consult_anomaly` 도구 (⚠ 공통부, 사전 공지)

**Files:**
- Modify: `backend/api/assistant/subagent_tools.py` (`recall` 도구 정의 뒤, return 리스트 직전에 추가)

⚠ subagent_tools.py는 챗 공통부 — append-only 1개 도구 추가지만 챗 담당에게 사전 공지.
로직은 전부 domain(advisor) 위임, 여기는 얇은 래퍼만. 위젯 없음(ToolMessage 텍스트만) —
LLM이 결과를 읽고 필요 시 기존 위젯 도구를 이어서 호출한다.

- [ ] **Step 1: 도구 추가**

`recall` 도구 정의와 `return [` 사이에 추가:
```python
    # ───────────────────────── 매니지먼트 이상 상담 (위임: domain/management/remediation) ──
    @tool
    async def consult_anomaly(
        campaign_id: str = "",
        campaign_name: str = "",
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """캠페인이 '왜 안 좋은지/이상 있는지/문제 없는지' 물으면 호출. 서버 실측으로
        재검증해 이상이면 조치 옵션을, 정상이면 정상 확인을 답한다. 이름만 알면 campaign_name."""
        from domain.management.remediation.advisor import (  # noqa: PLC0415
            consult,
            find_campaign_id,
        )

        cid = campaign_id or (
            await find_campaign_id(settings, campaign_name) if campaign_name else None
        )
        if not cid:
            text_out = "캠페인을 특정하지 못했어요. 캠페인 이름이나 ID를 알려 주세요."
        else:
            res = await consult(settings, cid)
            if res is None:
                text_out = "실측 조회에 실패해 지금은 확인할 수 없어요. 잠시 후 다시 시도해 주세요."
            else:
                text_out = res.message
                if res.options:
                    # 기계가독 매핑 — LLM이 번호→도구를 오매핑하지 않게 명시(meta 미영속의 보완).
                    mapping = ", ".join(
                        f"{o.index}={o.action.value}({o.tool_hint or '관망'})"
                        for o in res.options
                    )
                    text_out += f"\n\n[옵션-도구 매핑 · campaign_id={cid}] {mapping}"
        return Command(
            update={"messages": [ToolMessage(text_out, tool_call_id=tool_call_id)]}
        )
```

> 한계(의도된 결정): 도구 경로 consult는 meta를 영속하지 않는다 — 옵션이 직전 대화
> 텍스트에 있어 LLM이 자연히 읽고, meta를 심으면 sink의 전용 세션 dedup 체계와 어긋난다.
> 부작용: 도구 경로 상담은 벨 쿨다운에 안 잡혀 벨+채팅이 각각 올 수 있음(서로 다른 표면 — 허용).

그리고 return 리스트의 `manage_campaign,` 다음 줄에 `consult_anomaly,` 추가.

- [ ] **Step 2: 임포트 스모크 확인**

Run: `cd backend && uv run python -c "from api.assistant.subagent_tools import build_chat_tools; from core.config import settings; tools = build_chat_tools(settings); print([t.name for t in tools])"`
Expected: 목록에 `consult_anomaly` 포함, 예외 없음

- [ ] **Step 3: 커밋**

```bash
git add backend/api/assistant/subagent_tools.py
git commit -m "add: 채팅 consult_anomaly 도구 — 이상 재검증·조치 옵션 보조 진입(위임만)"
```

---

### Task 8: 수동 스캔 엔드포인트 + 보호장치 — `management.py`

**Files:**
- Modify: `backend/api/routers/management.py` (`/anomaly/scan` 엔드포인트 아래에 추가)
- Test: `backend/tests/management/test_notify_scan_endpoint.py`

보호장치 4종(스펙 §6): 인증+org 스코프 / org별 동시 실행 잠금(409) / 쿨다운(429, 설정) /
통지 dedup은 sink가 담당. 응답에 배달 요약 포함. 스케줄러 스캐너 경로(run_scan) 재사용으로
mock 모드에서도 동작.

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/management/test_notify_scan_endpoint.py`:
```python
# 수동 알림 스캔 엔드포인트 테스트 — 동시 409·쿨다운 429·배달 요약 응답
from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app(monkeypatch):
    from fastapi import FastAPI

    from api.routers import management as mgmt
    from core.auth import get_current_user
    from core.config import settings

    # 느린 스캔을 흉내내 동시성 창을 만든다 + org 해석·요약만 검증
    async def fake_run_scan(_settings, sink):
        await asyncio.sleep(0.05)
        out = await sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_x"})
        return 1 if out.status == "delivered" else 0

    async def fake_require_org_id(user, db):
        return "org-1"

    monkeypatch.setattr("domain.management.scheduler.run_scan", fake_run_scan)
    monkeypatch.setattr(mgmt, "_require_org_id", fake_require_org_id)
    monkeypatch.setattr(settings, "management_scan_manual_cooldown_seconds", 0, raising=False)
    # 잠금·쿨다운 전역 상태 초기화(테스트 간 격리)
    mgmt._notify_scan_locks.clear()
    mgmt._notify_scan_last.clear()

    # sink는 매핑 실패로 skip되도록(외부 의존 없는 결정론) — resolver가 None을 내는 게 기본
    application = FastAPI()
    application.include_router(mgmt.router, prefix="/api/management")
    application.dependency_overrides[get_current_user] = lambda: object()
    return application


@pytest.mark.asyncio
async def test_concurrent_second_request_gets_409(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r1, r2 = await asyncio.gather(
            client.post("/api/management/anomaly/notify-scan"),
            client.post("/api/management/anomaly/notify-scan"),
        )
    codes = sorted([r1.status_code, r2.status_code])
    assert codes == [200, 409]  # 정확히 1건 통과, 1건 잠금 거부


@pytest.mark.asyncio
async def test_cooldown_returns_429(app, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "management_scan_manual_cooldown_seconds", 60, raising=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r1 = await client.post("/api/management/anomaly/notify-scan")
        r2 = await client.post("/api/management/anomaly/notify-scan")
    assert r1.status_code == 200
    assert r2.status_code == 429


@pytest.mark.asyncio
async def test_response_contains_delivery_summary(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.post("/api/management/anomaly/notify-scan")
    body = r.json()
    assert set(body) >= {"scanned_findings", "delivered", "skipped", "failed"}


@pytest.mark.asyncio
async def test_different_orgs_do_not_block_each_other(app, monkeypatch):
    # org별 잠금 분리 — 서로 다른 org의 동시 요청은 양쪽 다 통과해야 한다(스펙 §10)
    from itertools import count

    from api.routers import management as mgmt

    seq = count()

    async def rotating_org(user, db):
        return f"org-{next(seq)}"

    monkeypatch.setattr(mgmt, "_require_org_id", rotating_org)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r1, r2 = await asyncio.gather(
            client.post("/api/management/anomaly/notify-scan"),
            client.post("/api/management/anomaly/notify-scan"),
        )
    assert [r1.status_code, r2.status_code] == [200, 200]
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_notify_scan_endpoint.py -v`
Expected: FAIL — 404 (엔드포인트 없음)

- [ ] **Step 3: 엔드포인트 구현**

`backend/api/routers/management.py`의 `/anomaly/scan` 엔드포인트(`anomaly_scan` 함수) 바로 아래에 추가.
파일 상단 import에 `import asyncio` · `import time`이 없으면 추가(asyncio는 이미 있을 수 있음 — 확인).

```python
# 수동 알림 스캔 — org별 인프로세스 잠금·쿨다운(단일 EC2 전제, 스펙 §6)
_notify_scan_locks: dict[str, asyncio.Lock] = {}
_notify_scan_last: dict[str, float] = {}


@router.post("/anomaly/notify-scan")
async def anomaly_notify_scan(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """이상 스캔 + 채팅 선제 알림 트리거(데모·수동) — 배달 요약 반환.

    스케줄러와 같은 run_scan 경로 재사용(mock에서도 동작). 통지 스팸은 sink 판정표가
    이중 방어하므로 이 엔드포인트의 보호장치는 비용(중복 스캔) 방지가 목적.
    """
    org_id = await _require_org_id(user, db)
    key = str(org_id)

    cooldown = getattr(settings, "management_scan_manual_cooldown_seconds", 60)
    now_mono = time.monotonic()
    last = _notify_scan_last.get(key)
    if last is not None and now_mono - last < cooldown:
        raise HTTPException(429, f"{int(cooldown - (now_mono - last)) + 1}초 후 다시 시도하세요.")

    lock = _notify_scan_locks.setdefault(key, asyncio.Lock())
    if lock.locked():
        raise HTTPException(409, "이미 스캔이 진행 중입니다.")
    async with lock:
        _notify_scan_last[key] = time.monotonic()
        from domain.management.notifications import LogNotificationSink  # noqa: PLC0415
        from domain.management.remediation.chat_sink import ChatNotificationSink  # noqa: PLC0415
        from domain.management.scheduler import run_scan  # noqa: PLC0415

        sink = ChatNotificationSink(settings, fallback=LogNotificationSink())
        count = await run_scan(settings, sink)
        summary = sink.summary()

    # 고정 스키마 집계 로그 — 예약 실행은 건별 이벤트 로그로 관측(스케줄러 무변경 원칙).
    logger.info(
        '{"event": "management.scan_summary", "org": "%s", "findings": %d, "delivered": %d}',
        key,
        count,
        summary["delivered"],
    )
    return {"scanned_findings": count, **summary}
```

`logger`가 이 파일에 없으면 상단에 `logger = logging.getLogger("clickme")` + `import logging` 추가.

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_notify_scan_endpoint.py -v`
Expected: PASS (4 tests)

주의: 테스트의 run_scan monkeypatch 대상은 `domain.management.scheduler.run_scan`
(엔드포인트가 함수 내부에서 지연 import하므로 원본 모듈 패치가 유효).

- [ ] **Step 5: 커밋**

```bash
git add backend/api/routers/management.py backend/tests/management/test_notify_scan_endpoint.py
git commit -m "add: 수동 알림 스캔 엔드포인트 — org 잠금·쿨다운·배달 요약"
```

---

### Task 9: 스펙 정합 + 전체 검증

**Files:**
- Modify: `docs/superpowers/specs/2026-07-02-anomaly-remediation-advisor-design.md` (§7-1 한 줄)

- [ ] **Step 1: 스펙 §7-1 예약 실행 집계 문구 조정**

§7-1 마지막 문장 "스케줄 틱도 종료 시 같은 집계를 `management.scan_summary` 로그 1줄로
남긴다"를 다음으로 교체(스케줄러 무변경 원칙과 충돌 — 구현 확정 반영):
```
수동 스캔은 응답+`management.scan_summary` 집계 로그, 예약 실행은 건별 고정 스키마
이벤트 로그(`management.notify_*`)로 관측한다(스케줄러 무변경 원칙 — 틱 종료 훅 없음).
```

- [ ] **Step 2: Ruff + 전체 테스트**

Run: `cd backend && uv run ruff format . && uv run ruff check . --fix`
Expected: 오류 0
Run: `cd backend && uv run pytest tests/ -v`
Expected: 전체 PASS (기존 테스트 회귀 없음)

- [ ] **Step 3: 최종 커밋**

```bash
# ruff가 무관 파일을 재포맷했을 수 있음 — 반드시 git status로 확인 후 이번 작업 파일만 add.
git status
git add docs/superpowers/specs/2026-07-02-anomaly-remediation-advisor-design.md \
  backend/domain/management/remediation/ backend/tests/management/ \
  backend/domain/management/notifications.py backend/api/routers/chat.py \
  backend/api/routers/management.py backend/api/assistant/subagent_tools.py
git commit -m "edit: remediation 스펙 관측 문구 정합 + ruff 정리"
```

- [ ] **Step 4: 수동 검증 (Claude Preview 권장)**

`management_chat_notify_enabled=true` + mock 모드로 백엔드·프론트 기동 후:
1. `POST /api/management/anomaly/notify-scan` 호출(mock 캠페인 중 노출 0인 것이 있어야 함 —
   없으면 mock adapter의 노출 0 캠페인 존재 여부 확인).
2. 프론트 채팅 벨에 "⚠ 캠페인 이상 알림" 세션 배지 확인.
3. 세션 열어 상담 메시지 확인 → "1번 해줘" 입력 → 해당 위젯(sim_form 등) 렌더 확인.
4. 같은 스캔 재호출 → skipped(bell_pending/cooldown) 확인.

---

## 사전 공지 체크리스트 (구현 시작 전)

- [ ] 챗 담당: `subagent_tools.py` 도구 1개 append + `chat.py` 주입 몇 줄 (Task 6·7)
- [ ] 🅰: `notifications.py` `build_notification_sink` 분기 1줄 (Task 5)

## 후속 PR 후보 (이 계획 범위 밖)

- 캠페인→프로젝트 체인 2(생성 제안 링크) — campaign_id↔proposal 연계 저장 위치 확인 후.
- 구경로(`/regenerate*`·규칙표·selection) 사용처 재확인 후 삭제 PR.
- 체크박스 명시 확인 UI(v2) · org 공용 관리 세션(프론트 org-wide 폴링 전환 시).
