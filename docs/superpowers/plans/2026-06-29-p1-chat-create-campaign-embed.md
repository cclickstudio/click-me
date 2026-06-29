# P1 — 챗 카드 신규 캠페인 생성 임베드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매니지먼트 챗에서 사용자가 신규 캠페인을 만들 수 있게, 기존 `CampaignForm` + `CreateProposalPreview` + 정식 `/create-proposal`·`/approve`·`/execute`를 **챗 카드에 임베드**한다. 사람이 프리뷰에서 승인해야 생성된다(PAUSED).

**Architecture:** 프론트엔드 전용. 자족형 컴포넌트 `ChatCreateCampaignCard`(폼→프리뷰→결과 상태기계)를 새로 만들고, `chat/page.tsx`가 트리거(퀵 액션 버튼)로 그 카드를 대화에 인라인 렌더한다. 백엔드·API·기존 컴포넌트는 **미수정**(재사용만). 진단 파이프라인·spec3 브릿지·DB 마이그레이션 없음(엄브렐러 §4-C).

**Tech Stack:** Next.js(App Router, TS) · Tailwind · 기존 `@/lib/api` `management` 메서드. **프론트는 단위 테스트 하니스가 없으므로** 각 태스크는 `pnpm lint` + `pnpm build` 통과 + 수동 확인으로 검증한다(코드베이스 기존 관행).

**상위 설계:** `docs/superpowers/specs/2026-06-29-chat-campaign-actions-reuse-overview-design.md` (P1).

---

## 참조 — 재사용할 기존 시그니처 (구현 중 의존, 미수정)

- `@/components/manage/campaigns/CampaignForm` — `CampaignForm({ onSubmit: (v: CampaignFormValues) => void, busy: boolean })`. `CampaignFormValues = { name, objective:'traffic'|'leads', daily_budget_krw, run_days, creative_ad_id?, image_hash?, special_ad_category, country, age_min, age_max, gender }`.
- `@/components/manage/campaigns/CreateProposalPreview` — `CreateProposalPreview({ proposal: Proposal, onApprove: () => void, onCancel: () => void, busy: boolean })`.
- `@/components/manage/types` — `Proposal`, `ActionResult`(`{ result_id, approval_id, status, failure_reason, idempotency_key, platform_response_snapshot? }`).
- `@/lib/api` `api.management`:
  - `createCampaignProposal(body) → { proposal: Proposal }` (body = `CampaignFormValues` 형태).
  - `approve(proposal: unknown, approved: boolean) → { status, approved_action }`.
  - `execute(approved_action: unknown, proposal: unknown) → { result: ActionResult, error_message? }`.
- 트리거를 붙일 화면: `frontend/src/app/(app)/chat/page.tsx`. 이 페이지는 인증된 `(app)` 레이아웃 하위라 로그인 컨텍스트가 보장된다(정식 엔드포인트 인증 충족).

> **참고(범위 밖):** 생성 직후 게재 시작(ACTIVATE)·충전 흐름은 P1에서 다루지 않는다. 생성은 PAUSED까지. 게재는 `ACTIVATE_CAMPAIGN`(P2). LLM 폼 prefill·발화 인텐트 라우팅은 P1.5 후속(아래 Task 4 노트).

---

## File Structure

| 파일 | 신규/수정 | 책임 |
|---|---|---|
| `frontend/src/components/chat/ChatCreateCampaignCard.tsx` | 신규 | 챗 임베드 생성 플로우(폼→프리뷰→결과). 기존 컴포넌트·api 재사용 |
| `frontend/src/app/(app)/chat/page.tsx` | 수정 | `Message.embed` 타입 + 임베드 렌더 + 퀵 액션 트리거 |

---

## Task 1: `ChatCreateCampaignCard` 컴포넌트 (자족형 생성 플로우)

**Files:**
- Create: `frontend/src/components/chat/ChatCreateCampaignCard.tsx`

- [ ] **Step 1: 컴포넌트 작성**

`frontend/src/components/chat/ChatCreateCampaignCard.tsx` 전체 내용:

