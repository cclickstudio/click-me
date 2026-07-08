'use client';

// 센터 — 우측 접이식 채팅·알림 통합 aside. 접힘(세로 2버튼 띠)/펼침(상단 탭) 전환·localStorage 복원.
// 스펙: docs/center/center-spec.md §3. 콘텐츠(필터바·알림 목록·채팅)는 후속 Phase에서 슬롯에 채운다.

import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { useAuth } from '../AuthProvider';
import { useProjects } from '../ProjectContext';
import { api, getAdminOrgId, setAdminOrgId } from '@/lib/api';
import CenterFilterBar, { type CenterSegment } from './CenterFilterBar';
import AlarmCenter from './AlarmCenter';
import ChatCenter from './ChatCenter';

type CenterTab = 'chat' | 'alarm';

const LS_EXPANDED = 'center:expanded';
const LS_TAB = 'center:tab';
// ADMIN이 마지막 선택한 기업 — 전역 adminOrgId는 sessionStorage(보안: 탭 종료 시 소멸)라,
// 센터 배지 복원용으로 별도 localStorage에 기억했다가 마운트 시 sessionStorage를 재확립한다.
const LS_ORG = 'center:orgId';

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
  const { projects, refresh: refreshProjects } = useProjects();
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
  // 상담하기 등으로 특정 세션을 채팅 센터에서 열도록 하는 신호(알림→채팅 전환).
  const [openTarget, setOpenTarget] = useState<{ sessionId: string; projectId: string } | null>(
    null,
  );

  // /chat 라우트에선 채팅이 페이지(패널 옆 세션 사이드바)로 이동 → 센터는 알림만 노출.
  // 그 외 라우트에선 채팅+알림 둘 다. 채팅 탭을 숨기고 활성 탭을 알림으로 고정한다.
  const pathname = usePathname();
  const chatInPage = !!pathname && pathname.startsWith('/chat');
  const effectiveTab: CenterTab = chatInPage ? 'alarm' : tab;

  // 상태 복원 — 펼침 여부 + 마지막으로 연 센터(스펙 §3).
  useEffect(() => {
    if (localStorage.getItem(LS_EXPANDED) === 'true') setExpanded(true);
    const t = localStorage.getItem(LS_TAB);
    if (t === 'chat' || t === 'alarm') setTab(t);
  }, []);

  // ADMIN 마지막 선택 기업 복원 — 세션(sessionStorage) 없으면 localStorage에서 되살려
  // sessionStorage(X-Org-Id)를 재확립. 접힘 상태에서도 마운트 즉시 배지가 뜨게 한다.
  useEffect(() => {
    if (!isAdmin) return;
    const saved = getAdminOrgId() || localStorage.getItem(LS_ORG) || '';
    if (saved) {
      setAdminOrgId(saved);
      setOrgId(saved);
    }
  }, [isAdmin]);

  // 기업 선택 변경 — 센터 상태 + localStorage 동기화(재접속 복원용) + 프로젝트 목록 재조회.
  // (프로젝트 드롭다운을 선택 기업 소속으로 한정 — CenterFilterBar가 setAdminOrgId를 먼저 반영하므로
  //  refreshProjects는 새 org 스코프로 /api/projects를 다시 부른다.)
  const handleOrgId = (v: string) => {
    setOrgId(v);
    if (v) localStorage.setItem(LS_ORG, v);
    else localStorage.removeItem(LS_ORG);
    void refreshProjects();
  };

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
      <div className="max-md:hidden fixed right-0 top-[100px] z-50 flex flex-col gap-1 rounded-l-xl border border-r-0 border-line bg-white p-1.5 shadow-lg dark:bg-[#1C2333]">
        {!chatInPage && (
          <button
            type="button"
            onClick={() => openTab('chat')}
            aria-label="채팅 센터 열기"
            className="relative flex h-10 w-10 items-center justify-center rounded-lg text-ink-secondary hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D]"
          >
            {ChatIcon}
            <Badge count={chatUnread} />
          </button>
        )}
        <button
          type="button"
          onClick={() => openTab('alarm')}
          aria-label="알림 센터 열기"
          className="relative flex h-10 w-10 items-center justify-center rounded-lg text-ink-secondary hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D]"
        >
          {BellIcon}
          <Badge count={alarmUnread} />
        </button>
      </div>
    );
  }

  // 펼침 — 우측 전체 높이 aside(본문 위에 덮음). 상단 두 버튼을 탭으로 전환(스펙 §3).
  return (
    <aside className="max-md:hidden fixed right-0 top-0 z-50 flex h-full w-[460px] flex-col border-l border-line bg-white shadow-xl dark:bg-[#1C2333]">
      <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
        {/* 로고 — 좌측 브랜드 마크(사이드바 워드마크와 통일) */}
        <span className="shrink-0 select-none text-sm font-bold tracking-tight text-primary">
          ClickMe
        </span>
        {/* 채팅 | 알림 세그먼트 — 배지는 아이콘 위가 아니라 라벨 옆 인라인 */}
        <div className="mx-auto flex items-center gap-0.5 rounded-lg bg-surface-1 p-0.5">
          {!chatInPage && (
            <SegTab active={effectiveTab === 'chat'} count={chatUnread} onClick={() => persistTab('chat')} icon={ChatIcon}>
              채팅
            </SegTab>
          )}
          <SegTab active={effectiveTab === 'alarm'} count={alarmUnread} onClick={() => persistTab('alarm')} icon={BellIcon}>
            알림
          </SegTab>
        </div>
        <button
          type="button"
          onClick={() => persistExpanded(false)}
          aria-label="센터 접기"
          className="shrink-0 flex h-8 w-8 items-center justify-center rounded-lg text-ink-tertiary hover:bg-accent"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M9 18l6-6-6-6" />
          </svg>
        </button>
      </div>
      <div className="flex flex-1 flex-col overflow-hidden">
        <CenterFilterBar
          segment={effectiveTab === 'chat' ? chatSeg : alarmSeg}
          onSegment={effectiveTab === 'chat' ? setChatSeg : setAlarmSeg}
          projectId={projectId}
          onProjectId={setProjectId}
          projects={projects}
          isAdmin={!!isAdmin}
          orgId={orgId}
          onOrgId={handleOrgId}
        />
        {isAdmin && !orgId ? (
          // ADMIN 기업 미선택 — 두 센터 disable + 안내(스펙 §7). 상단 기업 드롭다운으로 선택 유도.
          <div className="flex flex-1 flex-col items-center justify-center gap-1 p-6 text-center">
            <p className="text-sm font-medium text-ink">
              기업을 선택해주세요
            </p>
            <p className="text-xs text-ink-tertiary">
              상단 기업 드롭다운에서 기업을 고르면 채팅·알림이 열립니다.
            </p>
          </div>
        ) : (
          // 두 센터를 모두 마운트해 두고 탭은 CSS로만 토글 — 탭 전환 시 재요청 없이
          // 기업 선택(orgKey 변경) 때 각 1회만 조회한다.
          <>
            {!chatInPage && (
              <div className={effectiveTab === 'chat' ? 'flex flex-1 flex-col overflow-hidden' : 'hidden'}>
                <ChatCenter
                  projectId={projectId}
                  segment={chatSeg}
                  readOnly={user?.role === 'COMPANY'}
                  orgKey={orgId}
                  openTarget={openTarget}
                  onOpenConsumed={() => setOpenTarget(null)}
                />
              </div>
            )}
            <div className={effectiveTab === 'alarm' ? 'flex flex-1 flex-col overflow-hidden' : 'hidden'}>
              <AlarmCenter
                projectId={projectId}
                segment={alarmSeg}
                role={user?.role}
                orgKey={orgId}
                onOpenChat={(sessionId, pid) => {
                  setOpenTarget({ sessionId, projectId: pid });
                  persistTab('chat');
                }}
              />
            </div>
          </>
        )}
      </div>
    </aside>
  );
}

// 세그먼트 탭 — 아이콘+라벨, 미읽음은 라벨 옆 인라인 배지(아이콘 위에 겹치지 않음).
function SegTab({
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
      className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
        active
          ? 'bg-card text-primary shadow-sm'
          : 'text-ink-tertiary hover:text-ink-secondary'
      }`}
    >
      {icon}
      {children}
      {count > 0 && (
        <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold leading-none text-danger-foreground">
          {count > 9 ? '9+' : count}
        </span>
      )}
    </button>
  );
}
