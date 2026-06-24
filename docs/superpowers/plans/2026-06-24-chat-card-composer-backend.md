# 채팅 카드 + Composer 백엔드 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매니지먼트 어시스턴트의 한 턴 응답을 "결론 + 타입이 붙은 카드 리스트(evidence/result/review/actionbar)"로 구조화하고, Composer가 조립한 카드를 2단계 SSE(`conclusion_delta` → `card_ready` → `final`)로 스트리밍한다.

**Architecture:** 순수 계약 모듈(`chat_cards`)이 카드 봉투 모델과 `(kind, type, version)` 레지스트리를 정의한다. `composer.py`가 기존 `AskResult`를 카드 봉투(`TurnEnvelope`)로 매핑하고(결론은 서술 가드 통과), `stream_turn`이 고정 슬롯 순서(actionbar 항상 마지막)로 SSE 이벤트를 생성한다. 라우터는 의존성 주입된 `_management_card_stream`으로 분리해 앱·DB 없이 테스트한다. 능동 제안·영속·실행 API·프론트는 후속 plan.

**Tech Stack:** Python 3.12 · FastAPI(StreamingResponse) · Pydantic v2 · pytest(`pytest-asyncio`) · uv.

설계 근거 문서 — `docs/superpowers/specs/2026-06-24-chat-card-composer-design.md` (§4 데이터 계약 · §5 SSE · §6 불변식).

**MVP 경계(중요)** — 실행 API·proposal 영속이 아직 없으므로 **actionbar의 변경(mutating) 액션은 비활성**(`enabled=False, wired=False`)으로 내보내고 `proposal_draft`만 싣는다. 실제 승인·실행 배선은 후속 plan 2에서. 이로써 불변식 ①(실행 권한 정본=실행 API)을 MVP에서도 위반하지 않는다.

---

## File Structure

| 파일 | 책임 | 생성/수정 |
|---|---|---|
| `backend/domain/management/assistant/chat_cards/__init__.py` | 패키지 공개 API 재노출 | 생성 |
| `backend/domain/management/assistant/chat_cards/models.py` | 카드 봉투 모델(`CardKind`·`CardStatus`·`Card`·`CardPayload`·`TurnEnvelope`·`TurnOrigin`) | 생성 |
| `backend/domain/management/assistant/chat_cards/registry.py` | `(kind, type, version)` 레지스트리 + 검증 | 생성 |
| `backend/domain/management/assistant/composer.py` | `compose_turn`(AskResult→봉투) · `stream_turn`(SSE) · 서술 가드 | 생성 |
| `backend/api/routers/chat.py` | 매니지먼트 분기를 주입형 `_management_card_stream`으로 교체 | 수정 |
| `backend/tests/management/test_chat_cards.py` | 레지스트리·모델·AST 순수성 | 생성 |
| `backend/tests/management/test_composer.py` | 매핑·서술 가드·actionbar 비활성·슬롯 순서 | 생성 |
| `backend/tests/management/test_chat_sse.py` | `stream_turn` 시퀀스 + 주입형 라우터 헬퍼 | 생성 |

`chat_cards`는 **management 내부를 import하지 않는다**(순수). Task 1에서 AST로 강제한다.

**참고 — 기존 자산** (`backend/domain/management/assistant/contracts.py`)
- `AskResult`(answer·citations·used_tools·evidence·suggested_action·requires_approval·thread_id).
- `Citation`(kind·source·title) · `SuggestedAction`(action_type·target_campaign_id·tier·requires_approval·rationale).
- 매핑 — `answer`→conclusion(서술 가드) / `citations`→evidence(`rag_citations`) / `suggested_action`→result(`action_proposal`)+review(`policy_check`)+actionbar(`actions`).

---

## Task 1: 카드 계약 모델 + 레지스트리 (`chat_cards`)

**Files:**
- Create: `backend/domain/management/assistant/chat_cards/__init__.py`
- Create: `backend/domain/management/assistant/chat_cards/models.py`
- Create: `backend/domain/management/assistant/chat_cards/registry.py`
- Test: `backend/tests/management/test_chat_cards.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/management/test_chat_cards.py`:

```python
# 카드 계약 모델·레지스트리·순수성(AST import-0) 검증
import ast
import pathlib

import pytest

from domain.management.assistant.chat_cards import (
    Card,
    CardKind,
    CardPayload,
    CardStatus,
    TurnEnvelope,
    TurnOrigin,
    is_registered,
    validate_card,
)


def test_envelope_defaults_origin_user():
    env = TurnEnvelope(turn_id="t1", conclusion="요약")
    assert env.origin == TurnOrigin.USER
    assert env.trigger is None
    assert env.read_state is None
    assert env.cards == []


def test_card_default_status_ok():
    card = Card(kind=CardKind.EVIDENCE, payload=CardPayload(type="rag_citations", version=1))
    assert card.status == CardStatus.OK


def test_registry_known_types_registered():
    assert is_registered(CardKind.RESULT, "action_proposal", 1)
    assert is_registered(CardKind.REVIEW, "policy_check", 1)
    assert is_registered(CardKind.ACTIONBAR, "actions", 1)
    assert is_registered(CardKind.EVIDENCE, "rag_citations", 1)


def test_registry_rejects_unknown_type_and_version():
    assert not is_registered(CardKind.RESULT, "kpi_distribution", 1)  # B 단계, 미등록
    assert not is_registered(CardKind.RESULT, "action_proposal", 2)  # 미등록 버전


def test_validate_card_raises_on_unregistered():
    bad = Card(kind=CardKind.RESULT, payload=CardPayload(type="nope", version=1))
    with pytest.raises(ValueError, match="unregistered card"):
        validate_card(bad)


def test_chat_cards_is_pure_no_management_imports():
    # AST 정적 검사 — chat_cards는 자기 패키지(.models/.registry, level==1)만 상대 import.
    # level>=2 상대 import(.. 이상)와 chat_cards 외 절대 management import는 금지.
    import domain.management.assistant.chat_cards as pkg

    pkg_dir = pathlib.Path(pkg.__file__).parent
    allowed = "domain.management.assistant.chat_cards"
    offenders: list[tuple[str, str]] = []
    for py in sorted(pkg_dir.glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.startswith("domain.management") and not a.name.startswith(allowed):
                        offenders.append((py.name, a.name))
            elif isinstance(node, ast.ImportFrom):
                if node.level >= 2:
                    # 패키지 밖(.. 이상)으로 나가는 상대 import 금지 — from ..contracts 등 차단
                    offenders.append((py.name, f"relative level={node.level} module={node.module}"))
                elif node.level == 1:
                    continue  # 자기 패키지 내부(.models/.registry/.) 허용
                elif node.module and node.module.startswith("domain.management") and not node.module.startswith(allowed):
                    offenders.append((py.name, node.module))
    assert offenders == [], f"chat_cards must not import management internals: {offenders}"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_chat_cards.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.management.assistant.chat_cards'`

- [ ] **Step 3: 모델 구현**

`backend/domain/management/assistant/chat_cards/models.py`:

```python
# 채팅 카드 봉투 계약 — kind(닫힌 슬롯) + payload.type/version(열린 확장점). management 내부 import 금지(순수).
from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class CardKind(StrEnum):
    EVIDENCE = "evidence"
    RESULT = "result"
    REVIEW = "review"
    ACTIONBAR = "actionbar"


class CardStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


class TurnOrigin(StrEnum):
    USER = "user"
    PROACTIVE = "proactive"


class CardPayload(BaseModel):
    type: str  # 슬롯 안의 변종 (rag_citations / action_proposal / policy_check / actions ...)
    version: int = 1
    data: dict[str, Any] = Field(default_factory=dict)


class Card(BaseModel):
    kind: CardKind
    status: CardStatus = CardStatus.OK
    payload: CardPayload


class TurnEnvelope(BaseModel):
    turn_id: str
    origin: TurnOrigin = TurnOrigin.USER  # 기본 user — 필드 없으면 user로 간주
    conclusion: str  # 항상, 서술만(불변식 ③ — Composer 서술 가드 통과)
    cards: list[Card] = Field(default_factory=list)
    # 능동 제안 전용(origin=proactive일 때만) — 후속 plan에서 채움
    trigger: dict[str, Any] | None = None
    read_state: Literal["unread", "read"] | None = None
```

- [ ] **Step 4: 레지스트리 + 패키지 API 구현**

`backend/domain/management/assistant/chat_cards/registry.py`:

```python
# (kind, type, version) 레지스트리 — 프론트 렌더러와 Composer가 공유하는 A↔B 계약의 단일 출처.
from __future__ import annotations

from .models import Card, CardKind

# (kind, type) -> 지원 version 집합. B 단계에서 result에 kpi_distribution/variants 등 추가.
_REGISTRY: dict[tuple[CardKind, str], set[int]] = {
    (CardKind.EVIDENCE, "rag_citations"): {1},
    (CardKind.RESULT, "action_proposal"): {1},
    (CardKind.REVIEW, "policy_check"): {1},
    (CardKind.ACTIONBAR, "actions"): {1},
}


def is_registered(kind: CardKind, type_: str, version: int) -> bool:
    return version in _REGISTRY.get((kind, type_), set())


def validate_card(card: Card) -> None:
    if not is_registered(card.kind, card.payload.type, card.payload.version):
        raise ValueError(
            f"unregistered card: ({card.kind}, {card.payload.type}, v{card.payload.version})"
        )
```

