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

  // ADMIN은 조직 스코프(X-Org-Id)가 없어 목록·스트림 호출이 400 → 아예 호출하지 않는다.
  const isAdmin = user?.role === 'ADMIN';

  const refetch = useCallback(() => {
    if (!user || isAdmin) return;
    api.management.notifications
      .list()
      .then(r => {
        setItems(r.notifications);
        setUnread(r.unread_count);
      })
      .catch(() => {});
  }, [user, isAdmin]);

  // 폴백: 라우트 전환 시 refetch(N5 벨과 같은 패턴) + SSE 수신 시 refetch
  useEffect(() => {
    refetch();
  }, [refetch, pathname]);
  useNotificationStream(!!user && !isAdmin, refetch);

  // 패널 토글 — 읽음 처리는 패널이 "보이는 카드"를 알려줄 때(onReadVisible)만 수행
  const openPanel = () => {
    const next = !open;
    setOpen(next);
  };

  // 패널에 실제로 보이는(필터 적용된) 미읽음 카드만 bulk read(스펙 §2)
  const readVisible = useCallback(
    (ids: string[]) => {
      api.management.notifications.read(ids).then(refetch).catch(() => {});
    },
    [refetch],
  );

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
    // ADMIN은 manage 상단바(AdminOrgPicker, 약 51px)와 겹치지 않게 top-14로 내림
    <div ref={rootRef} className={`fixed ${user.role === 'ADMIN' ? 'top-14' : 'top-3'} right-4 z-40`}>
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
        <NotificationPanel
          items={items}
          onRefetch={refetch}
          onClose={() => setOpen(false)}
          onReadVisible={readVisible}
        />
      )}
    </div>
  );
}
