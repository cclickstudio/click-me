'use client';

// 센터 — 우측 접이식 채팅·알림 통합 aside. 접힘(세로 2버튼 띠)/펼침(상단 탭) 전환·localStorage 복원.
// 스펙: docs/center/center-spec.md §3. 콘텐츠(필터바·알림 목록·채팅)는 후속 Phase에서 슬롯에 채운다.

import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { useAuth } from '../AuthProvider';
import { useProjects } from '../ProjectContext';
import { api, getAdminOrgId } from '@/lib/api';
import CenterFilterBar, { type CenterSegment } from './CenterFilterBar';
import AlarmCenter from './AlarmCenter';
import ChatCenter from './ChatCenter';

type CenterTab = 'chat' | 'alarm';

const LS_EXPANDED = 'center:expanded';
const LS_TAB = 'center:tab';

// 미읽음 배지 — 0이면 숨김, 9 초과는 9+.
function Badge({ count }: { count: number }) {
  if (!count) return null;
  return (
    <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-[#F04452] px-1 text-[10px] font-bold leading-none text-white">
      {count > 9 ? '9+' : count}
    </span>
  );
}

const ChatIcon = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
);

const BellIcon = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
    <path d="M13.73 21a2 2 0 0 1-3.46 0" />
  </svg>
);

