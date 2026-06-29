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
- **`ResultStatus`(백엔드 `enums.py`)** = `success` | `failed` | `rejected` | `pending_review`(Meta 비동기 심사). 즉
  생성 결과는 `success`(즉시 완료, mock/demo)뿐 아니라 **`pending_review`(라이브 심사 중)** 일 수 있다 — 성공 판정에
  둘 다 "정상 처리"로 다뤄야 한다.
- **승인 아티팩트**(엄브렐러 §3 동등성): `ActionResult.approval_id` 존재 + `api.management.audit(approval_id)`
  (`GET /management/audit?approval_id=`)로 감사 이벤트 조회. P1 검증의 핵심 — "예쁜 카드"가 아니라 정식 route와
  같은 승인/감사 레코드가 생기는지 확인한다.
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

## P1 범위·한계 (구현 전 합의)

- **클라이언트 로컬 임베드** — 카드는 `chat/page.tsx`의 로컬 메시지 상태에만 존재한다. **새로고침·세션 재조회 시
  카드 상태는 복원하지 않는다**(메시지 persistence/서버 재수화 대상 아님). 생성된 캠페인 자체는 정식 경로로 영속되니
  대시보드에는 남는다 — 사라지는 건 챗 안의 카드 UI 상태뿐.
- **승인/감사 영속은 백엔드(정식 route)가 담당** — P1은 프론트만 바꾸지만, 집행은 `/approve`+`/execute`를 타므로
  `approval_id`·감사 레코드는 정식과 동일하게 생긴다(Task 4에서 검증).

---

## Task 0: 실제 컴포넌트 소스 확인 (구현 전 필수)

> 코드는 변하므로 **구현 전에 실물 시그니처를 직접 확인**한다. 추측 금지.

**Files:** (읽기 전용)
- `frontend/src/components/manage/campaigns/CampaignForm.tsx`
- `frontend/src/components/manage/campaigns/CreateProposalPreview.tsx`
- `frontend/src/app/(app)/manage/campaigns/new/page.tsx`
- `frontend/src/lib/api.ts` (`management.createCampaignProposal`/`approve`/`execute`/`audit`)
- `backend/domain/management/contracts/enums.py` (`ResultStatus`)

- [ ] **Step 1: 확인 항목 체크** — 다음이 plan의 가정과 일치하는지 확인하고, 다르면 Task 1 코드를 그에 맞춰 조정:
  1. `CampaignForm` props가 `{ onSubmit: (v: CampaignFormValues) => void, busy: boolean }` 인지. **자체 submit 버튼**
     문구("제안 생성 →")·`valid` validation(이름 필수·`sendDaily >= minBudget`·`1 ≤ sendDays ≤ 90`)·기본값(예산
     floor ₩1,521 등)을 폼이 **내부적으로** 갖는지 → 임베드 카드는 폼 검증을 다시 만들지 않는다.
  2. `CreateProposalPreview` props가 `{ proposal, onApprove, onCancel, busy }` 인지.
  3. `api.management.approve(proposal, true)` 반환에 `approved_action`이, `execute(...)` 반환에 `{ result, error_message? }`
     가 있는지. `result`에 `approval_id`·`status`가 실리는지.
  4. `ResultStatus` 문자열: `success`·`pending_review`·`failed`·`rejected`. 생성 성공 시 **mock/demo는 `success`,
     라이브는 `pending_review`** 가능 — Task 1의 성공 판정이 둘 다 다루는지 확인.
