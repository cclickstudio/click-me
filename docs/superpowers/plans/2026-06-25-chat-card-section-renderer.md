# 채팅 카드 범용 섹션 렌더러 구현 계획 (스펙 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매니지먼트 챗 한 턴을 도메인 비종속 `ChatCard{sections[]}`로 조립해 `kind:"card"` SSE로 흘리고, 프론트는 섹션 `kind`만 보고 그리는 범용 렌더러로 표시한다(현재 데이터 기준 v0, "답 안 옴" 버그 해소).

**Architecture:** 백엔드 `chat_cards`를 섹션 기반 Pydantic 계약으로 재작성하고, `composer`가 `AskResult`를 섹션으로 normalize(`compose_card`)한 뒤 2단계 SSE(`summary_delta`→`card`→`final`)로 스트리밍(`stream_card`)한다. 프론트는 공유 타입 + 섹션 렌더러 레지스트리(`SECTION_RENDERERS`, 미등록 kind 스킵) + `ChatCardView`로 렌더하고 `(app)/chat/page.tsx`가 `data.kind` 분기를 추가한다. **CLIO(token/done/meta) 경로는 무변경**(핵심 불변식).

**Tech Stack:** Python 3.12 · Pydantic v2(discriminated union) · pytest(`pytest-asyncio`) · uv · ruff / Next.js(TS) · pnpm(lint·build, 프론트 테스트 러너 없음 — 빌드·린트로 검증).

설계 근거 — `docs/superpowers/specs/2026-06-25-chat-card-section-renderer-design.md`.

**커밋 정책** — 각 Task 끝의 커밋은 **권장 체크포인트**다. 한 PR/한 커밋으로 묶어도 무방하나, TDD 단위로 끊으면 회귀 추적이 쉽다.

**교체 blast radius(검증 완료)** — `compose_turn`/`stream_turn`/`TurnEnvelope`/`Card`/`validate_card`/`is_registered` 등 구 심볼을 import하는 곳은 **`api/routers/chat.py`뿐**(18·110·136행). 다른 importer 0건 → 본 계획은 chat.py + 3개 테스트만 손대면 완결. (Task 7에서 재확인.)

**계약 참고(AskResult / SuggestedAction)** — `backend/domain/management/assistant/contracts.py`
- `AskResult(answer, citations: list[Citation], used_tools: list[str], evidence: dict, suggested_action: SuggestedAction|None, requires_approval, thread_id)`.
- `Citation(kind, source, title="")`.
- `SuggestedAction(action_type, target_campaign_id: str|None=None, tier, requires_approval, rationale)` — `target_campaign_id`만 optional, 나머지 required.

---

## Task 1: chat_cards 섹션 계약 재작성

**Files:**
- Modify(재작성): `backend/domain/management/assistant/chat_cards/models.py`
- Modify(재작성): `backend/domain/management/assistant/chat_cards/__init__.py`
- Delete(파일 삭제): `backend/domain/management/assistant/chat_cards/registry.py` (kind/type/version 레지스트리 폐기)
- Test(재작성): `backend/tests/management/test_chat_cards.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/management/test_chat_cards.py` 전체를 아래로 교체:

```python
# 섹션 기반 ChatCard 계약 — discriminated union·기본값·trace allowlist·actions 미직렬화
import pytest
from pydantic import ValidationError

from domain.management.assistant.chat_cards import (
    TRACE_RAW_ALLOWLIST,
    ChatCard,
    MetricItem,
    MetricsSection,
    SummarySection,
    TraceInfo,
    filtered_trace_raw,
)


def test_chatcard_defaults():
    card = ChatCard(sections=[SummarySection(text="요약")])
    assert card.version == 1
    assert card.type == "management"
    assert card.status is None
    assert card.badges == []


def test_section_discriminated_by_kind():
    card = ChatCard(
        sections=[
            SummarySection(text="결론"),
            MetricsSection(items=[MetricItem(label="이번 달 소진", value="29,082원")]),
        ]
    )
    dumped = card.model_dump(mode="json")
    assert dumped["sections"][0]["kind"] == "summary"
    assert dumped["sections"][1]["kind"] == "metrics"
    assert dumped["sections"][1]["items"][0]["value"] == "29,082원"


def test_section_round_trips_by_kind():
    card = ChatCard.model_validate({"sections": [{"kind": "summary", "text": "x"}]})
    assert isinstance(card.sections[0], SummarySection)


def test_unknown_section_kind_rejected():
    with pytest.raises(ValidationError):
        ChatCard.model_validate({"sections": [{"kind": "nope", "text": "x"}]})


def test_actions_not_serialized():
    # 변경 액션 실행 정본은 실행 API — v1 출력에 actions 필드 없음
    card = ChatCard(sections=[SummarySection(text="x")])
    assert "actions" not in card.model_dump(mode="json")


def test_filtered_trace_raw_drops_non_allowlist():
    raw = {"turn_id": "t1", "period": "2026-06", "account_token": "SECRET", "rows": [1, 2, 3]}
    out = filtered_trace_raw(raw)
    assert out == {"turn_id": "t1", "period": "2026-06"}
    assert "account_token" not in TRACE_RAW_ALLOWLIST


def test_trace_info_turn_id_only():
    t = TraceInfo(turn_id="mgmt-s1")
    assert t.turn_id == "mgmt-s1"
    assert t.raw is None
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_chat_cards.py -v`
Expected: FAIL — `ImportError: cannot import name 'ChatCard'`.