export default function Center() {
  const { user } = useAuth();
  const { projects } = useProjects();
  const isAdmin = user?.role === 'ADMIN';
  const [expanded, setExpanded] = useState(false);
  const [tab, setTab] = useState<CenterTab>('alarm');
  const [alarmUnread, setAlarmUnread] = useState(0);
  const [chatUnread, setChatUnread] = useState(0);
  // 필터 상태 — 세그먼트는 채팅/알림 각각(스펙 §4), 프로젝트·기업은 공유. 기본 전체.
  const [chatSeg, setChatSeg] = useState<CenterSegment>('all');
  const [alarmSeg, setAlarmSeg] = useState<CenterSegment>('all');
  const [projectId, setProjectId] = useState('');
  const [orgId, setOrgId] = useState('');

  // 상태 복원 — 펼침 여부 + 마지막으로 연 센터(스펙 §3). ADMIN 선택 기업(X-Org-Id)도 복원.
  useEffect(() => {
    if (localStorage.getItem(LS_EXPANDED) === 'true') setExpanded(true);
    const t = localStorage.getItem(LS_TAB);
    if (t === 'chat' || t === 'alarm') setTab(t);
    setOrgId(getAdminOrgId() ?? '');
  }, []);

  const persistExpanded = (v: boolean) => {
    setExpanded(v);
    localStorage.setItem(LS_EXPANDED, String(v));
  };
  const persistTab = (t: CenterTab) => {
    setTab(t);
    localStorage.setItem(LS_TAB, t);
  };
  const openTab = (t: CenterTab) => {
    persistTab(t);
    persistExpanded(true);
  };

  // 미읽음 카운트 — 알림(병합 unread_count) + 채팅(통합 세션 unread 합). org 미선택(ADMIN)이면 0.
  const refreshCounts = useCallback(async () => {
    try {
      const n = await api.center.notifications();
      setAlarmUnread(n.unread_count || 0);
    } catch {
      /* best-effort — 배지 실패가 UI를 막지 않음 */
    }
    try {
      const s = await api.center.sessions();
      setChatUnread((s.sessions || []).reduce((acc, r) => acc + (r.unread_count || 0), 0));
    } catch {
      /* best-effort */
    }
  }, []);

  useEffect(() => {
    if (!user) return;
    refreshCounts();
    const id = setInterval(refreshCounts, 30000);
    return () => clearInterval(id);
  }, [user, refreshCounts]);

  // ADMIN이 기업을 바꾸면 즉시 배지 재조회(X-Org-Id 변경 반영).
  useEffect(() => {
    if (user) refreshCounts();
  }, [orgId, user, refreshCounts]);

  if (!user) return null;

  // 접힘 — 오른쪽 가장자리 세로 2버튼 띠(살짝 보이는 형태, 스펙 §3).
  if (!expanded) {
    return (
      <div className="max-md:hidden fixed right-0 top-1/2 z-50 flex -translate-y-1/2 flex-col gap-1 rounded-l-xl border border-r-0 border-[#E5E8EB] bg-white p-1.5 shadow-lg dark:border-[#2D3748] dark:bg-[#1C2333]">
        <button
          type="button"
          onClick={() => openTab('chat')}
          aria-label="채팅 센터 열기"
          className="relative flex h-10 w-10 items-center justify-center rounded-lg text-[#4E5968] hover:bg-[#F2F4F6] dark:text-[#9CA3AF] dark:hover:bg-[#252D3D]"
        >
          {ChatIcon}
          <Badge count={chatUnread} />
        </button>
        <button
          type="button"
          onClick={() => openTab('alarm')}
          aria-label="알림 센터 열기"
          className="relative flex h-10 w-10 items-center justify-center rounded-lg text-[#4E5968] hover:bg-[#F2F4F6] dark:text-[#9CA3AF] dark:hover:bg-[#252D3D]"
        >
          {BellIcon}
          <Badge count={alarmUnread} />
        </button>
      </div>
    );
  }

  // 펼침 — 우측 전체 높이 aside(본문 위에 덮음). 상단 두 버튼을 탭으로 전환(스펙 §3).
  return (
    <aside className="max-md:hidden fixed right-0 top-0 z-50 flex h-full w-72 flex-col border-l border-[#E5E8EB] bg-white shadow-xl dark:border-[#2D3748] dark:bg-[#1C2333]">
      <div className="flex items-center border-b border-[#E5E8EB] dark:border-[#2D3748]">
        <TabButton active={tab === 'chat'} count={chatUnread} onClick={() => persistTab('chat')} icon={ChatIcon}>
          채팅
        </TabButton>
        <TabButton active={tab === 'alarm'} count={alarmUnread} onClick={() => persistTab('alarm')} icon={BellIcon}>
          알림
        </TabButton>
        <button
          type="button"
          onClick={() => persistExpanded(false)}
          aria-label="센터 접기"
          className="ml-auto mr-1 flex h-8 w-8 items-center justify-center rounded-lg text-[#8B95A1] hover:bg-[#F2F4F6] dark:text-[#6B7280] dark:hover:bg-[#252D3D]"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M9 18l6-6-6-6" />
          </svg>
        </button>
      </div>
      <div className="flex flex-1 flex-col overflow-hidden">
        <CenterFilterBar
          segment={tab === 'chat' ? chatSeg : alarmSeg}
          onSegment={tab === 'chat' ? setChatSeg : setAlarmSeg}
          projectId={projectId}
          onProjectId={setProjectId}
          projects={projects}
          isAdmin={!!isAdmin}
          orgId={orgId}
          onOrgId={setOrgId}
        />
        {tab === 'chat' ? (
          <ChatCenter
            projectId={projectId}
            segment={chatSeg}
            readOnly={user?.role === 'COMPANY'}
            orgKey={orgId}
          />
        ) : (
          <AlarmCenter
            projectId={projectId}
            segment={alarmSeg}
            role={user?.role}
            orgKey={orgId}
          />
        )}
      </div>
    </aside>
  );
}

function TabButton({
  active,
  count,
  onClick,
  icon,
  children,
}: {
  active: boolean;
  count: number;
  onClick: () => void;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative flex flex-1 items-center justify-center gap-1.5 py-3 text-sm font-medium transition-colors ${
        active
          ? 'border-b-2 border-[#3182F6] text-[#3182F6]'
          : 'text-[#8B95A1] hover:text-[#4E5968] dark:text-[#6B7280] dark:hover:text-[#9CA3AF]'
      }`}
    >
      <span className="relative">
        {icon}
        <Badge count={count} />
      </span>
      {children}
    </button>
  );
}
