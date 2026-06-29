# P2 — 챗 캠페인 상태 조치(PAUSE·ACTIVATE) 임베드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`).
> **루프 규칙(이 레포):** 서브에이전트 구현 → **커밋 전** 적대적 리뷰(`/codex:adversarial-review`는 사용자가 실행) → 사소한 수정은 인라인·어려운 건 `/codex:rescue` → 커밋.

**Goal:** 챗에서 "이 캠페인 중지해줘 / 게재 시작해줘"류 발화로 캠페인을 **일시중지(PAUSE)·게재시작(ACTIVATE)** 할 수 있게, 오케스트레이터에 `manage_campaign` 툴을 추가하고 챗 카드(확인 → 기존 `/pause`·`/activate` 호출)를 임베드한다. ACTIVATE는 실과금 확인을 카드에 둔다.

**Architecture:** P1.5와 동일한 deepagents-ready 패턴 — 인텐트는 오케스트레이터(`deep_agent.py`) **툴**. `manage_campaign(campaign_id?, action)` 툴이 `meta.embed='campaign_action'` + `{action, campaign_id?, campaign_name?}` 신호만 낸다(DB 미접촉). 프론트가 `ChatCampaignActionCard`를 렌더 — campaign_id가 없으면 **캠페인 선택기**(기존 목록 재사용), 확인하면 **기존 정식 엔드포인트** `api.management.pause(id)` / `activate(id)`를 호출(이 엔드포인트들이 내부에서 proposal+approve+execute 수행). **`chat.py`·executor·정식 엔드포인트 미수정.** 이 툴이 deepagents 이식 연결점.

**Tech Stack:** FastAPI·LangGraph(`deep_agent.py`)·Next.js/TS·Tailwind. 백엔드 순수 함수는 pytest, 프론트는 `pnpm lint`+`pnpm build`+수동.

**상위 설계:** `docs/superpowers/specs/2026-06-29-chat-campaign-actions-reuse-overview-design.md`(P2). **선행:** P1·P1.5 완료(`ChatCreateCampaignCard`·`create_campaign` 툴·embed 렌더 존재). **다음:** P2b(예산 INCREASE/DECREASE — 이 plan의 카드·툴·선택기 재사용 + proposal 빌더).

---

## 참조 — 기존 코드 (구현 중 의존, 미수정)

- 백엔드:
  - `backend/api/assistant/deep_agent.py` — `_TOOL_SPECS`·`_SYS_ORCHESTRATOR`·`_OState`·`orchestrate`(create_prefill short-circuit 패턴)·`dispatch`(create_campaign early-return 패턴)·`_state_to_result`(create_prefill→embed/prefill 합성, source를 deep-agent로 고정하는 블록). **P1.5에서 `create_campaign`을 추가한 그 자리 옆에 `manage_campaign`을 같은 방식으로 추가.**
  - `backend/api/routers/management.py` — `POST /campaigns/{id}/pause`(PAUSE proposal+approve+execute 한 방), `POST /campaigns/{id}/activate`(ACTIVATE, commit/credit 게이트). **호출만, 미수정.**
- 프론트:
  - `api.management.pause(campaignId)` → `{ paused: boolean, result, error_message? }`.
  - `api.management.activate(campaignId, commitKrw?)` → `{ serving: boolean, result, balance_krw, credit_krw, commit_krw, causes }`(`commitKrw` 선택).
  - `api.management.campaigns(...)` → 캠페인 목록(선택기 재사용). 항목에 `campaign_id`·`name`·`status` 존재(`components/manage/types.ts` `Campaign`).
  - `chat/page.tsx` — `SourceMeta`/`Message`(`embed?`·`prefill?`), SSE `data.meta` 분기(P1.5에서 `const meta = data.meta` 호이스트), 렌더 분기.

---

## File Structure