- [ ] **Step 3: 모델 재작성**

`backend/domain/management/assistant/chat_cards/models.py` 전체를 아래로 교체:

```python
# 채팅 카드 봉투 — 도메인 비종속 섹션 구조. 프론트 범용 렌더러와 백엔드 composer가 공유하는 계약.
from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

Tone = Literal["neutral", "muted", "success", "warning", "critical"]
CardStatus = Literal["ok", "warning", "critical", "neutral"]

# trace.raw에 담아도 되는 키(스펙 2 대비). 토큰·계정 비밀·대량 row는 영구 제외(루트 규칙).
TRACE_RAW_ALLOWLIST: frozenset[str] = frozenset({"turn_id", "period"})


def filtered_trace_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """allowlist 키만 통과. composer가 trace.raw를 담을 땐 반드시 이 함수만 거친다."""
    return {k: v for k, v in raw.items() if k in TRACE_RAW_ALLOWLIST}


class Badge(BaseModel):
    label: str
    tone: Tone = "neutral"


class MetricItem(BaseModel):
    label: str
    value: str  # 포맷 완료된 표시 문자열 (예 "29,082원")
    hint: str | None = None


class KeyValueItem(BaseModel):
    key: str
    value: str


class Citation(BaseModel):
    kind: str
    source: str
    title: str = ""


class SummarySection(BaseModel):
    kind: Literal["summary"] = "summary"
    title: str | None = None
    text: str


class MetricsSection(BaseModel):
    kind: Literal["metrics"] = "metrics"
    title: str | None = None
    items: list[MetricItem]


class EntitySection(BaseModel):
    kind: Literal["entity"] = "entity"
    title: str | None = None
    items: list[KeyValueItem]


class ProposalSection(BaseModel):
    kind: Literal["proposal"] = "proposal"
    title: str | None = None
    action_type: str
    rationale: str | None = None
    proposal_id: str | None = None


class ReviewSection(BaseModel):
    kind: Literal["review"] = "review"
    title: str | None = None
    decision: str
    rationale: str | None = None


class EvidenceSection(BaseModel):
    kind: Literal["evidence"] = "evidence"
    title: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    used_tools: list[str] = Field(default_factory=list)


class EmptyStateSection(BaseModel):
    kind: Literal["empty_state"] = "empty_state"
    title: str | None = None
    text: str


CardSection = Annotated[
    Union[
        SummarySection,
        MetricsSection,
        EntitySection,
        ProposalSection,
        ReviewSection,
        EvidenceSection,
        EmptyStateSection,
    ],
    Field(discriminator="kind"),
]


class TraceInfo(BaseModel):
    turn_id: str | None = None
    raw: dict[str, Any] | None = None  # v0 미사용 — 담을 땐 filtered_trace_raw만 거친다


class ChatCard(BaseModel):
    version: Literal[1] = 1
    type: Literal["management", "report", "qa", "generic"] = "management"
    title: str | None = None
    status: CardStatus | None = None
    badges: list[Badge] = Field(default_factory=list)
    sections: list[CardSection]
    trace: TraceInfo | None = None
    # actions: v1 미직렬화 — 변경 액션 실행 정본은 실행 API. 모델에 두지 않는다.
```

- [ ] **Step 4: 패키지 API 재작성 + registry.py 삭제**

`backend/domain/management/assistant/chat_cards/__init__.py` 전체를 아래로 교체:

```python
# chat_cards 공개 API — 섹션 기반 ChatCard 계약.
from .models import (
    TRACE_RAW_ALLOWLIST,
    Badge,
    CardSection,
    CardStatus,
    ChatCard,
    Citation,
    EmptyStateSection,
    EntitySection,
    EvidenceSection,
    KeyValueItem,
    MetricItem,
    MetricsSection,
    ProposalSection,
    ReviewSection,
    SummarySection,
    Tone,
    TraceInfo,
    filtered_trace_raw,
)

__all__ = [
    "TRACE_RAW_ALLOWLIST",
    "Badge",
    "CardSection",
    "CardStatus",
    "ChatCard",
    "Citation",
    "EmptyStateSection",
    "EntitySection",
    "EvidenceSection",
    "KeyValueItem",
    "MetricItem",
    "MetricsSection",
    "ProposalSection",
    "ReviewSection",
    "SummarySection",
    "Tone",
    "TraceInfo",
    "filtered_trace_raw",
]
```

그리고 **`backend/domain/management/assistant/chat_cards/registry.py` 파일을 삭제한다**(kind/type/version 레지스트리는 더 이상 쓰지 않음).

- [ ] **Step 5: 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_chat_cards.py -v`
Expected: PASS (7 passed)

- [ ] **Step 6: Ruff + 커밋(권장 체크포인트)**

```bash
(cd backend && uv run ruff format domain/management/assistant/chat_cards tests/management/test_chat_cards.py && uv run ruff check domain/management/assistant/chat_cards tests/management/test_chat_cards.py --fix)
git add backend/domain/management/assistant/chat_cards backend/tests/management/test_chat_cards.py
git commit -m "edit: chat_cards를 섹션 기반 ChatCard 계약으로 재작성"
```

---

## Task 2: composer — compose_card (AskResult → ChatCard)

**Files:**
- Modify(재작성): `backend/domain/management/assistant/composer.py`
- Test(재작성): `backend/tests/management/test_composer.py`

섹션 순서는 **summary → metrics → proposal → review → evidence**, 각 섹션은 데이터 있을 때만. 서술 가드(결론에서 실행 지시 제거)는 유지.

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/management/test_composer.py` 전체를 아래로 교체:

