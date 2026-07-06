# Task 2: 두뇌 — `remediation/advisor.py`

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-02-anomaly-remediation-advisor.md` · 스펙: `docs/superpowers/specs/2026-07-02-anomaly-remediation-advisor-design.md`
> **실행 규칙**: 모든 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 .py 첫 줄 한국어 헤더 주석 · 🅰 소유 파일(detection/, approval.py, agents/diagnosis*) 수정 금지(읽기만).
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.

---

**Files:**
- Create: `backend/domain/management/remediation/advisor.py`
- Test: `test/backend/management/test_remediation_advisor.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`test/backend/management/test_remediation_advisor.py`:
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


@pytest.mark.asyncio
async def test_options_block_survives_llm_polish(monkeypatch):
    # LLM이 인트로를 어떻게 바꿔놔도 옵션 블록은 결정론 렌더러가 항상 붙는다(구조 보증)
    from domain.management.remediation import advisor as adv

    async def rogue_polish(settings, intro):
        return "완전히 다른 텍스트"

    monkeypatch.setattr(adv, "_polish", rogue_polish)
    res = await consult(_Settings(), "camp_1", reader=FakeReader(impressions=0))
    assert "완전히 다른 텍스트" in res.message
    assert "①" in res.message and "번호로 답해 주세요" in res.message


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

Run: `cd backend && uv run pytest ../test/backend/management/test_remediation_advisor.py -v`
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


def _render_intro(name: str, anomaly_type: str) -> str:
    """상황 설명 문단 — LLM이 다듬을 수 있는 유일한 부분."""
    hypothesis = _HYPOTHESIS.get(anomaly_type, "성과 이상이 감지됐어요.")
    return f"**{name}** 캠페인에 이상이 감지됐어요.\n{hypothesis}"


def _render_options(options: list[RemediationOption]) -> str:
    """옵션 블록은 항상 결정론 렌더링 — LLM이 절대 만지지 않는다(구조 보증)."""
    lines = [
        f"{_CIRCLED[o.index - 1] if o.index <= len(_CIRCLED) else o.index} {o.label}"
        for o in options
    ]
    return "어떻게 하실래요?\n" + "\n".join(lines) + "\n\n번호로 답해 주세요."


async def _polish(settings: Any, intro: str) -> str:
    """상황 설명 문단만 LLM으로 다듬는다(옵션 블록은 입력에 없음). 실패 시 intro 그대로."""
    api_key = getattr(settings, "openai_api_key", None)
    if not api_key:
        return intro
    try:
        from langchain_openai import ChatOpenAI  # noqa: PLC0415 — 키 없는 환경 보호

        llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.3)
        resp = await llm.ainvoke(
            [
                (
                    "system",
                    "광고 운영 어시스턴트의 상황 설명 문단을 자연스럽게 다듬어라. "
                    "사실·수치를 추가하거나 빼지 말 것. 한국어, 2문장 이내.",
                ),
                ("human", intro),
            ],
            config={"run_name": "management:consult_polish", "tags": ["management"]},
        )
        text = resp.content if isinstance(resp.content, str) else ""
        return text or intro
    except Exception:  # noqa: BLE001 — LLM 실패는 결정론 문구 폴백
        return intro


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
    # LLM은 인트로만 — 옵션 블록은 항상 결정론으로 이어붙인다(구조 보증).
    intro = await _polish(settings, _render_intro(name, anomaly_type))
    message = f"{intro}\n\n{_render_options(options)}"
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

Run: `cd backend && uv run pytest ../test/backend/management/test_remediation_advisor.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: 커밋**

```bash
git add backend/domain/management/remediation/advisor.py test/backend/management/test_remediation_advisor.py
git commit -m "add: remediation advisor — 실측 재검증·옵션 풀·결정론 문구(LLM 폴백)"
```
