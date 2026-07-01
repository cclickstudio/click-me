# P2b — 챗 캠페인 예산 조치(INCREASE·DECREASE = 이미지) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`).
> **루프 규칙(이 레포):** 서브에이전트 구현(커밋 안 함) → **커밋 전** 적대적 리뷰(`/codex:adversarial-review`는 사용자 실행) + `requesting-code-review` → 사소한 건 인라인·어려운 건 `/codex:rescue` → 커밋.

**Goal:** 챗에서 "이 캠페인 예산 올려줘/내려줘"류 발화로 캠페인 **일 예산을 변경**한다. 이미지의 "검토·승인 → 집행" 카드 — 현재 예산 → 변경 예산을 **프리뷰로 보여주고 사람이 승인**하면 `/approve`+`/execute`로 집행. INCREASE/DECREASE는 직접 엔드포인트가 없으므로 **서버가 proposal을 빌드·finalize(hash)** 한다.

**Architecture:** P2 패턴 확장. `manage_campaign` 툴 action enum에 `increase_budget`·`decrease_budget`를 추가하고 예산 인자(`new_daily_budget_krw` 또는 `pct`)를 받는다. 신규 빌드 전용 엔드포인트 `POST /campaigns/{id}/budget-proposal`이 **현재 일예산을 서버 정본(DB)에서 조회**하고, **방향(선언 action=목표 방향)·no-op·범위를 검증**한 뒤 `ActionProposal`을 `finalize_proposal`(proposal_hash)해 반환(미집행). 프론트 `ChatBudgetProposalCard`가 프리뷰(현재→변경·Tier) 표시 후 **기존** `api.management.approve`+`execute` 호출. **§3 불변식**: 현재값·proposal 모두 서버가 정본(클라/LLM 입력 불신), 프리뷰=집행 대상은 hash 결속, 사람 승인이 게이트, 집행값은 `budget_after`(절대값). **`chat.py`·executor·`/approve`·`/execute` 미수정.**

**Tech Stack:** FastAPI(`management.py`·`deep_agent.py`)·Next.js/TS·Tailwind. 백엔드 pytest, 프론트 `pnpm lint`+`build`+수동.

**상위 설계:** `docs/superpowers/specs/2026-06-29-chat-campaign-actions-reuse-overview-design.md`(P2 예산 행). **선행(의존):** **P2(상태) 머지 완료** — `manage_campaign` 툴·`ChatCampaignActionCard`·`embed='campaign_action'` 렌더 분기가 있어야 한다(이 plan은 그 위에 예산 분기를 얹는다). **다음:** P3(REPLACE_CREATIVE·EXPAND_AUDIENCE·CHANGE_BID_STRATEGY).

---

## 참조 — 기존 코드 (구현 중 의존)

- 백엔드:
  - `backend/api/assistant/deep_agent.py` — P2의 `manage_campaign` 툴(enum `pause|activate`, dispatch가 `("action","campaign_id","campaign_name")` 키만 추림, `_state_to_result`가 `embed='campaign_action'`+`action` 합성·source 고정). **이 enum·키·디스패치를 확장한다.**
  - `backend/api/routers/management.py` — `finalize_proposal`·`ActionProposal`·`ActionTier`·`approve`·`_get_executor`·`_resolved_execution_mode`·`_require_org_id`·`_require_ad_account`·`_require_owned_campaign`·`judge_tier`·`PROPOSAL_TTL_MINUTES`·`APPROVAL_POLICY_VERSION` 임포트됨. `/pause`(2577)·`build_sample_proposal`(demo.py:70)이 `ActionProposal` 빌드 본보기.
  - `judge_tier("INCREASE_BUDGET")=TIER_3`, `judge_tier("DECREASE_BUDGET")=TIER_1`(`policy.py` `TIER_POLICY`).
  - `executor`가 `INCREASE_BUDGET`/`DECREASE_BUDGET`를 `writer.adjust_budget(target, budget_after_krw, idem)`로 집행(`executor.py:385`). 즉 **집행값은 `budget_after`(절대 일예산)**.
