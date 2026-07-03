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