```python
# compose_card: AskResult→ChatCard 섹션 매핑 — 순서·생략·서술 가드·trace
from domain.management.assistant.composer import compose_card
from domain.management.assistant.contracts import AskResult, Citation, SuggestedAction


def _kinds(card):
    return [s.kind for s in card.sections]


def _section(card, kind):
    return next(s for s in card.sections if s.kind == kind)


def _pause(requires_approval=False, tier="TIER_1"):
    return SuggestedAction(
        action_type="PAUSE_CAMPAIGN",
        target_campaign_id="camp_1",
        tier=tier,
        requires_approval=requires_approval,
        rationale="런레이트 초과",
    )


def test_read_only_no_action_has_summary_and_metrics_only():
    res = AskResult(
        answer="예산은 정상 페이스입니다.",
        evidence={"this_month_spent_krw": 29082, "runrate_projection_krw": 34898, "period": "2026-06"},
    )
    card = compose_card(res, turn_id="t1")
    assert card.type == "management"
    assert _kinds(card) == ["summary", "metrics"]
    assert _section(card, "summary").text == "예산은 정상 페이스입니다."
    assert card.trace.turn_id == "t1"


def test_metrics_section_formats_krw_and_period_title():
    res = AskResult(answer="x", evidence={"account_balance_krw": 9, "period": "2026-06"})
    card = compose_card(res, turn_id="t1")
    metrics = _section(card, "metrics")
    assert metrics.title == "핵심 지표 (2026-06)"
    assert metrics.items[0].value == "9원"


def test_empty_evidence_omits_metrics():
    card = compose_card(AskResult(answer="x", evidence={}), turn_id="t1")
    assert "metrics" not in _kinds(card)


def test_action_builds_proposal_review_in_order():
    res = AskResult(
        answer="일시중지를 제안합니다.",
        citations=[Citation(kind="live", source="live_budget")],
        suggested_action=_pause(),
    )
    card = compose_card(res, turn_id="t2")
    assert _kinds(card) == ["summary", "proposal", "review", "evidence"]
    assert _section(card, "proposal").action_type == "PAUSE_CAMPAIGN"


def test_review_decision_reflects_requires_approval():
    auto = compose_card(AskResult(answer="x", suggested_action=_pause(requires_approval=False)), turn_id="t3")
    needs = compose_card(AskResult(answer="x", suggested_action=_pause(requires_approval=True, tier="TIER_3")), turn_id="t4")
    assert _section(auto, "review").decision == "auto_ok"
    assert _section(needs, "review").decision == "needs_approval"


def test_badges_present_for_action():
    card = compose_card(AskResult(answer="x", suggested_action=_pause()), turn_id="t5")
    assert {b.label for b in card.badges} == {"TIER_1", "draft", "auto_ok"}


def test_no_badges_for_read_only():
    card = compose_card(AskResult(answer="x"), turn_id="t6")
    assert card.badges == []


def test_conclusion_strips_execution_directive():
    res = AskResult(answer="예산이 초과됐습니다. 지금 실행하세요.", suggested_action=_pause())
    card = compose_card(res, turn_id="t7")
    text = next(s for s in card.sections if s.kind == "summary").text
    assert "실행하세요" not in text
    assert "예산이 초과됐습니다." in text


def test_evidence_section_carries_citations_and_tools():
    res = AskResult(
        answer="x",
        citations=[Citation(kind="kb", source="meta_ad_policy.md", title="Meta 정책")],
        used_tools=["live_budget"],
    )
    card = compose_card(res, turn_id="t8")
    ev = next(s for s in card.sections if s.kind == "evidence")
    assert ev.citations[0].source == "meta_ad_policy.md"
    assert ev.used_tools == ["live_budget"]
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_composer.py -v`
Expected: FAIL — `ImportError: cannot import name 'compose_card'`.

- [ ] **Step 3: composer 재작성**

`backend/domain/management/assistant/composer.py` 전체를 아래로 교체:

