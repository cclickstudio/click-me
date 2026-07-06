# Task 13: RemediationOptionsWidget + ChatConversation 연결

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-03-remediation-hybrid-notification.md` · 스펙: `docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md` §4·§6
> **실행 규칙**: 프론트 검증은 `cd frontend && pnpm lint && pnpm build` · 커밋은 명시 파일만 add · 새 .tsx 첫 줄 한국어 헤더 주석.
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.
> 선행: Task 10(백엔드 option_select 수용) · Task 11.

---

**Files:**
- Create: `frontend/src/components/chat/RemediationOptionsWidget.tsx`
- Modify: `frontend/src/components/chat/ChatConversation.tsx` (위젯 렌더 분기 + 전송 함수 연결 + option_select 전달)

- [ ] **Step 1: 위젯 작성**

`frontend/src/components/chat/RemediationOptionsWidget.tsx`:

```tsx
// 이상 조치 옵션 버튼 위젯 — consult meta의 옵션을 동적 렌더 + [기타] (이상 감지 C안)
'use client';

import { useState } from 'react';

const CIRCLED = ['①', '②', '③', '④', '⑤'];

export type RemediationOption = {
  index: number;
  action: string;
  tool_hint: string | null;
  label: string;
};

export type OptionSelectMeta = {
  kind: 'remediation_option_select';
  option_index: number;
  action: string;
  tool_hint: string | null;
  campaign_id: string;
  label: string;
};

export default function RemediationOptionsWidget({
  options,
  campaignId,
  onSelect,
  onEtc,
}: {
  options: RemediationOption[];
  campaignId: string;
  onSelect: (text: string, meta: OptionSelectMeta) => void;
  onEtc: () => void;
}) {
  // 실행 표시는 위젯 로컬 상태만(1차 범위 — 세션 재로드 시 소실 수용, 스펙 §4)
  const [executed, setExecuted] = useState<number[]>([]);

  const click = (o: RemediationOption) => {
    setExecuted(prev => (prev.includes(o.index) ? prev : [...prev, o.index]));
    onSelect(`${o.index}번(${o.label}) 진행해줘`, {
      kind: 'remediation_option_select',
      option_index: o.index,
      action: o.action,
      tool_hint: o.tool_hint,
      campaign_id: campaignId,
      label: o.label,
    });
  };

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {options.map(o => (
        <button
          key={o.index}
          type="button"
          onClick={() => click(o)}
          className={`rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors ${
            executed.includes(o.index)
              ? 'border-[#3182F6] bg-[#3182F6]/10 text-[#3182F6]'
              : 'border-[#E5E8EB] dark:border-[#2D3748] text-[#4E5968] dark:text-[#9CA3AF] hover:border-[#3182F6]'
          }`}
        >
          {executed.includes(o.index) && '✓ '}
          {CIRCLED[o.index - 1] ?? o.index} {o.label}
        </button>
      ))}
      <button
        type="button"
        onClick={onEtc}
        className="rounded-lg border border-dashed border-[#E5E8EB] dark:border-[#2D3748] px-2.5 py-1.5 text-xs text-[#8B95A1]"
      >
        기타…
      </button>
    </div>
  );
}
```

버튼 정책(스펙 §4): 실행한 옵션은 ✓ 표시만 하고 **비활성화하지 않는다** — 후속 대화 뒤 다른 옵션 선택이 가능해야 한다. [기타]는 전송 없이 입력창 포커스만.

- [ ] **Step 2: ChatConversation 연결**

`frontend/src/components/chat/ChatConversation.tsx`에서 (파일이 크므로 앵커로 위치를 찾는다):

1. import 추가:

```tsx
import RemediationOptionsWidget, { type OptionSelectMeta } from './RemediationOptionsWidget';
```

2. **meta 타입 확장** — meta 타입 정의부(앵커: `type SourceMeta` 검색)에 없으면 추가:

```tsx
  kind?: string;
  options?: { index: number; action: string; tool_hint: string | null; label: string }[];
  campaign_id?: string;
```

3. **assistant 메시지 렌더 블록**(앵커: `msg.meta?.widget?.type === 'sim_form' &&` 검색, 1740행 부근)과 같은 레벨에 분기 추가 — 메시지 본문 아래:

```tsx
{msg.role === 'assistant' &&
  msg.meta?.kind === 'remediation_consult' &&
  Array.isArray(msg.meta?.options) &&
  msg.meta.options.length > 0 && (
    <RemediationOptionsWidget
      options={msg.meta.options}
      campaignId={String(msg.meta.campaign_id ?? '')}
      onSelect={(text, optionSelect) => sendUserMessage(text, { optionSelect })}
      onEtc={() => focusInput('궁금한 점이나 다른 방법을 물어보세요')}
    />
  )}
```

4. **전송 함수 연결** — 입력창 onSubmit이 호출하는 기존 전송 함수(입력 state를 비우고 `/chat/complete`를 fetch하는 함수)를 찾아 옵션 파라미터를 추가한다. 함수 이름이 다르면 그 이름을 쓰되 동작은 동일하게:
   - `sendUserMessage(text: string, opts?: { optionSelect?: OptionSelectMeta })` 형태로 재사용 가능하게(이미 함수가 있으면 opts 파라미터만 추가).
   - `/chat/complete` 요청 body를 만드는 곳에 `...(opts?.optionSelect ? { option_select: opts.optionSelect } : {})` 추가 (백엔드 `ChatRequest.option_select` — Task 10).
   - 사용자 메시지를 로컬 목록에 추가하는 곳에서 content는 text 그대로(사람이 읽는 로그).
5. **focusInput(placeholder)** — 입력창 ref가 이미 있으면 `ref.current?.focus()` + placeholder 상태 교체로 구현. 없으면 입력 `<input|textarea>`에 ref를 추가한다. placeholder는 blur 시 원복.

- [ ] **Step 3: 검증 + 커밋**

```bash
cd frontend && pnpm lint && pnpm build
git add frontend/src/components/chat/RemediationOptionsWidget.tsx frontend/src/components/chat/ChatConversation.tsx
git commit -m "add: 채팅 옵션 버튼 위젯 — consult meta 동적 렌더·option_select 동봉·[기타] 포커스"
```