```tsx
// 챗 카드에 임베드하는 신규 캠페인 생성 플로우 — 폼→프리뷰→승인·집행→결과. 정식 엔드포인트 재사용.
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { CampaignForm, type CampaignFormValues } from '@/components/manage/campaigns/CampaignForm';
import { CreateProposalPreview } from '@/components/manage/campaigns/CreateProposalPreview';
import type { Proposal, ActionResult } from '@/components/manage/types';

type Phase = 'form' | 'preview' | 'done';

export default function ChatCreateCampaignCard() {
  const [phase, setPhase] = useState<Phase>('form');
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [result, setResult] = useState<ActionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 폼 제출 → 정식 /create-proposal 로 제안 생성(아직 미집행).
  const createProposal = async (v: CampaignFormValues) => {
    setBusy(true);
    setError(null);
    try {
      const { proposal: p } = await api.management.createCampaignProposal(v);
      setProposal(p);
      setPhase('preview');
    } catch (e) {
      setError(e instanceof Error ? e.message : '제안 생성 실패');
    } finally {
      setBusy(false);
    }
  };

  // 프리뷰 승인 → 정식 /approve + /execute (사람 승인 게이트). 생성은 PAUSED 까지.
  const approveAndExecute = async () => {
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
      if (resp.error_message) setError(resp.error_message); // Meta 거부 사유 등
      setPhase('done');
    } catch (e) {
      setError(e instanceof Error ? e.message : '승인·생성 실패');
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setProposal(null);
    setResult(null);
    setError(null);
    setPhase('form');
  };

  if (phase === 'form') {
    return (
      <div className="mt-1">
        <CampaignForm onSubmit={createProposal} busy={busy} />
        {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
      </div>
    );
  }

  if (phase === 'preview' && proposal) {
    return (
      <div className="mt-1">
        <CreateProposalPreview
          proposal={proposal}
          onApprove={approveAndExecute}
          onCancel={reset}
          busy={busy}
        />
        {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
      </div>
    );
  }

  // done
  const success = result?.status === 'success';
  return (
    <div className="mt-1 rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-4 max-w-xl">
      {success ? (
        <>
          <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">✓ 캠페인 생성됨 (PAUSED)</p>
          <p className="mt-1 text-sm text-[#8B95A1]">대시보드에서 게재를 시작할 수 있어요.</p>
        </>
      ) : (
        <>
          <p className="font-bold text-red-500">생성 실패</p>
          <p className="mt-1 text-sm text-[#8B95A1]">
            {error ?? `사유 코드 ${result?.failure_reason ?? '알 수 없음'}`}
          </p>
        </>
      )}
      <div className="mt-3 flex gap-2">
        <Link
          href="/manage/campaigns"
          className="px-3 py-1.5 bg-[#3182F6] text-white text-xs font-medium rounded-lg hover:bg-[#1B6EEB]"
        >
          대시보드로
        </Link>
        <button
          onClick={reset}
          className="px-3 py-1.5 text-xs font-medium rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] text-[#4E5968] dark:text-[#9CA3AF]"
        >
          다시 만들기
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 린트·빌드 확인**

Run: `cd frontend && pnpm lint && pnpm build`
Expected: 통과(이 컴포넌트는 아직 어디서도 import 안 하므로 트리셰이킹될 수 있으나, 타입·린트 에러가 없어야 한다).

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/components/chat/ChatCreateCampaignCard.tsx
git commit -m "add: 챗 임베드 신규 캠페인 생성 카드(폼→프리뷰→집행) — P1"
```

---

## Task 2: `chat/page.tsx`에 임베드 렌더 배선

**Files:**
- Modify: `frontend/src/app/(app)/chat/page.tsx`

- [ ] **Step 1: import 추가**

`chat/page.tsx` 상단 import 블록(다른 컴포넌트 import 근처)에 추가:

```tsx
import ChatCreateCampaignCard from '@/components/chat/ChatCreateCampaignCard';
```

- [ ] **Step 2: `Message` 타입에 `embed` 필드 추가**

`type Message = {` 정의를 찾아(현재 `role`·`content`·`meta` 보유) `embed`를 추가:

```tsx
type Message = {
  role: 'user' | 'assistant';
  content: string;
  meta?: SourceMeta;
  embed?: 'create_campaign'; // 임베드 카드 종류(P1: 신규 캠페인 생성)
};
```

- [ ] **Step 3: 빈 assistant 메시지 skip 조건 보정**

렌더 루프에서 빈 assistant placeholder를 숨기는 줄을 찾는다(현재):

```tsx
if (msg.role === 'assistant' && msg.content === '') return null;
```

임베드 메시지는 content가 비어도 렌더해야 하므로 다음으로 교체:

```tsx
if (msg.role === 'assistant' && msg.content === '' && !msg.embed) return null;
```

- [ ] **Step 4: 임베드 카드 렌더**

assistant 메시지 본문(메시지 버블) 영역에서, 마크다운 버블을 렌더하는 분기 근처에 임베드 분기를 추가한다. 메시지 버블 렌더 `{msg.role === 'user' ? msg.content : renderMarkdown(msg.content)}` 가 들어있는 div **바로 다음**에, 같은 컬럼(`flex flex-col` 컨테이너) 안쪽에 추가:

```tsx
{msg.role === 'assistant' && msg.embed === 'create_campaign' && (
  <ChatCreateCampaignCard />
)}
```

> 빈 content인 임베드 메시지는 버블이 비어 보일 수 있다. 버블 자체를 숨기려면 버블 div를 `{(msg.content || !msg.embed) && (<div className="...버블...">...</div>)}` 로 감싸도 되지만, P1에서는 선택. 최소 변경은 위 추가만으로 충분(빈 버블 위에 카드가 렌더됨).

- [ ] **Step 5: 린트·빌드 확인**

Run: `cd frontend && pnpm lint && pnpm build`
Expected: 통과. (아직 트리거가 없어 카드는 화면에 안 뜨지만 타입·참조가 맞아야 한다.)

- [ ] **Step 6: 커밋**

```bash
git add frontend/src/app/(app)/chat/page.tsx
git commit -m "edit: 챗에 신규 캠페인 생성 카드 임베드 렌더 배선 — P1"
```