`backend/domain/management/assistant/chat_cards/__init__.py`:

```python
# chat_cards 공개 API — 카드 봉투 계약 + 레지스트리.
from .models import (
    Card,
    CardKind,
    CardPayload,
    CardStatus,
    TurnEnvelope,
    TurnOrigin,
)
from .registry import is_registered, validate_card

__all__ = [
    "Card",
    "CardKind",
    "CardPayload",
    "CardStatus",
    "TurnEnvelope",
    "TurnOrigin",
    "is_registered",
    "validate_card",
]
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_chat_cards.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: Ruff**

Run: `cd backend && uv run ruff format domain/management/assistant/chat_cards tests/management/test_chat_cards.py && uv run ruff check domain/management/assistant/chat_cards tests/management/test_chat_cards.py --fix`

- [ ] **Step 7: 커밋**

```bash
git add backend/domain/management/assistant/chat_cards backend/tests/management/test_chat_cards.py
git commit -m "add: 채팅 카드 계약 모델·레지스트리(chat_cards) — kind+type+version"
```

---

## Task 2: Composer — `compose_turn` (AskResult → 봉투)

**Files:**
- Create: `backend/domain/management/assistant/composer.py`
- Test: `backend/tests/management/test_composer.py`

매핑 — `answer`→conclusion(서술 가드) / `citations`→evidence / `suggested_action`→result+review+actionbar. suggested_action 없으면 result·review·actionbar 없음(progressive disclosure).

**서술 가드(불변식 ③)** — `_descriptive_conclusion`이 결론에서 실행 지시 문장(예 "지금 실행하세요")을 제거한다. 행동 가능한 주장은 카드/액션바에만.

**review·actionbar(MVP, 불변식 ①)** — review는 `decision ∈ {auto_ok, needs_approval}`를 **기록만** 한다. actionbar의 변경 액션(`approve`/`execute`)은 실행 API가 없으므로 **항상 `enabled=False, wired=False`**, `proposal_draft`만 싣는다. `regenerate`(클라이언트측 재질문)만 `enabled=True`. decision은 실행을 자동 활성하지 않는다.

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/management/test_composer.py`:

```python
# Composer: AskResult→봉투 매핑 — 서술 가드·슬롯 순서·actionbar 변경액션 비활성(MVP)
from domain.management.assistant.chat_cards import CardKind, TurnOrigin, validate_card
from domain.management.assistant.composer import compose_turn
from domain.management.assistant.contracts import AskResult, Citation, SuggestedAction


def _kinds(env):
    return [c.kind for c in env.cards]


def _card(env, kind):
    return next(c for c in env.cards if c.kind == kind)


def _pause(requires_approval=False, tier="TIER_1"):
    return SuggestedAction(
        action_type="PAUSE_CAMPAIGN", target_campaign_id="camp_1",
        tier=tier, requires_approval=requires_approval, rationale="런레이트 초과",
    )


def test_read_only_answer_has_conclusion_no_action_cards():
    res = AskResult(answer="예산은 정상 페이스입니다.", citations=[Citation(kind="live", source="live_budget")])
    env = compose_turn(res, turn_id="t1")
    assert env.turn_id == "t1"
    assert env.origin == TurnOrigin.USER
    assert env.conclusion == "예산은 정상 페이스입니다."
    assert CardKind.EVIDENCE in _kinds(env)
    assert CardKind.RESULT not in _kinds(env)
    assert CardKind.ACTIONBAR not in _kinds(env)


def test_evidence_card_carries_citations():
    res = AskResult(answer="x", citations=[Citation(kind="kb", source="meta_ad_policy.md", title="Meta 정책")])
    env = compose_turn(res, turn_id="t1")
    ev = _card(env, CardKind.EVIDENCE)
    assert ev.payload.type == "rag_citations"
    assert ev.payload.version == 1
    assert ev.payload.data["citations"][0]["source"] == "meta_ad_policy.md"


def test_action_intent_builds_result_review_actionbar_in_order():
    res = AskResult(answer="일시중지를 제안합니다.", suggested_action=_pause())
    env = compose_turn(res, turn_id="t2")
    assert _kinds(env) == [CardKind.RESULT, CardKind.REVIEW, CardKind.ACTIONBAR]  # 슬롯 순서 + actionbar 마지막
    result = _card(env, CardKind.RESULT)
    assert result.payload.type == "action_proposal"
    assert result.payload.data["action_type"] == "PAUSE_CAMPAIGN"


def test_conclusion_strips_execution_directive():
    # 불변식 ③ — 결론은 서술만. "지금 실행하세요" 같은 지시 문장 제거.
    res = AskResult(answer="예산이 초과됐습니다. 지금 실행하세요.", suggested_action=_pause())
    env = compose_turn(res, turn_id="t3")
    assert "실행하세요" not in env.conclusion
    assert "예산이 초과됐습니다." in env.conclusion


def test_directive_only_answer_degrades_to_neutral():
    # 답변이 지시문뿐이면 원문을 흘리지 말고 중립 강등(P1 — 원문 재노출 금지).
    res = AskResult(answer="지금 실행하세요.", suggested_action=_pause())
    env = compose_turn(res, turn_id="t3b")
    assert "실행하세요" not in env.conclusion
    assert env.conclusion == "자세한 내용은 아래 카드를 확인하세요."


def test_result_card_marks_draft_not_executable():
    # result는 draft 단계 — "바로 실행 가능"이 아님을 data로 명시.
    res = AskResult(answer="제안합니다.", suggested_action=_pause())
    env = compose_turn(res, turn_id="t3c")
    data = _card(env, CardKind.RESULT).payload.data
    assert data["stage"] == "draft"
    assert data["executable"] is False


def test_mutating_actions_disabled_pending_execute_api():
    # MVP — 변경 액션은 실행 API 미연결이라 비활성, proposal_draft만 실림(불변식 ①).
    res = AskResult(answer="일시중지를 제안합니다.", suggested_action=_pause())
    env = compose_turn(res, turn_id="t4")
    actions = {a["id"]: a for a in _card(env, CardKind.ACTIONBAR).payload.data["actions"]}
    assert actions["regenerate"]["enabled"] is True
    for aid in ("approve", "execute"):
        assert actions[aid]["enabled"] is False
        assert actions[aid]["wired"] is False
        assert actions[aid]["kind"] == "mutating"
        assert actions[aid]["proposal_draft"]["action_type"] == "PAUSE_CAMPAIGN"


def test_review_records_decision_without_enabling_execute():
    # auto_ok든 needs_approval이든 MVP에선 execute가 자동 활성되지 않는다.
    auto = compose_turn(AskResult(answer="x", suggested_action=_pause(requires_approval=False)), turn_id="t5")
    needs = compose_turn(
        AskResult(answer="x", suggested_action=_pause(requires_approval=True, tier="TIER_3"), requires_approval=True),
        turn_id="t6",
    )
    assert _card(auto, CardKind.REVIEW).payload.data["decision"] == "auto_ok"
    assert _card(needs, CardKind.REVIEW).payload.data["decision"] == "needs_approval"
    for env in (auto, needs):
        ab = {a["id"]: a for a in _card(env, CardKind.ACTIONBAR).payload.data["actions"]}
        assert ab["execute"]["enabled"] is False  # 실행 정본은 실행 API


def test_all_cards_are_registered():
    res = AskResult(
        answer="x",
        citations=[Citation(kind="live", source="live_budget")],
        suggested_action=_pause(),
    )
    env = compose_turn(res, turn_id="t7")
    for card in env.cards:
        validate_card(card)  # 미등록이면 raise
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_composer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.management.assistant.composer'`

- [ ] **Step 3: Composer 구현**

`backend/domain/management/assistant/composer.py`:

```python
# Composer — 어시스턴트 재료(AskResult)를 검증된 카드 봉투로 조립한다. 서술 가드·검수 게이트를 여기서 강제.
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .chat_cards import (
    Card,
    CardKind,
    CardPayload,
    CardStatus,
    TurnEnvelope,
    TurnOrigin,
    validate_card,
)

if TYPE_CHECKING:
    from .contracts import AskResult

# 불변식 ③ — 결론에서 제거할 실행 지시 마커(휴리스틱 1차). 행동 가능한 주장은 카드/액션바로.
_DIRECTIVE_MARKERS = (
    "실행하세요",
    "실행하면 됩니다",
    "지금 실행",
    "바로 실행",
    "바로 적용",
    "집행하세요",
    "눌러서 실행",
)
# 전부 지시문이라 남길 서술이 없을 때의 중립 강등 문구. 원문(지시문) 재노출 금지.
_NEUTRAL_CONCLUSION = "자세한 내용은 아래 카드를 확인하세요."


def _descriptive_conclusion(answer: str) -> str:
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", answer.strip()) if s]
    kept = [s for s in sentences if not any(m in s for m in _DIRECTIVE_MARKERS)]
    cleaned = " ".join(kept).strip()
    return cleaned or _NEUTRAL_CONCLUSION  # 전부 지시문이면 중립 강등(원문 재노출 금지)


def _evidence_card(res: AskResult) -> Card | None:
    if not res.citations:
        return None
    return Card(
        kind=CardKind.EVIDENCE,
        payload=CardPayload(
            type="rag_citations",
            version=1,
            data={
                "citations": [
                    {"kind": c.kind, "source": c.source, "title": c.title} for c in res.citations
                ],
                "used_tools": list(res.used_tools),
            },
        ),
    )


def _result_card(res: AskResult) -> Card:
    sa = res.suggested_action
    return Card(
        kind=CardKind.RESULT,
        payload=CardPayload(
            type="action_proposal",
            version=1,
            data={
                "action_type": sa.action_type,
                "target_campaign_id": sa.target_campaign_id,
                "tier": sa.tier,
                "rationale": sa.rationale,
                # MVP — 아직 영속·검증된 proposal이 아님. "바로 실행 가능"으로 오해 금지.
                "stage": "draft",
                "executable": False,
            },
        ),
    )


def _review_card(res: AskResult) -> tuple[Card, str]:
    sa = res.suggested_action
    decision = "needs_approval" if sa.requires_approval else "auto_ok"
    card = Card(
        kind=CardKind.REVIEW,
        payload=CardPayload(
            type="policy_check",
            version=1,
            data={"decision": decision, "tier": sa.tier, "reasons": [sa.rationale]},
        ),
    )
    return card, decision


def _actionbar_card(res: AskResult) -> Card:
    # MVP — 실행 API 미연결이라 변경 액션은 비활성(불변식 ①). proposal_draft로 Plan 2 배선 대비.
    sa = res.suggested_action
    draft = {
        "action_type": sa.action_type,
        "target_campaign_id": sa.target_campaign_id,
        "tier": sa.tier,
    }
    pending = "실행 API 미연결 (Plan 2)"
    actions = [
        {"id": "regenerate", "label": "다시 생성", "kind": "safe", "enabled": True, "wired": True,
         "proposal_draft": None},
        {"id": "approve", "label": "승인", "kind": "mutating", "enabled": False, "wired": False,
         "disabled_reason": pending, "proposal_draft": draft},
        {"id": "execute", "label": "실행", "kind": "mutating", "enabled": False, "wired": False,
         "disabled_reason": pending, "proposal_draft": draft},
    ]
    return Card(
        kind=CardKind.ACTIONBAR,
        payload=CardPayload(type="actions", version=1, data={"actions": actions}),
    )


def compose_turn(
    res: AskResult, *, turn_id: str, origin: TurnOrigin = TurnOrigin.USER
) -> TurnEnvelope:
    """AskResult를 카드 봉투로 매핑. 슬롯 순서 고정, actionbar는 review 이후 항상 마지막."""
    cards: list[Card] = []

    evidence = _evidence_card(res)
    if evidence is not None:
        cards.append(evidence)

    if res.suggested_action is not None:
        cards.append(_result_card(res))
        review, _decision = _review_card(res)
        cards.append(review)
        cards.append(_actionbar_card(res))  # 항상 마지막

    for card in cards:
        validate_card(card)

    return TurnEnvelope(
        turn_id=turn_id,
        origin=origin,
        conclusion=_descriptive_conclusion(res.answer),
        cards=cards,
    )
```

> `Card`/`CardPayload` 기본 `status=ok`라 명시 생략. `CardStatus`는 Task 3 `stream_turn`에서 사용하므로 import 유지.

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_composer.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Ruff**

Run: `cd backend && uv run ruff format domain/management/assistant/composer.py tests/management/test_composer.py && uv run ruff check domain/management/assistant/composer.py tests/management/test_composer.py --fix`

- [ ] **Step 6: 커밋**

```bash
git add backend/domain/management/assistant/composer.py backend/tests/management/test_composer.py
git commit -m "add: Composer compose_turn — 카드 매핑·서술 가드·변경액션 비활성(MVP)"
```

---

## Task 3: Composer — `stream_turn` (2단계 SSE 이벤트)

**Files:**
- Modify: `backend/domain/management/assistant/composer.py`
- Test: `backend/tests/management/test_chat_sse.py`

이벤트 — `conclusion_delta`(결론 청크) → `card_ready`(슬롯 순서, actionbar 마지막) → `final`(`status` ∈ ok/partial/failed). `final`은 항상 송신. 라인은 `data: {json}\n\n`. `final.status` — 모든 카드 ok면 `ok`, 일부 degraded/failed면 `partial`.

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/management/test_chat_sse.py`:

```python
# stream_turn: 2단계 SSE 이벤트 시퀀스·actionbar 마지막·final status (+ Task 4 라우터 헬퍼)
import json