- 프론트:
  - `api.management.approve(proposal, true)`→`{approved_action}`, `execute(approved_action, proposal)`→`{result, error_message?}`. (P1에서 검증한 형태.)
  - `Proposal`·`ActionResult` 타입(`components/manage/types.ts`). `Proposal`에 `budget_before_krw`·`budget_after_krw`·`action_tier`·`proposal_hash` 있음.
  - P2의 `ChatCampaignActionCard`·`chat/page.tsx`의 `embed` 유니온(`'create_campaign'|'campaign_action'`)·렌더 분기.

---

## File Structure

| 파일 | 신규/수정 | 책임 |
|---|---|---|
| `backend/api/assistant/deep_agent.py` | 수정 | `manage_campaign` enum에 `increase_budget`/`decrease_budget` + 예산 인자, dispatch 키 확장 |
| `backend/api/routers/management.py` | 수정 | `POST /campaigns/{id}/budget-proposal` — 예산 proposal 빌드·finalize(미집행) |
| `backend/tests/management/test_budget_proposal.py` | 신규 | 빌더가 INCREASE/DECREASE proposal을 hash 결속해 반환하는지 |
| `frontend/src/lib/api.ts` | 수정 | `budgetProposal` 메서드 |
| `frontend/src/components/chat/ChatBudgetProposalCard.tsx` | 신규 | 프리뷰(현재→변경·Tier)→approve+execute→결과 |
| `frontend/src/app/(app)/chat/page.tsx` | 수정 | `increase_budget`/`decrease_budget` 렌더 분기 |

---

## Task 1: `manage_campaign` 툴에 예산 액션 추가 (`deep_agent.py`)

**Files:** Modify `backend/api/assistant/deep_agent.py`

- [ ] **Step 1: enum·인자 확장** — `manage_campaign` 툴 스펙의 `action` enum과 properties를 교체:

```python
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["pause", "activate", "increase_budget", "decrease_budget"],
                },
                "campaign_id": {"type": "string", "description": "대상 캠페인 ID(알면)"},
                "campaign_name": {"type": "string", "description": "사용자가 말한 캠페인 이름(있으면)"},
                "new_daily_budget_krw": {
                    "type": "integer",
                    "description": "예산 변경 시 목표 일예산 원(언급 시, '5만원'=50000)",
                },
                "pct": {
                    "type": "integer",
                    "description": "예산 변경 비율 %(언급 시, '25% 올려'=25, 내림은 음수)",
                },
            },
            "required": ["action"],
        },
```

설명(description)도 한 줄 보강(예산 포함):

```python
        "description": (
            "기존 캠페인 상태·예산 변경 요청에 호출한다. action='pause'|'activate'|"
            "'increase_budget'|'decrease_budget'. 예산 변경이면 new_daily_budget_krw 또는 pct를 채운다."
            " 특정 가능하면 campaign_id, 모르면 비운다. 생성엔 호출하지 않는다."
        ),
```

시스템 프롬프트(`_SYS_ORCHESTRATOR`)의 manage_campaign 줄도 예산 포함으로 갱신:

```
- 기존 캠페인 일시중지·게재 시작·예산 증액/감액 요청 → manage_campaign 호출
```

- [ ] **Step 2: dispatch 키 확장** — `manage_campaign` 분기의 payload 추출 키에 예산 인자 추가:

```python
                    action_payload = {
                        k: v
                        for k, v in args.items()
                        if k in ("action", "campaign_id", "campaign_name", "new_daily_budget_krw", "pct")
                        and v is not None
                    }
                    _VALID = ("pause", "activate", "increase_budget", "decrease_budget")
                    if action_payload.get("action") not in _VALID:
                        # 파싱 깨졌을 때 pause로 떨어뜨리지 않는다(안전 fallback 아님). 카드 미생성 →
                        # campaign_action을 세팅하지 않고 ToolMessage로 재질문을 유도한다.
                        tool_msgs.append(
                            ToolMessage(
                                content="어떤 조치인지 명확하지 않아요. 무엇을(중지/게재/예산 변경) 어느 캠페인에 할지 다시 알려 주세요.",
                                tool_call_id=tool_id,
                            )
                        )
                        return {
                            "messages": tool_msgs,
                            "sub_results": new_sub,
                            "thread_id": new_thread_id,
                            "requires_approval": new_requires,
                            # create_prefill/campaign_action 미설정 → 카드 없음, orchestrate가 정상 답변 합성
                        }
```

