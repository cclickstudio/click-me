# Task 12: NotificationBell + NotificationPanel + AppLayout 장착

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-03-remediation-hybrid-notification.md` · 스펙: `docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md` §6
> **실행 규칙**: 프론트 검증은 `cd frontend && pnpm lint && pnpm build` · 커밋은 명시 파일만 add · 새 .tsx 첫 줄 한국어 헤더 주석.
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.
> ⚠ `AppLayout.tsx`는 프론트 공통부 — 사전 공지(Task 0 ②) 확인 후 진행. 벨 1줄 append만.
> 선행: Task 11 (`api.management.notifications`·`useNotificationStream`).

---

**Files:**
- Create: `frontend/src/components/manage/notifications/NotificationPanel.tsx`
- Create: `frontend/src/components/manage/notifications/NotificationBell.tsx`
- Modify: `frontend/src/components/AppLayout.tsx:114` (`<Sidebar …/>` 아래 1줄)

- [ ] **Step 1: NotificationPanel 작성**

`frontend/src/components/manage/notifications/NotificationPanel.tsx`:

```tsx
// 알림 패널 — 카드 목록·프로젝트 필터·[상담하기][무시] (이상 감지 C안)
'use client';

import { useMemo, useState } from 'react';
import { api, type ManagementNotification } from '@/lib/api';
import { useProjects } from '../../ProjectContext';
import { useChatController } from '../../chat/ChatController';

const ANOMALY_LABEL: Record<string, string> = {
  no_delivery: '노출 0 감지',
  quality_degraded: 'CTR 하락',
  budget_exhausted: '예산 조기 소진',
};