import pytest

from domain.management.assistant.chat_cards import CardStatus
from domain.management.assistant.composer import compose_turn, stream_turn
from domain.management.assistant.contracts import AskResult, Citation, SuggestedAction


def _parse(lines: list[str]) -> list[dict]:
    out = []
    for ln in lines:
        assert ln.startswith("data: ") and ln.endswith("\n\n")
        out.append(json.loads(ln[len("data: ") :].strip()))
    return out


async def _collect(env) -> list[dict]:
    return _parse([chunk async for chunk in stream_turn(env)])


@pytest.mark.asyncio
async def test_event_sequence_conclusion_then_cards_then_final():
    res = AskResult(
        answer="일시중지를 제안합니다.",
        citations=[Citation(kind="live", source="live_budget")],
        suggested_action=SuggestedAction(
            action_type="PAUSE_CAMPAIGN", tier="TIER_1", requires_approval=False, rationale="r",
        ),
    )
    env = compose_turn(res, turn_id="t1")
    events = await _collect(env)
    names = [e["event"] for e in events]
    assert names[0] == "conclusion_delta"
    assert names[-1] == "final"
    card_events = [e for e in events if e["event"] == "card_ready"]
    assert card_events[-1]["card"]["kind"] == "actionbar"


@pytest.mark.asyncio
async def test_final_status_ok_when_all_cards_ok():
    res = AskResult(answer="정상입니다.", citations=[Citation(kind="live", source="live_budget")])
    env = compose_turn(res, turn_id="t2")
    events = await _collect(env)
    final = events[-1]
    assert final["event"] == "final"
    assert final["turn_id"] == "t2"
    assert final["status"] == "ok"


@pytest.mark.asyncio
async def test_final_status_partial_when_a_card_degraded():
    res = AskResult(answer="x", citations=[Citation(kind="live", source="live_budget")])
    env = compose_turn(res, turn_id="t3")
    env.cards[0].status = CardStatus.DEGRADED
    events = await _collect(env)
    assert events[-1]["status"] == "partial"


@pytest.mark.asyncio
async def test_conclusion_streamed_in_chunks_reassembles():
    res = AskResult(answer="a" * 60)  # 지시 마커 없음 → 서술 가드 통과, 원문 보존
    env = compose_turn(res, turn_id="t4")
    events = await _collect(env)
    text = "".join(e["text"] for e in events if e["event"] == "conclusion_delta")
    assert text == "a" * 60
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_chat_sse.py -v`
Expected: FAIL — `ImportError: cannot import name 'stream_turn'`

- [ ] **Step 3: `stream_turn` 구현 (composer.py에 추가)**

`backend/domain/management/assistant/composer.py` 상단 import 블록에 추가:

```python
import json
from collections.abc import AsyncGenerator
```

파일 끝에 추가:

```python
def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _chunks(text: str, size: int = 24) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def _final_status(env: TurnEnvelope) -> str:
    return "partial" if any(c.status != CardStatus.OK for c in env.cards) else "ok"


async def stream_turn(env: TurnEnvelope) -> AsyncGenerator[str, None]:
    """카드 봉투를 2단계 SSE로 — 결론 먼저, 카드는 슬롯 순서(actionbar 마지막), final 항상."""
    for piece in _chunks(env.conclusion):
        yield _sse({"event": "conclusion_delta", "text": piece})
    for card in env.cards:  # compose_turn이 이미 슬롯 순서·actionbar 마지막으로 정렬
        yield _sse({"event": "card_ready", "card": card.model_dump(mode="json")})
    yield _sse({"event": "final", "turn_id": env.turn_id, "status": _final_status(env)})
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_chat_sse.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Ruff**

Run: `cd backend && uv run ruff format domain/management/assistant/composer.py tests/management/test_chat_sse.py && uv run ruff check domain/management/assistant/composer.py tests/management/test_chat_sse.py --fix`

- [ ] **Step 6: 커밋**

```bash
git add backend/domain/management/assistant/composer.py backend/tests/management/test_chat_sse.py
git commit -m "add: stream_turn — 2단계 SSE(conclusion_delta·card_ready·final)"
```

---

## Task 4: 라우터 연결 — 주입형 `_management_card_stream`

**Files:**
- Modify: `backend/api/routers/chat.py` (매니지먼트 분기 + 헬퍼 추가)
- Test: `backend/tests/management/test_chat_sse.py` (헬퍼 단위 테스트 추가)

라우터 분기를 **의존성 주입 헬퍼**로 추출한다(`assistant`·`record` 주입). 테스트는 fake를 넣어 **앱·LLM·DB 없이** 결정론적으로 검증한다. CLIO(Gemini) 분기는 그대로.