```python
# Composer — AskResult를 도메인 비종속 ChatCard(섹션)로 normalize한다. 서술 가드는 여기서 강제.
from __future__ import annotations

import json
import re
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from .chat_cards import (
    Badge,
    ChatCard,
    Citation,
    EvidenceSection,
    MetricItem,
    MetricsSection,
    ProposalSection,
    ReviewSection,
    SummarySection,
    TraceInfo,
)

if TYPE_CHECKING:
    from .chat_cards import CardSection
    from .contracts import AskResult, SuggestedAction

# 결론에서 제거할 실행 지시 마커. 행동 가능한 주장은 카드(proposal)로.
_DIRECTIVE_MARKERS = (
    "실행하세요",
    "실행하면 됩니다",
    "지금 실행",
    "바로 실행",
    "바로 적용",
    "집행하세요",
    "눌러서 실행",
)
_NEUTRAL_CONCLUSION = "자세한 내용은 아래 카드를 확인하세요."

# evidence dict 숫자 → 표시 라벨(KRW). 없는 키는 건너뛴다.
_METRIC_LABELS: tuple[tuple[str, str], ...] = (
    ("this_month_spent_krw", "이번 달 소진"),
    ("runrate_projection_krw", "월말 예상"),
    ("account_balance_krw", "계정 잔액"),
)


def _descriptive_conclusion(answer: str) -> str:
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", answer.strip()) if s]
    kept = [s for s in sentences if not any(m in s for m in _DIRECTIVE_MARKERS)]
    return " ".join(kept).strip() or _NEUTRAL_CONCLUSION


def _won(value: object) -> str:
    return f"{int(value):,}원"


def _metrics_section(evidence: dict) -> MetricsSection | None:
    items = [
        MetricItem(label=label, value=_won(evidence[key]))
        for key, label in _METRIC_LABELS
        if isinstance(evidence.get(key), (int, float))
    ]
    if not items:
        return None
    period = evidence.get("period")
    return MetricsSection(title=f"핵심 지표 ({period})" if period else "핵심 지표", items=items)


def _proposal_section(sa: SuggestedAction) -> ProposalSection:
    return ProposalSection(title="제안", action_type=sa.action_type, rationale=sa.rationale)


def _review_section(sa: SuggestedAction) -> ReviewSection:
    decision = "needs_approval" if sa.requires_approval else "auto_ok"
    return ReviewSection(title="검수", decision=decision, rationale=sa.rationale)


def _evidence_section(res: AskResult) -> EvidenceSection | None:
    if not res.citations and not res.used_tools:
        return None
    return EvidenceSection(
        title="근거",
        citations=[Citation(kind=c.kind, source=c.source, title=c.title) for c in res.citations],
        used_tools=list(res.used_tools),
    )


def _badges(sa: SuggestedAction | None) -> list[Badge]:
    if sa is None:
        return []
    decision = "needs_approval" if sa.requires_approval else "auto_ok"
    return [
        Badge(label=sa.tier, tone="neutral"),
        Badge(label="draft", tone="muted"),
        Badge(label=decision, tone="success" if decision == "auto_ok" else "warning"),
    ]


def compose_card(res: AskResult, *, turn_id: str) -> ChatCard:
    """AskResult를 ChatCard로. 섹션 순서 summary→metrics→proposal→review→evidence, 없으면 생략."""
    sections: list[CardSection] = [
        SummarySection(title="결론", text=_descriptive_conclusion(res.answer))
    ]

    metrics = _metrics_section(res.evidence or {})
    if metrics is not None:
        sections.append(metrics)

    sa = res.suggested_action
    if sa is not None:
        sections.append(_proposal_section(sa))
        sections.append(_review_section(sa))

    evidence = _evidence_section(res)
    if evidence is not None:
        sections.append(evidence)

    return ChatCard(
        type="management",
        badges=_badges(sa),
        sections=sections,
        trace=TraceInfo(turn_id=turn_id),  # v0 — raw 미전송
    )


# SSE 한 줄 직렬화 — 와이어 포맷 단일 출처(라우터 오류 경로도 재사용).
def format_sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _chunks(text: str, size: int = 24) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def _summary_text(card: ChatCard) -> str:
    for section in card.sections:
        if section.kind == "summary":
            return section.text
    return ""


async def stream_card(card: ChatCard) -> AsyncGenerator[str, None]:
    """ChatCard를 2단계 SSE로 — summary 텍스트 스트리밍 → card → final(항상)."""
    for piece in _chunks(_summary_text(card)):
        yield format_sse({"kind": "summary_delta", "text": piece})
    yield format_sse({"kind": "card", "payload": card.model_dump(mode="json")})
    turn_id = card.trace.turn_id if card.trace else None
    yield format_sse({"kind": "final", "turn_id": turn_id, "status": "ok"})
```

> `stream_card`는 Task 3에서 테스트한다. Task 2는 `compose_card`만 검증.

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_composer.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Ruff + 커밋(권장 체크포인트)**

```bash
(cd backend && uv run ruff format domain/management/assistant/composer.py tests/management/test_composer.py && uv run ruff check domain/management/assistant/composer.py tests/management/test_composer.py --fix)
git add backend/domain/management/assistant/composer.py backend/tests/management/test_composer.py
git commit -m "edit: composer를 compose_card(AskResult→ChatCard 섹션)로 재작성"
```

---

## Task 3: stream_card SSE + 라우터 헬퍼 재작성

**Files:**
- Modify: `backend/api/routers/chat.py` (import + `_management_card_stream`)
- Test(재작성): `backend/tests/management/test_chat_sse.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/management/test_chat_sse.py` 전체를 아래로 교체:

```python
# stream_card SSE 시퀀스 + 주입형 _management_card_stream(앱·DB 없이)
import json

import pytest

from domain.management.assistant.composer import compose_card, stream_card
from domain.management.assistant.contracts import AskResult, Citation, SuggestedAction


def _parse(lines: list[str]) -> list[dict]:
    out = []
    for ln in lines:
        assert ln.startswith("data: ") and ln.endswith("\n\n")
        out.append(json.loads(ln[len("data: ") :].strip()))
    return out


async def _collect_stream(card) -> list[dict]:
    return _parse([chunk async for chunk in stream_card(card)])


@pytest.mark.asyncio
async def test_sequence_summary_then_card_then_final():
    res = AskResult(
        answer="일시중지를 제안합니다.",
        citations=[Citation(kind="live", source="live_budget")],
        suggested_action=SuggestedAction(
            action_type="PAUSE_CAMPAIGN",
            target_campaign_id="camp_1",
            tier="TIER_1",
            requires_approval=False,
            rationale="r",
        ),
    )
    card = compose_card(res, turn_id="t1")
    events = await _collect_stream(card)
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "summary_delta"
    assert "card" in kinds
    assert kinds[-1] == "final"
    assert events[-1]["status"] == "ok"
    assert events[-1]["turn_id"] == "t1"


@pytest.mark.asyncio
async def test_summary_delta_reassembles():
    card = compose_card(AskResult(answer="a" * 60), turn_id="t2")  # 지시 마커 없음 → 원문 보존
    events = await _collect_stream(card)
    text = "".join(e["text"] for e in events if e["kind"] == "summary_delta")
    assert text == "a" * 60


@pytest.mark.asyncio
async def test_card_event_carries_sections():
    card = compose_card(AskResult(answer="정상입니다.", evidence={"this_month_spent_krw": 100}), turn_id="t3")
    events = await _collect_stream(card)
    card_event = next(e for e in events if e["kind"] == "card")
    assert [s["kind"] for s in card_event["payload"]["sections"]] == ["summary", "metrics"]


@pytest.mark.asyncio
async def test_management_card_stream_happy_path():
    from api.routers.chat import _management_card_stream

    async def fake_assistant(req):
        assert req.question == "예산?"
        return AskResult(answer="예산은 정상입니다.", citations=[Citation(kind="live", source="live_budget")])

    recorded = []

    async def fake_record(**kw):
        recorded.append(kw)

    chunks = [
        c
        async for c in _management_card_stream(
            question="예산?", session_id="s1", ad_id=None, assistant=fake_assistant, record=fake_record
        )
    ]
    events = _parse(chunks)
    assert events[0]["kind"] == "summary_delta"
    assert events[-1]["kind"] == "final" and events[-1]["status"] == "ok"
    assert recorded and recorded[0]["thread_id"] == "mgmt-s1"


@pytest.mark.asyncio
async def test_management_card_stream_failure_emits_safe_error_then_final_failed():
    from api.routers.chat import _management_card_stream

    async def boom(req):
        raise RuntimeError("assistant down: SECRET_TOKEN=abc")

    async def fake_record(**kw):
        pass

    chunks = [
        c
        async for c in _management_card_stream(
            question="예산?", session_id="s1", ad_id=None, assistant=boom, record=fake_record
        )
    ]
    events = _parse(chunks)
    err = next(e for e in events if e["kind"] == "error")
    assert err["scope"] == "turn"
    assert "SECRET_TOKEN" not in err["message"]  # raw exception 미노출
    assert events[-1]["kind"] == "final" and events[-1]["status"] == "failed"


@pytest.mark.asyncio
async def test_management_card_stream_record_failure_is_best_effort():
    from api.routers.chat import _management_card_stream

    async def fake_assistant(req):
        return AskResult(answer="예산은 정상입니다.")

    async def boom_record(**kw):
        raise RuntimeError("db down")

    chunks = [
        c
        async for c in _management_card_stream(
            question="예산?", session_id="s1", ad_id=None, assistant=fake_assistant, record=boom_record
        )
    ]
    events = _parse(chunks)
    assert events[-1]["kind"] == "final" and events[-1]["status"] == "ok"
    assert not any(e["kind"] == "error" for e in events)
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_chat_sse.py -v`
Expected: FAIL — `_management_card_stream`이 아직 구(`compose_turn`/`stream_turn`·`event` 키) 사용.

- [ ] **Step 3: chat.py import 교체**

`backend/api/routers/chat.py`의 import 한 줄을 교체.

기존:
```python
from domain.management.assistant.composer import compose_turn, format_sse, stream_turn
```
교체:
```python
from domain.management.assistant.composer import compose_card, format_sse, stream_card
```

- [ ] **Step 4: `_management_card_stream` 재작성**

`backend/api/routers/chat.py`의 `_management_card_stream` 함수 전체(현재 `compose_turn`/`stream_turn`·`event` 키 사용)를 아래로 교체:

```python
async def _management_card_stream(
    *,
    question: str,
    session_id: str,
    ad_id: str | None,
    assistant: Callable[[AskRequest], Awaitable[AskResult]],
    record: Callable[..., Awaitable[None]],
) -> AsyncGenerator[str, None]:
    # 매니지먼트 한 턴을 카드 SSE로. assistant/record 주입 → 앱·DB 없이 테스트 가능.
    thread_id = f"mgmt-{session_id}"

    # 1) 어시스턴트 호출 + 카드 조립 — 실패하면 안전 문구 error + final(failed). raw exception 미노출.
    try:
        t0 = time.perf_counter()
        result = await assistant(AskRequest(question=question, ad_id=ad_id, thread_id=thread_id))
        latency_ms = int((time.perf_counter() - t0) * 1000)
        card = compose_card(result, turn_id=thread_id)
    except Exception as exc:  # noqa: BLE001 — 턴 실패. 상세는 로그로만.
        print(f"[chat] management turn failed: {exc!r}")
        yield format_sse(
            {"kind": "error", "scope": "turn", "message": "매니지먼트 조회 중 문제가 발생했어요."}
        )
        yield format_sse({"kind": "final", "turn_id": thread_id, "status": "failed"})
        return

    # 2) 관측 적재는 best-effort — 실패해도 답변 스트림은 그대로.
    try:
        await record(
            thread_id=thread_id,
            result=result,
            question=question,
            ad_id=ad_id,
            latency_ms=latency_ms,
        )
    except Exception as exc:  # noqa: BLE001 — 적재 실패는 채팅을 끊지 않는다
        print(f"[chat] record_turn failed (best-effort, ignored): {exc!r}")

    # 3) 정상 답변 스트리밍.
    async for chunk in stream_card(card):
        yield chunk
```