| 파일 | 신규/수정 | 책임 |
|---|---|---|
| `backend/api/assistant/deep_agent.py` | 수정 | `manage_campaign` 툴 스펙·시스템 프롬프트·`campaign_action` 상태·orchestrate/dispatch 분기·`_state_to_result` 합성 |
| `backend/tests/management/test_manage_campaign_tool.py` | 신규 | `_state_to_result`가 `campaign_action` 싣는지 |
| `frontend/src/components/chat/ChatCampaignActionCard.tsx` | 신규 | 확인 카드(+캠페인 선택기·실과금 확인)→`pause`/`activate`→결과 |
| `frontend/src/app/(app)/chat/page.tsx` | 수정 | `SourceMeta`/`Message`에 `action` 필드 + SSE meta→action set + 렌더 분기 |

---

## Task 1: 오케스트레이터 `manage_campaign` 툴 (`deep_agent.py`)

**Files:**
- Modify: `backend/api/assistant/deep_agent.py`
- Test: `backend/tests/management/test_manage_campaign_tool.py` (신규)

- [ ] **Step 1: 실패 테스트 작성**

```python
# backend/tests/management/test_manage_campaign_tool.py
# manage_campaign 툴 결과가 meta.embed='campaign_action' + action 페이로드로 합성되는지.
from langchain_core.messages import AIMessage

from api.assistant.deep_agent import _state_to_result


def _state(action):
    return {
        "messages": [AIMessage(content="요청을 확인했어요.")],
        "sub_results": {},
        "requires_approval": False,
        "thread_id": None,
        "create_prefill": None,
        "campaign_action": action,
    }


def test_state_to_result_carries_campaign_action():
    result = _state_to_result(_state({"action": "pause", "campaign_id": "c_1", "campaign_name": "가을세일"}))
    assert result.meta["embed"] == "campaign_action"
    assert result.meta["action"] == {"action": "pause", "campaign_id": "c_1", "campaign_name": "가을세일"}
    assert result.meta["source"] == "deep-agent"  # management 게이트 오발동 방지


def test_state_to_result_no_action_has_no_embed():
    result = _state_to_result(_state(None))
    assert "embed" not in result.meta
```

- [ ] **Step 2: 실패 확인** — `cd backend && uv run pytest tests/management/test_manage_campaign_tool.py -v` → FAIL (`KeyError: 'campaign_action'`)

- [ ] **Step 3a: `_TOOL_SPECS`에 툴 추가** (리스트 끝):

```python
    {
        "name": "manage_campaign",
        "description": (
            "기존 캠페인의 상태를 바꾸는 요청에 호출한다 — 일시중지(action='pause')·게재 시작(action='activate')."
            " 캠페인을 특정할 수 있으면 campaign_id를 채우고, 모르면 비워둔다(사용자가 카드에서 고른다)."
            " 예산 변경·생성엔 호출하지 않는다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["pause", "activate"]},
                "campaign_id": {"type": "string", "description": "대상 캠페인 ID(알면)"},
                "campaign_name": {"type": "string", "description": "사용자가 말한 캠페인 이름(있으면)"},
            },
            "required": ["action"],
        },
    },
```

- [ ] **Step 3b: 시스템 프롬프트 1줄** — `_SYS_ORCHESTRATOR` 규칙 목록에:

```
- 기존 캠페인 일시중지·게재 시작 요청 → manage_campaign 호출(action=pause|activate, 알면 campaign_id)
```

- [ ] **Step 3c: `_OState`에 필드 추가**:

```python
    campaign_action: dict | None  # manage_campaign 툴 페이로드(action·campaign_id·campaign_name)
```

- [ ] **Step 3d: `orchestrate` short-circuit 확장** — P1.5에서 넣은 `if state.get("create_prefill") is not None:` 블록 **다음**에 추가:

```python
        if state.get("campaign_action") is not None:
            return {
                "messages": [
                    AIMessage(content="요청하신 캠페인 조치를 확인 카드로 준비했어요. 확인해 주세요.")
                ],
                "iteration": state["iteration"] + 1,
            }
```