- [ ] **Step 1: 헬퍼 단위 실패 테스트 추가**

`backend/tests/management/test_chat_sse.py` 끝에 추가:

```python
@pytest.mark.asyncio
async def test_management_card_stream_emits_events_with_injected_deps():
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
            question="예산?", session_id="s1", ad_id=None,
            assistant=fake_assistant, record=fake_record,
        )
    ]
    events = _parse(chunks)
    names = [e["event"] for e in events]
    assert names[0] == "conclusion_delta"
    assert names[-1] == "final"
    assert events[-1]["status"] == "ok"
    assert recorded and recorded[0]["thread_id"] == "mgmt-s1"


@pytest.mark.asyncio
async def test_management_card_stream_failure_emits_error_and_final_failed():
    from api.routers.chat import _management_card_stream

    async def boom(req):
        raise RuntimeError("assistant down")

    async def fake_record(**kw):
        pass

    chunks = [
        c
        async for c in _management_card_stream(
            question="예산?", session_id="s1", ad_id=None, assistant=boom, record=fake_record,
        )
    ]
    events = _parse(chunks)
    assert any(e.get("event") == "error" and e.get("scope") == "turn" for e in events)
    assert events[-1]["event"] == "final" and events[-1]["status"] == "failed"


@pytest.mark.asyncio
async def test_management_card_stream_record_failure_is_best_effort():
    # 적재(record) 실패는 답변 스트림을 깨지 않는다 — best-effort(원래 chat.py 동작).
    from api.routers.chat import _management_card_stream

    async def fake_assistant(req):
        return AskResult(answer="예산은 정상입니다.", citations=[Citation(kind="live", source="live_budget")])

    async def boom_record(**kw):
        raise RuntimeError("db down")

    chunks = [
        c
        async for c in _management_card_stream(
            question="예산?", session_id="s1", ad_id=None,
            assistant=fake_assistant, record=boom_record,
        )
    ]
    events = _parse(chunks)
    assert events[-1]["event"] == "final"
    assert events[-1]["status"] == "ok"  # 적재 실패에도 정상 종료
    assert not any(e.get("event") == "error" for e in events)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_chat_sse.py -k management_card_stream -v`
Expected: FAIL — `ImportError: cannot import name '_management_card_stream'`

- [ ] **Step 3: 헬퍼 + 라우터 분기 구현**

`backend/api/routers/chat.py` 상단 import 블록에 추가:

```python
from domain.management.assistant.composer import compose_turn, stream_turn
```

> **import 확인** — 헬퍼는 `AsyncGenerator`(시그니처)·`json`·`time`을 쓴다. 현재 chat.py 1~15행에 `import json`·`import time`·`from collections.abc import AsyncGenerator, Awaitable, Callable`가 **이미 있다**(확인됨). 만약 없으면 다음을 추가: `import json` · `import time` · `from collections.abc import AsyncGenerator`.

`chat_complete` 함수 **위**에 헬퍼 2개 추가:

```python
async def _record_management_turn(*, thread_id, result, question, ad_id, latency_ms) -> None:
    # 관측·평가용 적재. 실패해도 채팅은 진행(best-effort).
    await record_turn(
        thread_id=thread_id,
        question=question,
        answer=result.answer,
        model=getattr(settings, "management_assistant_model", "gpt-4o-mini"),
        latency_ms=latency_ms,
        used_tools=list(result.used_tools),
        citations=[{"kind": c.kind, "source": c.source, "title": c.title} for c in result.citations],
        suggested_action=(result.suggested_action.model_dump() if result.suggested_action else None),
        requires_approval=result.requires_approval,
        ad_id=ad_id,
    )


async def _management_card_stream(
    *, question, session_id, ad_id, assistant, record
) -> AsyncGenerator[str, None]:
    # 매니지먼트 한 턴을 카드 SSE로. assistant/record 주입 → 앱·DB 없이 테스트 가능.
    thread_id = f"mgmt-{session_id}"

    # 1) 어시스턴트 호출 + 봉투 조립 — 여기서 실패하면 진짜 턴 실패(아직 아무것도 yield 안 함).
    try:
        t0 = time.perf_counter()
        result = await assistant(AskRequest(question=question, ad_id=ad_id, thread_id=thread_id))
        latency_ms = int((time.perf_counter() - t0) * 1000)
        env = compose_turn(result, turn_id=thread_id)
    except Exception as exc:  # noqa: BLE001 — 어시스턴트/조립 실패 = 턴 실패
        yield (
            "data: "
            + json.dumps(
                {"event": "error", "scope": "turn", "code": "assistant_error",
                 "message": f"매니지먼트 조회 중 문제가 발생했어요: {exc}"},
                ensure_ascii=False,
            )
            + "\n\n"
        )
        yield (
            "data: "
            + json.dumps({"event": "final", "turn_id": thread_id, "status": "failed"}, ensure_ascii=False)
            + "\n\n"
        )
        return

    # 2) 관측 적재는 best-effort — 실패해도 답변 스트림은 그대로(원래 chat.py 동작 보존).
    try:
        await record(
            thread_id=thread_id, result=result, question=question, ad_id=ad_id, latency_ms=latency_ms
        )
    except Exception as exc:  # noqa: BLE001 — 적재 실패는 채팅을 끊지 않는다
        print(f"[chat] record_turn failed (best-effort, ignored): {exc!r}")

    # 3) 정상 답변 스트리밍.
    async for chunk in stream_turn(env):
        yield chunk
```

