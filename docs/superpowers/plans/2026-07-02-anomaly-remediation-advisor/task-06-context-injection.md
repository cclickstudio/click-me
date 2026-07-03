# Task 6: 컨텍스트 왕복 — `remediation/context.py` + `chat.py` 주입

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-02-anomaly-remediation-advisor.md` · 스펙: `docs/superpowers/specs/2026-07-02-anomaly-remediation-advisor-design.md`
> **실행 규칙**: 모든 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 .py 첫 줄 한국어 헤더 주석 · 🅰 소유 파일(detection/, approval.py, agents/diagnosis*) 수정 금지(읽기만).
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.

---

**Files:**
- Create: `backend/domain/management/remediation/context.py`
- Modify: `backend/api/routers/chat.py:410-412` (memory_context 회수 직후)
- Test: `test/backend/management/test_remediation_context.py`

주입 3조건(스펙 §4): TTL 24h 내 + 최근 K=10 메시지 내 + 최신 1건만. 판정은 순수 함수로
분리해 단위 테스트, chat.py에는 얇은 async 래퍼 호출만 추가.

- [ ] **Step 1: 실패하는 테스트 작성**

`test/backend/management/test_remediation_context.py`:
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

Run: `cd backend && uv run pytest ../test/backend/management/test_remediation_context.py -v`
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

Run: `cd backend && uv run pytest ../test/backend/management/test_remediation_context.py -v`
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

Run: `cd backend && uv run pytest ../test/backend -k "chat" -v`
Expected: 기존 chat 테스트 전부 PASS

- [ ] **Step 7: 커밋**

```bash
git add backend/domain/management/remediation/context.py test/backend/management/test_remediation_context.py backend/api/routers/chat.py
git commit -m "add: consult 컨텍스트 서버측 주입(TTL·근접성·최신 1건 조건)"
```