- [ ] **Step 5: 통과 확인 + 회귀**

Run: `cd backend && uv run pytest tests/management/test_chat_sse.py -v`
Expected: PASS (6 passed)

Run: `cd backend && uv run pytest tests/management/ -v`
Expected: 전체 PASS(어시스턴트 계약·툴 무변경).

- [ ] **Step 6: Ruff + 커밋(권장 체크포인트)**

```bash
(cd backend && uv run ruff format api/routers/chat.py tests/management/test_chat_sse.py && uv run ruff check api/routers/chat.py tests/management/test_chat_sse.py --fix)
git add backend/api/routers/chat.py backend/tests/management/test_chat_sse.py
git commit -m "edit: 매니지먼트 카드 스트림을 kind:card SSE + 안전 error 문구로 재작성"
```

---

## Task 4: 프론트 공유 타입 — chatCard.ts

**Files:**
- Create: `frontend/src/lib/chatCard.ts`

- [ ] **Step 1: 타입 + 가드 작성**

`frontend/src/lib/chatCard.ts` 생성:

```ts
// 채팅 카드 공유 타입 — 백엔드 ChatCard 계약과 1:1. 프론트는 섹션 kind만 보고 렌더한다.
export type Tone = 'neutral' | 'muted' | 'success' | 'warning' | 'critical';
export type CardStatus = 'ok' | 'warning' | 'critical' | 'neutral';

export type Badge = { label: string; tone: Tone };
export type MetricItem = { label: string; value: string; hint?: string };
export type KeyValueItem = { key: string; value: string };
export type Citation = { kind: string; source: string; title?: string };
export type TraceInfo = { turn_id?: string; raw?: Record<string, unknown> };

export type CardSection =
  | { kind: 'summary'; title?: string; text: string }
  | { kind: 'metrics'; title?: string; items: MetricItem[] }
  | { kind: 'entity'; title?: string; items: KeyValueItem[] }
  | { kind: 'proposal'; title?: string; action_type: string; rationale?: string; proposal_id?: string }
  | { kind: 'review'; title?: string; decision: string; rationale?: string }
  | { kind: 'evidence'; title?: string; citations?: Citation[]; used_tools?: string[] }
  | { kind: 'empty_state'; title?: string; text: string };

export type ChatCard = {
  version: 1;
  type: 'management' | 'report' | 'qa' | 'generic';
  title?: string;
  status?: CardStatus;
  badges?: Badge[];
  sections: CardSection[];
  trace?: TraceInfo;
};

// SSE 이벤트(카드 프로토콜) — data.kind로 분기.
export type CardEvent =
  | { kind: 'summary_delta'; text: string }
  | { kind: 'card'; payload: ChatCard }
  | { kind: 'final'; turn_id?: string; status: 'ok' | 'partial' | 'failed' }
  | { kind: 'error'; scope?: string; message: string };

const CARD_EVENT_KINDS = new Set(['summary_delta', 'card', 'final', 'error']);

export function isCardEvent(data: unknown): data is CardEvent {
  if (typeof data !== 'object' || data === null || !('kind' in data)) return false;
  const kind = (data as { kind: unknown }).kind;
  return typeof kind === 'string' && CARD_EVENT_KINDS.has(kind);
}
```

- [ ] **Step 2: 린트 확인**

Run: `cd frontend && pnpm lint`
Expected: 통과(에러 0).

- [ ] **Step 3: 커밋(권장)**

```bash
git add frontend/src/lib/chatCard.ts
git commit -m "add: 채팅 카드 공유 타입(ChatCard·CardSection·CardEvent)"
```

---

## Task 5: 프론트 섹션 렌더러 레지스트리 + ChatCardView

**Files:**
- Create: `frontend/src/components/chat/sections.tsx` (섹션 kind → 렌더러 레지스트리)
- Create: `frontend/src/components/chat/ChatCardView.tsx`

- [ ] **Step 1: 섹션 레지스트리 작성**

`frontend/src/components/chat/sections.tsx` 생성:

```tsx
// 섹션 렌더러 레지스트리 — kind → 렌더러. 새 섹션 추가 = 여기 한 줄 등록(스펙 §5.1).
import type { ReactNode } from 'react';
import type { CardSection } from '@/lib/chatCard';

type Renderer<K extends CardSection['kind']> = (s: Extract<CardSection, { kind: K }>) => ReactNode;
type Registry = { [K in CardSection['kind']]?: Renderer<K> };

function Title({ title }: { title?: string }) {
  if (!title) return null;
  return <p className="text-[11px] font-semibold text-[#8B95A1] dark:text-[#6B7280] mb-1">{title}</p>;
}

export const SECTION_RENDERERS: Registry = {
  summary: (s) => (
    <div>
      <Title title={s.title} />
      <p className="text-sm leading-relaxed text-[#191F28] dark:text-[#F2F4F6] whitespace-pre-wrap">{s.text}</p>
    </div>
  ),
  metrics: (s) => (
    <div>
      <Title title={s.title} />
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {s.items.map((m, i) => (
          <span key={i} className="text-sm text-[#4E5968] dark:text-[#9CA3AF]">
            {m.label} <b className="text-[#191F28] dark:text-[#F2F4F6]">{m.value}</b>
          </span>
        ))}
      </div>
    </div>
  ),
  entity: (s) => (
    <div>
      <Title title={s.title} />
      {s.items.map((kv, i) => (
        <p key={i} className="text-sm text-[#4E5968] dark:text-[#9CA3AF]">
          {kv.key} · {kv.value}
        </p>
      ))}
    </div>
  ),
  proposal: (s) => (
    <div>
      <Title title={s.title} />
      <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">{s.action_type}</p>
      {s.rationale && <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-0.5">근거: {s.rationale}</p>}
    </div>
  ),
  review: (s) => (
    <div>
      <Title title={s.title} />
      <p className="text-sm text-[#4E5968] dark:text-[#9CA3AF]">{s.decision}</p>
      {s.rationale && <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-0.5">{s.rationale}</p>}
    </div>
  ),
  evidence: (s) => {
    // 모든 근거를 표시 — live 인용/툴은 "실측·", kb 인용은 title||source. 중복 제거.
    const tools = (s.used_tools ?? []).map((t) => t.replace('live_', '실측·'));
    const cites = (s.citations ?? []).map((c) =>
      c.kind === 'kb' ? c.title || c.source : c.source.replace('live_', '실측·'),
    );
    const all = [...new Set([...tools, ...cites])];
    if (all.length === 0) return null;
    return <p className="text-[11px] text-[#B0B8C1] dark:text-[#6B7280]">근거: {all.join(' · ')}</p>;
  },
  empty_state: (s) => (
    <div>
      <Title title={s.title} />
      <p className="text-sm text-[#8B95A1] dark:text-[#6B7280]">{s.text}</p>
    </div>
  ),
};
```