- [ ] **Step 3e: `dispatch`에 `create_campaign` 분기 다음에 추가**:

```python
                elif name == "manage_campaign":
                    action_payload = {
                        k: v
                        for k, v in args.items()
                        if k in ("action", "campaign_id", "campaign_name") and v
                    }
                    if action_payload.get("action") not in ("pause", "activate"):
                        action_payload["action"] = "pause"  # enum 밖이면 보수적으로 pause(역방향·안전)
                    tool_msgs.append(
                        ToolMessage(content="조치 확인 카드를 준비했습니다.", tool_call_id=tool_id)
                    )
                    return {
                        "messages": tool_msgs,
                        "sub_results": new_sub,
                        "thread_id": new_thread_id,
                        "requires_approval": new_requires,
                        "campaign_action": action_payload,
                    }
```

- [ ] **Step 3f: `run` 초기 상태에 추가**: `"campaign_action": None,`

- [ ] **Step 3g: `_state_to_result`에 합성** — create_prefill 블록 **다음**에 추가:

```python
    if state.get("campaign_action") is not None:
        combined_meta["embed"] = "campaign_action"
        combined_meta["action"] = state["campaign_action"]
        combined_meta["source"] = "deep-agent"
```

> 주의: `_state_to_result`는 이미 `state.get("create_prefill")`을 쓰므로 `.get("campaign_action")`도 최소 state(테스트)·실제 `_OState` 모두 안전.

- [ ] **Step 4: 통과 확인** — `cd backend && uv run pytest tests/management/test_manage_campaign_tool.py -v` → PASS(2)

- [ ] **Step 5: Ruff + (커밋 전 적대적 리뷰 후) 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
# (여기서 /codex:adversarial-review — 사용자 실행 — 통과 후)
git add backend/api/assistant/deep_agent.py backend/tests/management/test_manage_campaign_tool.py
git commit -m "add: P2 오케스트레이터 manage_campaign 툴(pause/activate 확인 카드 신호)"
```

(본문 끝에 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.)

---

## Task 2: `ChatCampaignActionCard` 컴포넌트 (확인·선택기·실과금·결과)

**Files:**
- Create: `frontend/src/components/chat/ChatCampaignActionCard.tsx`

- [ ] **Step 1: 컴포넌트 작성** — 전체 내용:

```tsx
// 챗 임베드 캠페인 상태 조치 — 확인(+캠페인 선택기·실과금)→기존 pause/activate 호출→결과.
'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';

export type CampaignActionPayload = {
  action: 'pause' | 'activate';
  campaign_id?: string;
  campaign_name?: string;
};

type Phase = 'confirm' | 'running' | 'done';
type PickItem = { campaign_id: string; name: string; status: string };

const LABEL: Record<CampaignActionPayload['action'], string> = {
  pause: '일시중지',
  activate: '게재 시작',
};