`generate()` 안의 기존 `if _is_management(last_message):` 블록(현재 113~168행) 전체를 아래로 교체:

```python
        if _is_management(last_message):
            async for chunk in _management_card_stream(
                question=last_message,
                session_id=body.session_id,
                ad_id=body.context_ad_id,
                assistant=_get_assistant(),
                record=_record_management_turn,
            ):
                yield chunk
            return
```

> 교체로 매니지먼트 분기의 기존 `meta`/`token`/`done` 라인과 그 분기의 `_chunks` 사용이 사라진다. CLIO(Gemini) 분기·`record_feedback`·`/feedback`은 그대로. `_chunks`가 더 이상 어디서도 안 쓰이면 Ruff(F811/미사용)에서 잡히므로 그때 제거.

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_chat_sse.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: 전체 매니지먼트 회귀 + Ruff**

Run: `cd backend && uv run pytest tests/management/ -v`
Expected: 기존 `test_assistant*.py` 포함 전부 PASS(어시스턴트 계약·툴 라우팅 무변경).

Run: `cd backend && uv run ruff format api/routers/chat.py && uv run ruff check api/routers/chat.py --fix`
Expected: 통과. 미사용 `_chunks`가 매니지먼트 분기 제거로 잡히면 함께 정리.

- [ ] **Step 6: 커밋**

```bash
git add backend/api/routers/chat.py backend/tests/management/test_chat_sse.py
git commit -m "edit: /complete 매니지먼트 분기를 주입형 카드 SSE 헬퍼로 교체"
```

---

## Self-Review (계획 작성자 점검 결과)

- **Spec 커버리지** — §4 데이터 계약(Task 1) · §5 SSE 2단계+final 항상(Task 3) · §6 ②(슬롯 순서·actionbar 마지막, Task 2·3) · ③(서술 가드 `_descriptive_conclusion`, Task 2) · ④(final status partial/failed, Task 3·4) · ①(MVP에선 변경 액션 비활성+proposal_draft, 실 배선은 후속 plan 2). §10 능동 제안·§4.1 trigger/read_state는 **후속 plan**(아래) — 본 plan은 `TurnEnvelope`에 필드만 미리 둠.
- **타입 일관성** — `compose_turn(res, *, turn_id, origin)` / `stream_turn(env)` / `validate_card(card)` / `is_registered(kind, type_, version)` / `_management_card_stream(*, question, session_id, ad_id, assistant, record)` 전 Task 동일. `CardKind`·`CardStatus`·`TurnOrigin` enum 일치. actionbar 액션 키(`id`·`enabled`·`wired`·`kind`·`proposal_draft`) Task 2 정의와 Task 4 테스트 일치.
- **불안정 테스트 제거** — Task 4는 실제 앱/ASGI/DB 대신 주입형 헬퍼 단위 테스트.
- **플레이스홀더** — 없음. 모든 코드 스텝에 실제 코드 포함.

## 후속 Plan (본 plan 범위 밖)

1. **실행 API 재배선(불변식 ① 완성)** — actionbar `approve`/`execute`를 받아 `proposal_draft`로 서버에서 proposal 생성·재검증 후 `execution/` 집행. 이후 Composer가 decision에 따라 `enabled/wired`를 켠다. 기존 `approval.py`·`execution/` 연결.
2. **능동 제안(Proactive)** — `proactive.py`(트리거 invoker: demo tick) · escalation→Composer(origin=proactive) · dedup(실제 DB 키 `tenant_id+account_id+campaign_id+anomaly+escalation_step`) · 인박스 영속(`core/models.py` 신규 테이블 — 공유부, 사전 공지). spec §10.
3. **프론트 렌더러** — kind+payload.type 고정 슬롯·스켈레톤·액션바·인박스. spec §7.