> `and v` → `and v is not None`로 바꾼다(예산 0·pct 0이 떨어지지 않게; 음수 pct 보존). 상태 액션엔 영향 없음.
> **[리뷰 반영] invalid action을 pause로 강등하지 않는다** — 카드 미생성 + 재질문(예산 파싱 실패 시 엉뚱한 중지 방지).

- [ ] **Step 3: 린트** — `cd backend && uv run ruff format api/assistant/deep_agent.py && uv run ruff check api/assistant/deep_agent.py`. (테스트는 Task 2에서 빌더와 함께.)

> 이 Task는 단독 커밋하지 않고 Task 2의 백엔드와 함께 적대적 리뷰 후 커밋한다.

---

## Task 2: 예산 proposal 빌더 엔드포인트 (`management.py`)

**Files:**
- Modify: `backend/api/routers/management.py`
- Test: `backend/tests/management/test_budget_proposal.py` (신규)

- [ ] **Step 1: 실패 테스트 작성** (빌더 순수 로직 — proposal 빌드·tier·hash. 라우터는 finalize만 검증)

```python
# backend/tests/management/test_budget_proposal.py
# 예산 proposal 빌더 — INCREASE/DECREASE 판정·budget 결속·hash 검증(순수, DB·LLM 미경유).
from api.routers.management import _build_budget_proposal
from domain.management.contracts.enums import ActionTier
from domain.management.contracts.schemas import verify_proposal_hash


def test_increase_proposal():
    # 빌더는 선언된 action_type을 그대로 쓴다(방향 재판정 안 함). 검증·방향강제는 엔드포인트.
    p = _build_budget_proposal(
        tenant_id="org_1", ad_account_id="act_1", campaign_id="c_1",
        action_type="INCREASE_BUDGET", budget_before_krw=40000, new_daily_budget_krw=50000,
    )
    assert p.action_type == "INCREASE_BUDGET"
    assert p.action_tier == ActionTier.TIER_3
    assert p.budget_before_krw == 40000 and p.budget_after_krw == 50000
    assert p.max_total_spend_krw == 50000 * 7
    assert verify_proposal_hash(p)


def test_decrease_proposal():
    p = _build_budget_proposal(
        tenant_id="org_1", ad_account_id="act_1", campaign_id="c_1",
        action_type="DECREASE_BUDGET", budget_before_krw=50000, new_daily_budget_krw=30000,
    )
    assert p.action_type == "DECREASE_BUDGET"
    assert p.action_tier == ActionTier.TIER_1
    assert p.budget_after_krw == 30000
```

- [ ] **Step 2: 실패 확인** — `cd backend && uv run pytest tests/management/test_budget_proposal.py -v` → FAIL (`ImportError: _build_budget_proposal`)

- [ ] **Step 3: 빌더 + 엔드포인트 구현** — `management.py`에 추가(`/pause` 근처). 빌더는 순수 함수로 분리(테스트 가능):