- [ ] **Step 2: ChatCardView 작성**

`frontend/src/components/chat/ChatCardView.tsx` 생성:

```tsx
// 범용 카드 렌더러 — 레지스트리로 섹션 위임. 미등록 kind는 스킵(전방호환) + dev 로그.
import type { ReactNode } from 'react';
import type { CardSection, ChatCard, Tone } from '@/lib/chatCard';
import { SECTION_RENDERERS } from './sections';

const TONE_CLASS: Record<Tone, string> = {
  neutral: 'bg-[#F2F4F6] text-[#4E5968] dark:bg-[#2D3748] dark:text-[#9CA3AF]',
  muted: 'bg-[#F9FAFB] text-[#8B95A1] dark:bg-[#1C2333] dark:text-[#6B7280]',
  success: 'bg-[#E7F4EC] text-[#15803D] dark:bg-[#14321F] dark:text-[#86EFAC]',
  warning: 'bg-[#FEF3C7] text-[#B45309] dark:bg-[#3B2F0B] dark:text-[#FCD34D]',
  critical: 'bg-[#FEE2E2] text-[#B91C1C] dark:bg-[#3B1212] dark:text-[#FCA5A5]',
};

function renderSection(section: CardSection): ReactNode {
  const renderer = SECTION_RENDERERS[section.kind] as ((s: CardSection) => ReactNode) | undefined;
  if (!renderer) {
    // 미등록 섹션 kind — 렌더 스킵(전방호환). dev에서만 로깅.
    if (process.env.NODE_ENV !== 'production') {
      console.debug('[chat] unknown card section kind:', section.kind);
    }
    return null;
  }
  return renderer(section);
}

export default function ChatCardView({ card }: { card: ChatCard }) {
  const hasHeader = Boolean(card.title) || (card.badges?.length ?? 0) > 0;
  return (
    <div className="flex flex-col gap-3 px-4 py-3 rounded-xl bg-[#F2F4F6] dark:bg-[#252D3D] max-w-sm">
      {hasHeader && (
        <div className="flex flex-wrap items-center gap-1.5">
          {card.title && <span className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6]">{card.title}</span>}
          {card.badges?.map((b, i) => (
            <span key={i} className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${TONE_CLASS[b.tone]}`}>
              {b.label}
            </span>
          ))}
        </div>
      )}
      {card.sections.map((s, i) => (
        <div key={i}>{renderSection(s)}</div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: 린트 확인**

Run: `cd frontend && pnpm lint`
Expected: 통과(에러 0).

- [ ] **Step 4: 커밋(권장)**

```bash
git add frontend/src/components/chat/sections.tsx frontend/src/components/chat/ChatCardView.tsx
git commit -m "add: 섹션 렌더러 레지스트리 + 범용 ChatCardView"
```

---

## Task 6: 프론트 SSE 배선 — chat/page.tsx

**Files:**
- Modify: `frontend/src/app/(app)/chat/page.tsx`

- [ ] **Step 1: import + Message 타입에 card 추가**

상단 import에 추가:
```tsx
import ChatCardView from '@/components/chat/ChatCardView';
import { isCardEvent, type ChatCard } from '@/lib/chatCard';
```

`Message` 타입에 `card?: ChatCard` 추가:
```tsx
type Message = {
  role: 'user' | 'assistant';
  content: string;
  meta?: SourceMeta;
  card?: ChatCard;
};
```

- [ ] **Step 2: 빈 placeholder 스킵 조건 보강**

`page.tsx` 메시지 렌더 초입의 placeholder 스킵 라인을 교체(카드만 있고 본문 빈 경우 카드가 사라지지 않게):

기존:
```tsx
                if (msg.role === 'assistant' && msg.content === '') return null;
```
교체:
```tsx
                if (msg.role === 'assistant' && msg.content === '' && !msg.card) return null;
```

- [ ] **Step 3: SSE 루프에 kind 분기 추가**

`page.tsx`의 SSE 파싱 `try { const data = JSON.parse(raw) as {...}; if (data.done) ... } catch` 블록을 아래로 교체:

```tsx
          try {
            const data = JSON.parse(raw);

            // 카드 프로토콜(매니지먼트) — isCardEvent로 분기. 아니면 CLIO(token/done/meta).
            if (isCardEvent(data)) {
              if (data.kind === 'summary_delta') {
                setMessages((prev) => {
                  const last = prev[prev.length - 1];
                  return [...prev.slice(0, -1), { ...last, content: last.content + data.text }];
                });
              } else if (data.kind === 'card') {
                setMessages((prev) => {
                  const last = prev[prev.length - 1];
                  return [...prev.slice(0, -1), { ...last, card: data.payload }];
                });
              } else if (data.kind === 'error') {
                setMessages((prev) => {
                  const last = prev[prev.length - 1];
                  return [...prev.slice(0, -1), { ...last, content: data.message }];
                });
              } else if (data.kind === 'final') {
                setIsStreaming(false);
              }
              continue;
            }

            // CLIO 경로(기존) — token/done/meta
            if (data.done) {
              setIsStreaming(false);
            } else if (data.meta) {
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                return [...prev.slice(0, -1), { ...last, meta: data.meta as SourceMeta }];
              });
            } else if (data.token) {
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                return [...prev.slice(0, -1), { ...last, content: last.content + String(data.token) }];
              });
            }
          } catch {
            // ignore malformed SSE line
          }
```

> `for (const line of lines)` 루프 안이라 `continue`가 다음 SSE 라인으로 넘어간다. 환경상 루프 구조가 다르면 `continue` 대신 `else` 분기로 감싼다.

- [ ] **Step 4: 메시지 렌더에 카드 분기 추가**

assistant 본문 버블을 교체(카드가 있으면 ChatCardView, 없으면 기존 버블).

기존:
```tsx
                      <div
                        className={`px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
                          msg.role === 'user'
                            ? 'bg-[#3182F6] text-white rounded-br-md'
                            : 'bg-[#F2F4F6] dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] rounded-bl-md'
                        }`}
                      >
                        {msg.content}
                      </div>
```
교체:
```tsx
                      {msg.role === 'assistant' && msg.card ? (
                        <ChatCardView card={msg.card} />
                      ) : (
                        <div
                          className={`px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
                            msg.role === 'user'
                              ? 'bg-[#3182F6] text-white rounded-br-md'
                              : 'bg-[#F2F4F6] dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] rounded-bl-md'
                          }`}
                        >
                          {msg.content}
                        </div>
                      )}
```

- [ ] **Step 5: 빌드·린트 확인**

Run: `cd frontend && pnpm lint && pnpm build`
Expected: 린트 0 에러, 빌드 성공(타입 에러 0).

- [ ] **Step 6: 커밋(권장)**

```bash
git add "frontend/src/app/(app)/chat/page.tsx"
git commit -m "edit: 챗 페이지에 카드 SSE(kind:card) 분기·ChatCardView 렌더 배선"
```

---

## Task 7: 엔드투엔드 확인

**Files:** 없음(검증만).

- [ ] **Step 1: 교체 완결 확인(rg)**

Run: `rg -n "card_ready|conclusion_delta|actionbar" frontend/src ; echo "---"; rg -n "compose_turn|stream_turn|TurnEnvelope" backend/api backend/domain`
Expected: 프론트 0건(구 카드 포맷 소비자 없음 — `result`/`evidence`는 일반어라 제외, SSE 카드 문맥에서만 의미). 백엔드 0건(composer 교체로 구 심볼 사라짐).

- [ ] **Step 2: 백엔드 전체 회귀 + Ruff**

Run: `cd backend && uv run pytest tests/management/ tests/orchestration/ -v`
Expected: 전부 PASS.

Run: `cd backend && uv run ruff check .`
Expected: `All checks passed!`

- [ ] **Step 3: 서버·프론트 기동 후 확인**

Run(백엔드): `cd backend && uv run uvicorn api.main:app --reload --port 8000`
Run(프론트): `cd frontend && pnpm dev`

확인:
- 매니지먼트 질문("이번 캠페인 예산 소진 어때?") → **카드**(결론 + 핵심 지표) 렌더, 스피너 정상 종료. **배지는 제안(suggested_action)이 있는 응답에만 표시**(읽기 전용/정상이면 배지 없음 — 정직).
- 일반 질문("마케팅 카피 팁 알려줘") → **CLIO 토큰** 스트리밍(무변경).
- (선택) 어시스턴트 강제 실패 시 카드 자리에 안전 문구, 무한 스피너 없음.

---

## Self-Review (요약)

- **Spec 커버리지** — §3 계약(T1) · §4 SSE·안전 error(T2·T3) · §5.1 레지스트리·미등록 스킵·dev 로그(T5) · §5.1 card 없이 final 시 error 본문(T6) · §5.2 v0 매핑·trace turn_id만(T2) · §8 테스트(T1·T2·T3). partial은 v0 미발생이라 ok/failed만 검증.
- **타입 일관성** — `compose_card(res,*,turn_id)`·`stream_card(card)`·`format_sse`·`filtered_trace_raw`·`_management_card_stream(*,question,session_id,ad_id,assistant,record)` 전 Task 동일. 프론트 `ChatCard`/`CardSection`/`CardEvent`(T4) ↔ 백엔드 Pydantic(T1) 필드명 일치.
- **플레이스홀더 없음. DRY** — `format_sse` 단일 출처, 서술 가드·KRW 포맷 composer 한 곳.
```