export default function ChatCampaignActionCard({ action }: { action: CampaignActionPayload }) {
  const [phase, setPhase] = useState<Phase>('confirm');
  const [campaignId, setCampaignId] = useState(action.campaign_id ?? '');
  const [picker, setPicker] = useState<PickItem[]>([]);
  const [ackBilling, setAckBilling] = useState(false); // activate 실과금 확인
  const [ok, setOk] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  // campaign_id가 없으면 선택기용 목록을 불러온다(기존 캠페인 API 재사용).
  useEffect(() => {
    if (campaignId) return;
    api.management
      .campaigns()
      .then((r) => {
        const list = (r.campaigns ?? []) as PickItem[];
        setPicker(list);
      })
      .catch(() => setPicker([]));
  }, [campaignId]);

  const needsAck = action.action === 'activate';
  const canRun = !!campaignId && (!needsAck || ackBilling) && phase === 'confirm';

  const run = async () => {
    if (!campaignId) return;
    setPhase('running');
    setError(null);
    try {
      if (action.action === 'pause') {
        const r = (await api.management.pause(campaignId)) as { paused: boolean; error_message?: string };
        setOk(r.paused);
        if (!r.paused && r.error_message) setError(r.error_message);
      } else {
        const r = (await api.management.activate(campaignId)) as {
          serving: boolean;
          causes?: { code: string; message: string }[];
        };
        setOk(r.serving);
        if (!r.serving) setError((r.causes ?? []).map((c) => c.message).join(' / ') || '게재를 시작하지 못했어요.');
      }
      setPhase('done');
    } catch (e) {
      setError(e instanceof Error ? e.message : '요청 중 문제가 발생했어요.');
      setPhase('done');
    }
  };

  if (phase === 'done') {
    return (
      <div className="mt-1 rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-4 max-w-md">
        {ok ? (
          <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">
            ✓ {LABEL[action.action]} 완료
          </p>
        ) : (
          <>
            <p className="font-bold text-red-500">{LABEL[action.action]} 실패</p>
            <p className="mt-1 text-sm text-[#8B95A1]">{error ?? '처리되지 않았어요.'}</p>
          </>
        )}
        <Link
          href="/manage/campaigns"
          className="mt-3 inline-block px-3 py-1.5 bg-[#3182F6] text-white text-xs font-medium rounded-lg hover:bg-[#1B6EEB]"
        >
          대시보드로
        </Link>
      </div>
    );
  }

  return (
    <div className="mt-1 rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-4 max-w-md">
      <p className="font-bold text-[#191F28] dark:text-[#F2F4F6] mb-2">캠페인 {LABEL[action.action]}</p>

      {!action.campaign_id ? (
        <label className="block mb-2">
          <span className="text-xs text-[#8B95A1]">대상 캠페인</span>
          <select
            value={campaignId}
            onChange={(e) => setCampaignId(e.target.value)}
            className="mt-1 w-full rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent px-3 py-2 text-sm"
          >
            <option value="">선택하세요</option>
            {picker.map((c) => (
              <option key={c.campaign_id} value={c.campaign_id}>
                {c.name} ({c.status})
              </option>
            ))}
          </select>
        </label>
      ) : (
        <p className="text-sm text-[#4E5968] dark:text-[#9CA3AF] mb-2">
          {action.campaign_name ?? action.campaign_id}
        </p>
      )}

      {needsAck && (
        <label className="flex items-start gap-2 text-xs text-[#4E5968] dark:text-[#9CA3AF] mb-2">
          <input type="checkbox" checked={ackBilling} onChange={(e) => setAckBilling(e.target.checked)} className="mt-0.5" />
          <span>이 작업은 지금부터 실제 과금이 시작됩니다 — 이해했습니다.</span>
        </label>
      )}

      <button
        onClick={run}
        disabled={!canRun}
        className="px-4 py-2 bg-[#3182F6] text-white text-sm font-medium rounded-lg hover:bg-[#1B6EEB] disabled:opacity-40"
      >
        {phase === 'running' ? '처리 중…' : LABEL[action.action]}
      </button>
      {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
    </div>
  );
}
```

> **검증 항목(Task 0 식):** 구현 전 `api.management.campaigns()` 반환이 `{ campaigns: [...] }`이고 항목에 `campaign_id`/`name`/`status`가 있는지, `pause`/`activate` 반환 형태(`paused`/`serving`)가 위 가정과 맞는지 실제 소스로 확인하고 다르면 맞춘다.

- [ ] **Step 2: 린트·빌드** — `cd frontend && pnpm lint && pnpm build` → 통과(미사용 import 경고 없게).

- [ ] **Step 3: (적대적 리뷰 후) 커밋**

```bash
git add frontend/src/components/chat/ChatCampaignActionCard.tsx
git commit -m "add: P2 챗 캠페인 상태 조치 카드(확인·선택기·실과금)"
```

---

## Task 3: `chat/page.tsx` 배선 (action meta 렌더)

**Files:**
- Modify: `frontend/src/app/(app)/chat/page.tsx`

- [ ] **Step 1: import + 타입**

상단:

```tsx
import ChatCampaignActionCard, { type CampaignActionPayload } from '@/components/chat/ChatCampaignActionCard';
```

`type SourceMeta` 에 추가(이미 `embed?`·`prefill?` 있음):

```tsx
  action?: CampaignActionPayload; // manage_campaign 툴 페이로드
```

`type Message` 에 추가:

```tsx
  embed?: 'create_campaign' | 'campaign_action'; // 기존 'create_campaign'에 'campaign_action' 추가
  action?: CampaignActionPayload;
```

> 기존 `embed?: 'create_campaign'` 선언을 위 유니온으로 교체한다.

- [ ] **Step 2: SSE meta 분기에 campaign_action 반영** — P1.5에서 만든 `if (meta.embed === 'create_campaign')` 분기 **다음**(같은 `else if (data.meta)` 블록 안)에 추가:

```tsx
                if (meta.embed === 'campaign_action') {
                  patch.embed = 'campaign_action';
                  patch.action = meta.action;
                }
```

> `meta`는 P1.5에서 호이스트한 `const meta = data.meta;` 를 그대로 쓴다.

- [ ] **Step 3: 렌더 분기** — P1.5의 `isCreateCampaignEmbed && <ChatCreateCampaignCard .../>` **다음**에 추가:

```tsx
                      {msg.role === 'assistant' && msg.embed === 'campaign_action' && msg.action && (
                        <ChatCampaignActionCard action={msg.action} />
                      )}
```

> `isCreateCampaignEmbed`(= `msg.embed === 'create_campaign'`)는 그대로. 빈 버블 가드(`shouldRenderBubble`)는 `embed`가 truthy면 이미 숨기므로 campaign_action도 자동 적용된다(별도 수정 불필요 — 확인만).

- [ ] **Step 4: 린트·빌드** — `cd frontend && pnpm lint && pnpm build` → 통과.

- [ ] **Step 5: (적대적 리뷰 후) 커밋**

```bash
git add "frontend/src/app/(app)/chat/page.tsx"
git commit -m "add: P2 챗 campaign_action 카드 렌더 배선"
```

---

## Task 4: 수동 검증

**Files:** 없음.

- [ ] **Step 1: 서버 기동** + 로그인.
- [ ] **Step 2: 시나리오** — `/chat`에서:
  1. **"가을세일 캠페인 일시중지해줘"**(이름 언급) → 확인 카드(대상 표시) → "일시중지" → ✓ 완료. `/manage/campaigns`에서 PAUSED 확인.
  2. **"캠페인 하나 중지해줘"**(이름 없음) → 카드에 **캠페인 선택기** 등장 → 선택 후 중지.
  3. **"이 캠페인 게재 시작해줘"** → **실과금 확인 체크박스** 보임, 체크 전엔 버튼 비활성 → 체크 후 게재. 크레딧/잔액 부족이면 사유 표시.
  4. **"이 캠페인 성과 어때?"** → 카드 안 뜨고 일반 답변(오발동 없음).
- [ ] **Step 3: 회귀** — P1.5 생성("캠페인 만들어줘")·일반 management 질문이 여전히 정상인지(오케스트레이터 라우팅 회귀 없음).
- [ ] **Step 4: 결과 기록.**

> **P2b 예고(범위 밖):** INCREASE/DECREASE는 직접 엔드포인트가 없어 **proposal 빌더 신설 + 프리뷰 카드**(이미지의 "검토·승인 → 집행")가 필요 — 이 plan의 `manage_campaign` 툴·`ChatCampaignActionCard`·선택기를 재사용해 별도 plan에서 얹는다.