```python
_MIN_DAILY_BUDGET_KRW = 1_521  # 계정 floor(가능하면 campaign_policy 조회로 대체)
_MAX_DAILY_BUDGET_KRW = 100_000_000


async def _current_daily_budget(db: AsyncSession, campaign_id: str) -> int:
    """현재 일예산 정본 — created_campaigns에서 조회(없으면 0=빌더 진입 전 거부)."""
    row = (
        await db.execute(
            select(CreatedCampaign).where(CreatedCampaign.meta_campaign_id == campaign_id)
        )
    ).scalar_one_or_none()
    return int(row.daily_budget_krw) if row and row.daily_budget_krw else 0


def _build_budget_proposal(
    *, tenant_id: str, ad_account_id: str, campaign_id: str,
    action_type: str, budget_before_krw: int, new_daily_budget_krw: int, run_days: int = 7,
) -> ActionProposal:
    """선언된 action_type 그대로 정본 proposal 빌드(방향 재판정 안 함). 검증은 엔드포인트가 끝낸 상태."""
    now = datetime.now(UTC)
    return finalize_proposal(
        ActionProposal(
            proposal_id=f"prop_{uuid4().hex[:8]}",
            tenant_id=tenant_id,
            ad_account_id=ad_account_id,
            target_object_ids=(campaign_id,),
            action_type=action_type,
            action_tier=judge_tier(action_type),  # INCREASE=TIER_3, DECREASE=TIER_1
            evidence_metrics={"source": "chat", "name": campaign_id},
            metrics_as_of=now,
            hypothesis="사용자 예산 변경 요청",
            confidence=1.0,
            expected_state_version="state_v1",
            budget_before_krw=budget_before_krw,
            budget_after_krw=new_daily_budget_krw,
            max_total_spend_krw=new_daily_budget_krw * run_days,
            expires_at=now + timedelta(minutes=PROPOSAL_TTL_MINUTES),
            approval_policy_version=APPROVAL_POLICY_VERSION,
        )
    )


class BudgetProposalRequest(BaseModel):
    action: Literal["increase_budget", "decrease_budget"]  # 선언된 의도 — 서버가 방향 강제
    new_daily_budget_krw: int  # 목표 일예산(절대값 — 집행값)
    shown_budget_before_krw: int | None = None  # 카드 표시값(drift 비교용, 정본 아님)


@router.post("/campaigns/{campaign_id}/budget-proposal")
async def budget_proposal(
    campaign_id: str,
    body: BudgetProposalRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """예산 변경 proposal을 빌드해 반환(미집행). 현재 예산은 서버 정본, 방향·no-op·범위 검증 후 finalize."""
    org_id = await _require_org_id(user, db)
    await _require_owned_campaign(db, org_id, campaign_id)
    ad_account = await _require_ad_account(db, org_id)
    before = await _current_daily_budget(db, campaign_id)  # [리뷰1] 현재값은 서버 정본
    new = body.new_daily_budget_krw
    if before <= 0:
        raise HTTPException(409, "현재 일예산을 확인할 수 없어 예산 변경을 진행할 수 없어요.")
    if new < _MIN_DAILY_BUDGET_KRW or new > _MAX_DAILY_BUDGET_KRW:  # [리뷰4] 범위 검증
        raise HTTPException(
            422, f"일예산은 {_MIN_DAILY_BUDGET_KRW:,}~{_MAX_DAILY_BUDGET_KRW:,}원 사이여야 해요."
        )
    if new == before:  # [리뷰3] no-op 거부
        raise HTTPException(409, "현재 예산과 같아 변경할 게 없어요.")
    declared = "INCREASE_BUDGET" if body.action == "increase_budget" else "DECREASE_BUDGET"
    actual = "INCREASE_BUDGET" if new > before else "DECREASE_BUDGET"
    if declared != actual:  # [리뷰5] 선언 방향 ≠ 목표 방향 → 재확인
        raise HTTPException(
            409,
            f"요청({body.action})과 목표가 안 맞아요(현재 {before:,}원 → {new:,}원). 다시 확인해 주세요.",
        )
    proposal = _build_budget_proposal(
        tenant_id=str(org_id), ad_account_id=ad_account, campaign_id=campaign_id,
        action_type=declared, budget_before_krw=before, new_daily_budget_krw=new,
    )
    drift = body.shown_budget_before_krw is not None and body.shown_budget_before_krw != before
    return {"proposal": proposal.model_dump(mode="json"), "budget_before_krw": before, "drift": drift}
```

> 임포트 확인(없으면 append-only 추가): `Literal`(typing), `select`(sqlalchemy), `CreatedCampaign`(core.models), `HTTPException`(fastapi), `judge_tier`·`BaseModel`·`get_current_user`·`User`.
> **[리뷰 반영]** 현재 예산은 **서버 정본**(클라 입력 불신), no-op·범위·방향 **서버 검증**, 빌더는 선언 action을 그대로 써 **silent 방향 변경 없음**. 응답의 `budget_before_krw`(정본)·`drift`로 카드가 표시값을 갱신.