- [ ] **Step 2: 불일치 기록** — 차이가 있으면 이 plan의 Task 1 코드 블록을 수정한 뒤 진행(커밋 불필요, 다음 태스크에 반영).

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

  // done — ResultStatus: success(즉시) | pending_review(Meta 심사 중) 둘 다 "정상 처리". 나머지는 실패.
  const status = result?.status;
  const ok = status === 'success' || status === 'pending_review';
  return (
    <div className="mt-1 rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-4 max-w-xl">
      {ok ? (
        <>
          <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">
            {status === 'pending_review' ? '⏳ 캠페인 제출됨 (심사 중)' : '✓ 캠페인 생성됨 (PAUSED)'}
          </p>
          <p className="mt-1 text-sm text-[#8B95A1]">
            {status === 'pending_review'
              ? 'Meta 심사가 끝나면 게재할 수 있어요.'
              : '대시보드에서 게재를 시작할 수 있어요.'}
          </p>
          {result?.approval_id && (
            <p className="mt-1 text-[11px] text-[#B0B8C1]">승인 ID: {result.approval_id}</p>
          )}
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

웰컴 상태의 퀵 프롬프트 그리드(`quickPrompts.map(...)`로 버튼들을 그리는 `<div className="grid grid-cols-2 ...">`)를 찾는다.
기존 퀵 프롬프트 버튼은 **플레인 텍스트**(이모지 없음) 스타일이다. 그 그리드 **다음**에, 같은 텍스트 스타일을 따르되
강조색으로 구분되는 버튼을 추가(이모지 대신 텍스트 라벨):

```tsx
<button
  onClick={openCreateCampaign}
  className="mt-3 w-full max-w-lg p-4 text-left text-sm font-medium text-[#3182F6] bg-[#EBF3FF] dark:bg-[#1E3A5F] border border-[#3182F6]/30 rounded-xl hover:bg-[#DCEBFF] dark:hover:bg-[#234876] transition-all"
>
  새 캠페인 만들기
</button>
```

- [ ] **Step 3: 대화 중에도 열 수 있는 트리거 (라벨 명시)**

> **주의:** 입력바에 **의미가 넓은 단독 `＋` 아이콘은 쓰지 않는다**(앱은 아이콘 라이브러리 없이 인라인 SVG·텍스트
> 버튼을 쓰고, `＋`만으론 "새 캠페인"인지 불명확). 대신 **텍스트 라벨이 보이는 칩 버튼**을 입력 바 위에 둔다.

입력 바 컨테이너(`<div className="border-t ... px-4 py-4 ...">`)의 `max-w-2xl mx-auto` 입력 행 **바로 위**에, 텍스트가
보이는 작은 칩을 추가:

```tsx
<div className="max-w-2xl mx-auto mb-2">
  <button
    onClick={openCreateCampaign}
    disabled={isStreaming}
    className="text-xs font-medium text-[#3182F6] bg-[#EBF3FF] dark:bg-[#1E3A5F] hover:bg-[#DCEBFF] dark:hover:bg-[#234876] rounded-full px-3 py-1.5 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
  >
    + 새 캠페인 만들기
  </button>
</div>
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
  7. **[승인 레코드 동등성 — 핵심]** 챗 생성이 정식 route와 **같은 승인/감사 아티팩트**를 남기는지 확인(엄브렐러 §3):
     - 결과 카드에 **승인 ID(`result.approval_id`)** 가 표시된다(빈 값이 아님).
     - 브라우저 DevTools Network 또는 콘솔에서 `/management/execute` 응답 `result`에 `approval_id`·`status`가 있고,
       이어서 `GET /management/audit?approval_id=<그 값>`(`api.management.audit`)이 **감사 이벤트를 반환**하는지 확인.
     - 같은 폼을 정식 화면(`/manage/campaigns/new`)에서 생성했을 때와 **동일한 승인/감사 레코드 형태**가 나오는지 대조.
     - 통과 못 하면 P1은 미완 — "예쁜 카드만 생기고 정책 논거가 빈" 상태이므로, 재배선이 정식 경로를 정확히 타는지 점검.

- [ ] **Step 3: 결과 기록**

검증 통과/이슈를 `docs/superpowers/plans/2026-06-29-p1-chat-create-campaign-embed.md` 하단 또는 커밋 메시지에 한 줄로 남긴다(예: "P1 수동 검증 통과 — 챗에서 생성→대시보드 반영 확인").

> **P1.5 후속(범위 밖, 별도 plan):**
> - **LLM 인텐트 라우팅** — "새 캠페인 만들어줘" 발화를 orchestrator(deep_agent)가 감지해 `embed:'create_campaign'` 신호를 meta로 내려주면, 퀵 버튼 없이도 대화로 카드가 열린다(backend 변경).
> - **LLM 폼 prefill** — 발화에서 이름·예산·목표를 추출해 `CampaignForm` 초기값으로 주입(`CampaignForm`에 `initial?: Partial<CampaignFormValues>` prop 추가 필요).
> - **생성 직후 게재(ACTIVATE)** — P2 `ACTIVATE_CAMPAIGN` 임베드와 함께.