export default function NotificationPanel({
  items,
  onRefetch,
  onClose,
}: {
  items: ManagementNotification[];
  onRefetch: () => void;
  onClose: () => void;
}) {
  const { projects, selectedProject, selectProject } = useProjects();
  const { setActiveSessionId, setFloatingOpen } = useChatController();
  const [projectFilter, setProjectFilter] = useState<string>('');
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const visible = useMemo(
    () => (projectFilter ? items.filter(n => n.project_id === projectFilter) : items),
    [items, projectFilter],
  );

  const onConsult = async (n: ManagementNotification) => {
    setBusyId(n.id);
    try {
      const r = await api.management.notifications.consult(n.id);
      if (r.status === 'consult') {
        if (selectedProject?.id !== n.project_id) selectProject(n.project_id); // org 전체 패널 — 타 프로젝트 알림
        setActiveSessionId(r.session_id);
        setFloatingOpen(true);
        onClose();
      } else if (r.status === 'normal') {
        setNotice(r.message || '다시 확인하니 지금은 정상이에요.');
      } else {
        setNotice('이미 처리된 알림이에요.');
      }
      onRefetch();
    } catch {
      setNotice('상담 준비에 실패했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setBusyId(null);
    }
  };

  const onIgnore = async (n: ManagementNotification) => {
    setBusyId(n.id);
    try {
      await api.management.notifications.resolve(n.id, 'ignored');
      onRefetch();
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="absolute right-0 top-11 z-50 w-96 max-w-[92vw] rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] shadow-lg">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#E5E8EB] dark:border-[#2D3748]">
        <span className="text-sm font-semibold text-[#191F28] dark:text-white">운영 알림</span>
        <select
          value={projectFilter}
          onChange={e => setProjectFilter(e.target.value)}
          className="text-xs rounded-md border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent px-2 py-1 text-[#4E5968] dark:text-[#9CA3AF]"
        >
          <option value="">전체 프로젝트</option>
          {projects.map(p => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>
      {notice && (
        <div className="px-4 py-2 text-xs text-[#3182F6] bg-[#3182F6]/5">{notice}</div>
      )}
      <div className="max-h-96 overflow-y-auto">
        {visible.length === 0 ? (
          <p className="px-4 py-8 text-center text-xs text-[#8B95A1]">새 알림이 없어요.</p>
        ) : (
          visible.map(n => (
            <div key={n.id} className="px-4 py-3 border-b border-[#F2F4F6] dark:border-[#2D3748]/60">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-medium text-[#191F28] dark:text-white">
                    ⚠ {n.payload.campaign_name || n.campaign_id} —{' '}
                    {ANOMALY_LABEL[n.payload.anomaly_type ?? ''] || '이상 감지'}
                  </p>
                  <p className="mt-0.5 text-xs text-[#8B95A1]">
                    {n.project_name}
                    {n.followup_count > 0 && ` · ${n.followup_count + 1}회째 알림`}
                    {' · '}
                    {new Date(n.last_notified_at).toLocaleString('ko-KR')}
                  </p>
                </div>
                {!n.read_at && <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-[#EF4444]" />}
              </div>
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  disabled={busyId === n.id}
                  onClick={() => onConsult(n)}
                  className="rounded-lg bg-[#3182F6] px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                >
                  상담하기
                </button>
                <button
                  type="button"
                  disabled={busyId === n.id}
                  onClick={() => onIgnore(n)}
                  className="rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] px-3 py-1.5 text-xs text-[#4E5968] dark:text-[#9CA3AF] disabled:opacity-50"
                >
                  무시
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
```

전제 확인: `useProjects()`가 `projects`·`selectedProject`·`selectProject`를 노출하는지(`ProjectContext.tsx:32·172` 확인 완료), `useChatController()`가 `setActiveSessionId`·`setFloatingOpen`을 노출하는지(`ChatController.tsx:17-18` 확인 완료). 다르면 실제 이름에 맞추고 차이를 보고.

- [ ] **Step 2: NotificationBell 작성**

`frontend/src/components/manage/notifications/NotificationBell.tsx`:

```tsx
// 운영 알림 벨 — 상단 우측 고정, org 전체 미읽음 배지 + 패널 토글 (이상 감지 C안)
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { api, type ManagementNotification } from '@/lib/api';
import { useAuth } from '../../AuthProvider';
import NotificationPanel from './NotificationPanel';
import { useNotificationStream } from './useNotificationStream';

export default function NotificationBell() {
  const { user } = useAuth();
  const pathname = usePathname();
  const [items, setItems] = useState<ManagementNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const refetch = useCallback(() => {
    if (!user) return;
    api.management.notifications
      .list()
      .then(r => {
        setItems(r.notifications);
        setUnread(r.unread_count);
      })
      .catch(() => {});
  }, [user]);

  // 폴백: 라우트 전환 시 refetch(N5 벨과 같은 패턴) + SSE 수신 시 refetch
  useEffect(() => {
    refetch();
  }, [refetch, pathname]);
  useNotificationStream(!!user, refetch);

  // 패널 열람 = 보이는 카드 bulk read(스펙 §2)
  const openPanel = () => {
    setOpen(v => !v);
    if (!open) {
      const unreadIds = items.filter(n => !n.read_at).map(n => n.id);
      if (unreadIds.length) {
        api.management.notifications.read(unreadIds).then(refetch).catch(() => {});
      }
    }
  };

  // 바깥 클릭 시 닫기
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  if (!user) return null;

  return (
    <div ref={rootRef} className="fixed top-3 right-4 z-40">
      <button
        type="button"
        onClick={openPanel}
        aria-label="운영 알림"
        className="relative flex h-10 w-10 items-center justify-center rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] text-[#4E5968] dark:text-[#9CA3AF] shadow-sm"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.7 21a2 2 0 0 1-3.4 0" />
        </svg>
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-[#EF4444] px-1 text-[10px] font-bold text-white">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>
      {open && (
        <NotificationPanel items={items} onRefetch={refetch} onClose={() => setOpen(false)} />
      )}
    </div>
  );
}
```

- [ ] **Step 3: AppLayout 장착** (⚠ 프론트 공통부)

`frontend/src/components/AppLayout.tsx` — import 추가 후 `<Sidebar …/>`(114행) 아래에 1줄:

```tsx
import NotificationBell from './manage/notifications/NotificationBell';
```

```tsx
      <Sidebar mobileOpen={mobileNavOpen} />
      <NotificationBell />
```

- [ ] **Step 4: 검증 + 커밋**

```bash
cd frontend && pnpm lint && pnpm build
git add frontend/src/components/manage/notifications frontend/src/components/AppLayout.tsx
git commit -m "add: 운영 알림 벨·패널 — org 전체 배지·프로젝트 필터·상담하기/무시"
```