- [ ] **Step 4: 통과 확인** — `cd backend && uv run pytest tests/management/test_budget_proposal.py -v` → PASS(2)

- [ ] **Step 5: Ruff** — `cd backend && uv run ruff format . && uv run ruff check . --fix` (무관 파일이 포맷되면 되돌려 diff를 P2b로 한정).

> Task 1+2 백엔드는 **함께** 적대적 리뷰 후 커밋. (커밋 메시지: `add: P2b 예산 proposal 빌더 + manage_campaign 예산 액션`)

---

## Task 3: 프론트 — api + `ChatBudgetProposalCard`

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/components/chat/ChatBudgetProposalCard.tsx`

- [ ] **Step 1: api 메서드** — `api.management`에 추가(`approve`/`execute` 근처):

```ts
    budgetProposal: (
      campaignId: string,
      body: { action: 'increase_budget' | 'decrease_budget'; new_daily_budget_krw: number; shown_budget_before_krw?: number },
    ) =>
      request<{ proposal: Proposal; budget_before_krw: number; drift: boolean }>(
        `/management/campaigns/${campaignId}/budget-proposal`,
        { method: "POST", body: JSON.stringify(body) },
      ),
```

- [ ] **Step 2: `ChatBudgetProposalCard` 작성** — 전체 내용:

```tsx
// 챗 임베드 예산 변경 — /budget-proposal 빌드→프리뷰(현재→변경·Tier)→approve+execute→결과.
'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { Proposal, ActionResult } from '@/components/manage/types';

export type BudgetActionPayload = {
  action: 'increase_budget' | 'decrease_budget';
  campaign_id?: string;
  campaign_name?: string;
  new_daily_budget_krw?: number;
  pct?: number;
};
type PickItem = { campaign_id: string; name: string; state: string; daily_budget_krw?: number };