---

## Task 3: 생성 카드 트리거 (퀵 액션 버튼)

**Files:**
- Modify: `frontend/src/app/(app)/chat/page.tsx`

- [ ] **Step 1: 카드를 여는 핸들러 추가**

`handleSend` 정의 근처(컴포넌트 본문 내)에 추가. 사용자 의도를 대화에 남기고, 빈 assistant 메시지에 `embed`를 실어 카드를 띄운다:

```tsx
// 신규 캠페인 생성 카드를 대화에 인라인으로 연다(퀵 액션). 백엔드 호출 없음 — 카드 내부에서 정식 흐름 호출.
const openCreateCampaign = () => {
  if (isStreaming) return;
  setMessages((prev) => [
    ...prev,
    { role: 'user', content: '새 캠페인 만들기' },
    { role: 'assistant', content: '', embed: 'create_campaign' },
  ]);
};
```

- [ ] **Step 2: 웰컴 화면에 트리거 버튼 추가**

웰컴 상태의 퀵 프롬프트 그리드(`quickPrompts.map(...)`로 버튼들을 그리는 `<div className="grid grid-cols-2 ...">`)를 찾는다. 그 그리드 **다음**에 별도 버튼을 추가:

```tsx
<button
  onClick={openCreateCampaign}
  className="mt-3 w-full max-w-lg p-4 text-left text-sm font-medium text-[#3182F6] bg-[#EBF3FF] dark:bg-[#1E3A5F] border border-[#3182F6]/30 rounded-xl hover:bg-[#DCEBFF] dark:hover:bg-[#234876] transition-all"
>
  ➕ 새 캠페인 만들기
</button>
```

- [ ] **Step 3: 대화 중에도 열 수 있는 입력창 옆 버튼 추가(선택, 최소)**

입력 바(textarea가 있는 `<div className="max-w-2xl mx-auto flex items-end gap-3">`) 안, 전송 버튼 그룹 앞에 추가:

```tsx
<button
  onClick={openCreateCampaign}
  disabled={isStreaming}
  title="새 캠페인 만들기"
  aria-label="새 캠페인 만들기"
  className="p-3 rounded-xl text-[#3182F6] bg-[#EBF3FF] dark:bg-[#1E3A5F] hover:bg-[#DCEBFF] dark:hover:bg-[#234876] disabled:opacity-30 disabled:cursor-not-allowed transition-all shrink-0 font-bold"
>
  ＋
</button>
```

- [ ] **Step 4: 린트·빌드 확인**

Run: `cd frontend && pnpm lint && pnpm build`
Expected: 통과.

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/app/(app)/chat/page.tsx
git commit -m "add: 챗 신규 캠페인 생성 트리거(웰컴·입력바 버튼) — P1"
```

---

## Task 4: 수동 검증 + 마무리

**Files:** 없음(검증 전용).

- [ ] **Step 1: 개발 서버 기동**

Run: `cd frontend && pnpm dev` (백엔드도 필요: 별도 터미널 `cd backend && uv run uvicorn api.main:app --reload --port 8000`)

- [ ] **Step 2: 수동 시나리오 확인** — 로그인 후 `/chat` 진입:
  1. 웰컴 화면 "➕ 새 캠페인 만들기" 클릭 → 대화에 사용자 메시지 + 생성 폼 카드가 인라인으로 뜬다.
  2. 폼에 이름·예산 입력 후 "제안 생성 →" → 프리뷰 카드(Tier 3 · 사람 승인)로 전환.
  3. "승인하고 생성" → 결과 카드("✓ 캠페인 생성됨 (PAUSED)" 또는 실패 사유) 표시.
  4. "다시 만들기"로 폼 복귀, "대시보드로"로 `/manage/campaigns` 이동.
  5. 입력바 "＋" 버튼으로도 카드가 열린다. 스트리밍 중엔 비활성.
  6. (확인) `/manage/campaigns` 대시보드 또는 `/manage` 에서 방금 생성된 캠페인(PAUSED)이 보인다 — 정식 경로와 동일 결과.

- [ ] **Step 3: 결과 기록**

검증 통과/이슈를 `docs/superpowers/plans/2026-06-29-p1-chat-create-campaign-embed.md` 하단 또는 커밋 메시지에 한 줄로 남긴다(예: "P1 수동 검증 통과 — 챗에서 생성→대시보드 반영 확인").

> **P1.5 후속(범위 밖, 별도 plan):**
> - **LLM 인텐트 라우팅** — "새 캠페인 만들어줘" 발화를 orchestrator(deep_agent)가 감지해 `embed:'create_campaign'` 신호를 meta로 내려주면, 퀵 버튼 없이도 대화로 카드가 열린다(backend 변경).
> - **LLM 폼 prefill** — 발화에서 이름·예산·목표를 추출해 `CampaignForm` 초기값으로 주입(`CampaignForm`에 `initial?: Partial<CampaignFormValues>` prop 추가 필요).
> - **생성 직후 게재(ACTIVATE)** — P2 `ACTIVATE_CAMPAIGN` 임베드와 함께.
