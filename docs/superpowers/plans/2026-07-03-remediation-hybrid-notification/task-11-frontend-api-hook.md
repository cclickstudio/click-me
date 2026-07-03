# Task 11: 프론트 API 클라이언트 + SSE 훅

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-03-remediation-hybrid-notification.md` · 스펙: `docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md` §6
> **실행 규칙**: 프론트 검증은 `cd frontend && pnpm lint && pnpm build` · 커밋은 명시 파일만 add · 새 .ts/.tsx 첫 줄 한국어 헤더 주석 · pnpm은 frontend 전용(uv 금지).
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.

---

**Files:**
- Modify: `frontend/src/lib/api.ts` (`management:` 객체 안에 추가, 699행 부근 + 상단 타입 선언부)
- Create: `frontend/src/components/manage/notifications/useNotificationStream.ts`

- [ ] **Step 1: api.ts에 타입·메서드 추가**

파일 상단 타입 선언부(다른 type들 근처)에:

```typescript
export type ManagementNotification = {
  id: string;
  project_id: string;
  project_name: string;
  campaign_id: string | null;
  kind: string;
  payload: {
    campaign_name?: string;
    message?: string;
    anomaly_type?: string;
    options?: { index: number; action: string; tool_hint: string | null; label: string }[];
  };
  read_at: string | null;
  resolved_at: string | null;
  resolution: string | null;
  followup_count: number;
  last_notified_at: string;
  created_at: string | null;
};
```

`api.ts`의 `management: {` 객체 안 마지막에 추가:

```typescript
    // 운영 알림(이상 감지 C안) — 스펙 2026-07-03 §2
    notifications: {
      list: (params?: { project_id?: string; unread_only?: boolean }) => {
        const q = new URLSearchParams();
        if (params?.project_id) q.set("project_id", params.project_id);
        if (params?.unread_only) q.set("unread_only", "true");
        const qs = q.toString();
        return request<{ notifications: ManagementNotification[]; unread_count: number }>(
          `/management/notifications${qs ? `?${qs}` : ""}`,
        );
      },
      read: (ids: string[]) =>
        request<{ updated: number }>(`/management/notifications/read`, {
          method: "POST",
          body: JSON.stringify({ ids }),
        }),
      resolve: (id: string, resolution: "ignored" | "actioned") =>
        request<{ resolved: boolean }>(`/management/notifications/${id}/resolve`, {
          method: "POST",
          body: JSON.stringify({ resolution }),
        }),
      consult: (id: string) =>
        request<
          | { status: "consult"; session_id: string }
          | { status: "normal"; message: string }
          | { status: "already_resolved"; resolution: string }
        >(`/management/notifications/${id}/consult`, { method: "POST" }),
    },
```

- [ ] **Step 2: SSE 훅 작성**

`frontend/src/components/manage/notifications/useNotificationStream.ts`:

```typescript
// 알림 SSE 구독 훅 — "changed" 신호 수신 시 onChange 호출, 지수 백오프 재연결
'use client';

import { useEffect, useRef } from 'react';
import { authedFetch } from '@/lib/api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function useNotificationStream(enabled: boolean, onChange: () => void) {
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    let ctrl: AbortController | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const run = async (attempt: number) => {
      ctrl = new AbortController();
      try {
        const res = await authedFetch(`${API_BASE}/api/management/notifications/stream`, {
          signal: ctrl.signal,
        });
        if (!res.ok || !res.body) throw new Error(String(res.status));
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop() ?? '';
          for (const line of lines) {
            if (line.includes('"changed"')) onChangeRef.current();
          }
          attempt = 0; // 정상 수신 중 — 백오프 리셋
        }
      } catch {
        /* 재연결로 폴스루 — SSE 실패 시 라우트 전환 폴링이 폴백(스펙 §6) */
      }
      if (!stopped) {
        const delay = Math.min(30_000, 1000 * 2 ** attempt);
        timer = setTimeout(() => run(attempt + 1), delay);
      }
    };
    run(0);
    return () => {
      stopped = true;
      ctrl?.abort();
      if (timer) clearTimeout(timer);
    };
  }, [enabled]);
}
```

전제 확인: `authedFetch`는 api.ts에서 이미 `export`다(221행 `export async function authedFetch`).

- [ ] **Step 3: 검증 + 커밋**

```bash
cd frontend && pnpm lint && pnpm build
git add frontend/src/lib/api.ts frontend/src/components/manage/notifications/useNotificationStream.ts
git commit -m "add: 알림 API 클라이언트 + SSE 구독 훅(fetch 스트리밍·백오프)"
```