export default function ChatBudgetProposalCard({ action }: { action: BudgetActionPayload }) {
  const [campaignId, setCampaignId] = useState(action.campaign_id ?? '');
  const [before, setBefore] = useState<number | null>(null);
  const [picker, setPicker] = useState<PickItem[]>([]);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [result, setResult] = useState<ActionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 캠페인 목록(선택기 + 현재 예산 출처).
  useEffect(() => {
    api.management
      .campaigns()
      .then((r) => setPicker((r.campaigns ?? []) as PickItem[]))
      .catch(() => setPicker([]));
  }, []);

  // 선택된 캠페인의 현재 일예산을 목록에서 집는다.
  useEffect(() => {
    const c = picker.find((p) => p.campaign_id === campaignId);
    if (c?.daily_budget_krw != null) setBefore(c.daily_budget_krw);
  }, [campaignId, picker]);

  // 목표 예산 = 발화의 절대값 우선, 없으면 pct로 환산.
  const target =
    action.new_daily_budget_krw ??
    (before != null && action.pct != null ? Math.round(before * (1 + action.pct / 100)) : null);

  const review = async () => {
    if (!campaignId || before == null || target == null) return;
    setBusy(true);
    setError(null);
    try {
      const { proposal: p } = await api.management.budgetProposal(campaignId, {
        budget_before_krw: before,
        new_daily_budget_krw: target,
      });
      setProposal(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : '제안 생성 실패');
    } finally {
      setBusy(false);
    }
  };

  const execute = async () => {
    if (!proposal) return;
    setBusy(true);
    setError(null);
    try {
      const a = (await api.management.approve(proposal, true)) as { approved_action: unknown };
      const resp = (await api.management.execute(a.approved_action, proposal)) as {
        result: ActionResult;
        error_message?: string;
      };
      setResult(resp.result);
      if (resp.error_message) setError(resp.error_message);
    } catch (e) {
      setError(e instanceof Error ? e.message : '집행 실패');
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    const ok = result.status === 'success' || result.status === 'pending_review';
    return (
      <div className="mt-1 rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-4 max-w-md">
        <p className={`font-bold ${ok ? 'text-[#191F28] dark:text-[#F2F4F6]' : 'text-red-500'}`}>
          {ok ? '✓ 예산을 변경했어요' : '예산 변경 실패'}
        </p>
        {!ok && <p className="mt-1 text-sm text-[#8B95A1]">{error ?? `사유 ${result.failure_reason ?? '알 수 없음'}`}</p>}
        {ok && result.approval_id && <p className="mt-1 text-[11px] text-[#B0B8C1]">승인 ID: {result.approval_id}</p>}
        <Link href="/manage/campaigns" className="mt-3 inline-block px-3 py-1.5 bg-[#3182F6] text-white text-xs font-medium rounded-lg">
          대시보드로
        </Link>
      </div>
    );
  }

  return (
    <div className="mt-1 rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-4 max-w-md">
      <p className="font-bold text-[#191F28] dark:text-[#F2F4F6] mb-2">
        예산 {action.action === 'increase_budget' ? '증액' : '감액'}
      </p>

      {!action.campaign_id && (
        <select
          value={campaignId}
          onChange={(e) => setCampaignId(e.target.value)}
          className="mb-2 w-full rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent px-3 py-2 text-sm"
        >
          <option value="">캠페인 선택</option>
          {picker.map((c) => (
            <option key={c.campaign_id} value={c.campaign_id}>{c.name} ({c.state})</option>
          ))}
        </select>
      )}

      {before != null && target != null ? (
        <p className="text-sm text-[#4E5968] dark:text-[#9CA3AF] mb-2">
          일 예산 <b>{before.toLocaleString()}원</b> → <b className="text-[#3182F6]">{target.toLocaleString()}원</b>
          <span className="block text-[11px] text-[#8B95A1] mt-0.5">7일 기준 예상 최대 지출 {(target * 7).toLocaleString()}원</span>
        </p>
      ) : (
        <p className="text-xs text-[#8B95A1] mb-2">캠페인과 목표 예산을 확인할 수 없어요.</p>
      )}

      {!proposal ? (
        <button
          onClick={review}
          disabled={busy || !campaignId || before == null || target == null}
          className="px-4 py-2 bg-[#3182F6] text-white text-sm font-medium rounded-lg disabled:opacity-40"
        >
          {busy ? '준비 중…' : '검토·승인'}
        </button>
      ) : (
        <div className="flex gap-2">
          <button onClick={execute} disabled={busy} className="px-4 py-2 bg-[#3182F6] text-white text-sm font-medium rounded-lg disabled:opacity-40">
            {busy ? '집행 중…' : '집행'}
          </button>
          <button onClick={() => setProposal(null)} disabled={busy} className="px-4 py-2 border border-[#E5E8EB] dark:border-[#2D3748] text-sm rounded-lg disabled:opacity-40">
            취소
          </button>
        </div>
      )}
      {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
    </div>
  );
}
```

> **검증(Task 0 식):** `state` 필드는 P2에서 확인됨. radius/톤은 `CreateProposalPreview` 따른다.
>
> **[리뷰 반영] 카드 필수 변경(위 코드를 기준으로 적용):**
> 1. **현재 예산은 서버 정본** — 카드는 list의 예산을 신뢰하지 않는다. `review()`가 `budgetProposal(id, { action: action.action, new_daily_budget_krw: target, shown_budget_before_krw: before ?? undefined })`를 호출하고, **응답의 `budget_before_krw`(정본)로 `before`를 갱신**한 뒤 프리뷰(현재→변경)를 그 값으로 그린다. `drift===true`면 "현재 예산이 갱신됐어요" 한 줄 표시.
> 2. **목표 예산 입력 필드(리뷰6)** — `action.new_daily_budget_krw`·`pct`가 둘 다 없으면 `target`이 null이라 진행 불가 → **숫자 입력 필드**(`manualTarget` state)를 두어 사용자가 목표 일예산을 입력하게 한다. "예산 좀 내려줘"(목표 없음)도 카드에서 진행 가능해야 함.
> 3. **증액 문구(리뷰7)** — `action.action === 'increase_budget'`이면 프리뷰에 "일 예산이 증가해 추가 지출이 발생할 수 있어요" 안내를 둔다(별도 ack 아님, 프리뷰 문구).
> 4. **방향/검증 에러 표면** — 서버가 422/409(범위·no-op·방향불일치)면 그 메시지를 카드 에러로 보여주고 `proposal` 미설정 유지(집행 버튼 안 뜸).
> 5. `daily_budget_krw`를 list에서 못 얻어도 무방 — 현재값은 `review()` 응답으로 받는다(서버 정본).

- [ ] **Step 3: 린트·빌드** — `cd frontend && pnpm lint && pnpm build` → 통과.

---

## Task 4: 프론트 배선 (`chat/page.tsx`)

**Files:** Modify `frontend/src/app/(app)/chat/page.tsx`

- [ ] **Step 1: import + 타입**

```tsx
import ChatBudgetProposalCard, { type BudgetActionPayload } from '@/components/chat/ChatBudgetProposalCard';
```

`embed` 유니온 확장 + `action` 타입 확장(P2의 `CampaignActionPayload`와 합). `SourceMeta`/`Message`의 `action?`을 두 페이로드 합집합으로:

```tsx
  embed?: 'create_campaign' | 'campaign_action';
  action?: CampaignActionPayload | BudgetActionPayload;
```

> `manage_campaign` 툴이 4개 action을 모두 `embed='campaign_action'`로 내므로 embed는 그대로 `'campaign_action'`. 카드 분기는 `action.action` 값으로 한다.

- [ ] **Step 2: 렌더 분기** — P2의 `campaign_action` 렌더 분기를 action별로 가른다:

```tsx
                      {msg.role === 'assistant' && msg.embed === 'campaign_action' && msg.action &&
                        (msg.action.action === 'increase_budget' || msg.action.action === 'decrease_budget' ? (
                          <ChatBudgetProposalCard action={msg.action as BudgetActionPayload} />
                        ) : (
                          <ChatCampaignActionCard action={msg.action as CampaignActionPayload} />
                        ))}
```

> 기존 `ChatCampaignActionCard` 단독 분기를 위 삼항으로 교체. 폭 조건(P2 리뷰 minor)에도 `campaign_action`이 포함돼 있어야 카드가 안 눌린다 — `(isCreateCampaignEmbed || msg.embed === 'campaign_action')` 확인.

- [ ] **Step 3: 린트·빌드** — `cd frontend && pnpm lint && pnpm build` → 통과.

> Task 3+4 프론트는 함께 적대적 리뷰 후 커밋. (커밋 메시지: `add: P2b 챗 예산 변경 카드(검토·승인→집행)`)

---

## Task 5: 수동 검증 (이미지 재현)

- [ ] **Step 1: 서버 기동 + 로그인.**
- [ ] **Step 2: 시나리오** — `/chat`:
  1. **"가을세일 캠페인 예산 25% 올려줘"** → 카드에 **현재→변경 예산**(예 40,000 → 50,000) + 7일 예상 최대 지출 표시 → "검토·승인" → "집행" → ✓ + 승인 ID.
  2. **"예산 5만원으로 올려줘"**(절대값) → target=50,000으로 표시.
  3. 이름 미언급 → 캠페인 선택기 → "검토·승인" 시 **서버 정본 현재 예산**으로 프리뷰 갱신.
  4. **"이 캠페인 예산 좀 내려줘"**(목표 없음) → **카드에서 목표 예산 입력** → 감액(DECREASE, TIER_1).
- [ ] **Step 3: 검증 거부 케이스** — (a) 목표=현재 동일 → no-op 거부 메시지, (b) "증액인데 더 낮은 값" → 방향불일치 거부, (c) 0·음수·과대값 → 범위 거부. 모두 카드 에러로 표시되고 집행 버튼 안 뜸.
- [ ] **Step 4: 승인 동등성(§3)** — `/execute` 결과 `approval_id`·집행 후 대시보드 예산이 `budget_after`로 바뀌었는지. 증액 프리뷰에 추가지출 문구가 보이는지.
- [ ] **Step 5: 회귀** — pause/activate(P2)·create(P1.5)·일반 질문 정상.

> **P3 예고:** REPLACE_CREATIVE(소재 후보 출처)·EXPAND_AUDIENCE·CHANGE_BID_STRATEGY는 각 신규 프리뷰 + 파라미터가 필요 — 별도 plan(이 카드·툴 패턴 재사용).
