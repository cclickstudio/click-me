# Task 10: ChatRequest.option_select + 옵션 meta 우선 매핑

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-03-remediation-hybrid-notification.md` · 스펙: `docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md` §4
> **실행 규칙**: 백엔드 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 파일 첫 줄 한국어 헤더 주석 · 🅰 소유 파일 수정 금지.
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.
> ⚠ `core/schemas.py`는 공통부 — 해당 변경은 **단독 커밋**으로 분리(Step 6 참조), 사전 공지(Task 0 ③) 확인.

---

**Files:**
- Modify: `backend/core/schemas.py:166` (improve_context 아래)
- Modify: `backend/domain/management/remediation/context.py` (함수 1개 추가)
- Modify: `backend/api/routers/chat.py` (consult_ctx 회수 지점·`_persist`)
- Test: `test/backend/management/test_remediation_context.py` (기존 파일에 케이스 추가)

- [ ] **Step 1: 실패 테스트 추가**

`test/backend/management/test_remediation_context.py` 끝에:

```python
def test_build_option_instruction_prefers_meta_mapping():
    from domain.management.remediation.context import build_option_instruction

    sel = {
        "option_index": 1,
        "action": "VERIFY_SIM",
        "tool_hint": "run_simulation",
        "campaign_id": "c1",
        "label": "시뮬레이션으로 소재 점검",
    }
    text = build_option_instruction(sel)
    assert "run_simulation" in text and "c1" in text
    assert "1" in text  # 선택 번호 명시


def test_build_option_instruction_observe_without_tool():
    from domain.management.remediation.context import build_option_instruction

    sel = {"option_index": 4, "action": "OBSERVE", "tool_hint": None,
           "campaign_id": "c1", "label": "두고 보기(추가 조치 없음)"}
    text = build_option_instruction(sel)
    assert "호출하지" in text  # 도구 호출 금지 지시
```

- [ ] **Step 2: 실패 확인**

```bash
cd backend && uv run pytest ../test/backend/management/test_remediation_context.py -v
```
Expected: 새 2케이스 FAIL (함수 없음)

- [ ] **Step 3: context.py에 함수 추가**

`backend/domain/management/remediation/context.py` 끝에:

```python
def build_option_instruction(sel: dict) -> str:
    """옵션 버튼 클릭 meta → 지시문 — LLM 텍스트 해석 없이 정확 매핑(스펙 §4).

    meta가 실려 오면 recall(세션 회수)보다 이걸 우선한다. 일반 타이핑("1번 해줘")은
    기존 recall_consult_context 경로 그대로(두 입력 공존).
    """
    idx = sel.get("option_index")
    label = sel.get("label", "")
    cid = sel.get("campaign_id", "")
    hint = sel.get("tool_hint")
    head = f"[사용자가 이상 조치 옵션 {idx}번({label})을 버튼으로 선택했다 · campaign_id={cid}]\n"
    if hint:
        return head + (
            f"즉시 도구 {hint}를 campaign_id와 함께 호출해 진행하라. "
            "지출 조치(manage_campaign)는 확인 카드로만 제안하고 직접 실행하지 않는다."
        )
    return head + (
        "관망 선택 — 도구를 호출하지 말고, 지금은 지켜보겠다는 선택을 확인하는 답변만 하라."
    )
```

- [ ] **Step 4: core/schemas.py 필드 추가** (⚠ 공통부)

`backend/core/schemas.py` `improve_context` 필드 아래에:

```python
    # 이상 조치 옵션 버튼 클릭(관리 도메인) — {option_index, action, tool_hint, campaign_id, label}
    option_select: dict | None = None
```

- [ ] **Step 5: chat.py 연결**

`backend/api/routers/chat.py` 419행 부근 — `recall_consult_context` 회수 지점을 다음 형태로 (기존 recall 호출을 감싸는 분기 추가):

```python
        # 진행 중 이상 조치 상담 컨텍스트(management) — 옵션 버튼 meta가 오면 그걸 우선.
        if body.option_select:
            from domain.management.remediation.context import (  # noqa: PLC0415
                build_option_instruction,
            )

            consult_ctx = build_option_instruction(body.option_select)
        else:
            # (기존 recall_consult_context 호출 코드 그대로)
```

`_persist`(380행)에 파라미터 추가 — 시그니처와 user_meta에 각 1줄:

```python
async def _persist(
    session_id: str,
    user_content: str,
    assistant_content: str,
    meta: dict | None,
    image_url: str | None = None,
    result_ref: dict | None = None,
    option_select: dict | None = None,
) -> None:
    """한 턴을 DB에 적재(best-effort) — 세션 없거나 실패해도 채팅은 진행."""
    user_meta: dict = {}
    if image_url:
        user_meta["image_url"] = image_url
    if result_ref:
        user_meta["result"] = result_ref
    if option_select:
        user_meta["option_select"] = option_select
```

`_persist` 호출부(3곳 — 440·454·526행 부근)에 `body.option_select`를 마지막 인자로 추가.

- [ ] **Step 6: 통과 확인 + 커밋 2개(공통부 분리)**

```bash
cd backend && uv run pytest ../test/backend/management/test_remediation_context.py -v
cd backend && uv run pytest ../test/backend/management -q   # 회귀
cd backend && uv run ruff format . && uv run ruff check . --fix && cd ..
git add backend/core/schemas.py
git commit -m "add: ChatRequest.option_select 필드 — 옵션 버튼 meta 수용 (공통부 append-only)"
git add backend/domain/management/remediation/context.py backend/api/routers/chat.py test/backend/management/test_remediation_context.py
git commit -m "add: 옵션 버튼 meta 우선 매핑 — build_option_instruction + chat 연결"
```
