'use client';

// 우측 하단 플로팅 챗봇 — 접힘(버튼)/펼침(패널) 토글. /chat 탭에선 숨김.
// 열 때 활성 세션이 없으면 현재 프로젝트의 가장 최근 세션을 이어받는다. 세션 목록은 패널에서 고른다.
import { useEffect, useRef, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useProjects } from '../ProjectContext';
import { useAuth } from '../AuthProvider';
import { useChatController } from './ChatController';
import ChatConversation from './ChatConversation';
import { api } from '@/lib/api';

type ChatNotif = {
  session_id: string;
  title: string;
  preview: string;
  unread_count: number;
};

export default function FloatingChat() {
  const pathname = usePathname();
  const router = useRouter();
  const { selectedProject } = useProjects();
  const { user } = useAuth();
  // N5 미확인 알림 — 라우트 변경마다 폴링해 벨 배지·패널에 표시.
  const [notifs, setNotifs] = useState<ChatNotif[]>([]);
  const [showPanel, setShowPanel] = useState(false);
  const {
    floatingOpen,
    setFloatingOpen,
    activeSessionId,
    setActiveSessionId,
    refreshSessions,
    progress,
    setProgress,
    unread,
    pushUnread,
    clearUnread,
  } = useChatController();

  // 패널이 닫혀 있는지 추적(ref) — 결과 완료 콜백이 최신 열림 상태를 보게 한다.
  const openRef = useRef(floatingOpen);
  openRef.current = floatingOpen;

  // /chat 탭(페이지 자체가 채팅) + 비로그인 화면에선 숨김.
  // /chat 전체(게이트·프로젝트·세션) 하위 경로에선 페이지 자체가 채팅이라 플로팅 숨김.
  const hidden = (pathname?.startsWith('/chat') ?? false) || !user;

  // N5 — 라우트가 바뀔 때마다(언마운트 무관) 미확인 알림을 받아와 벨 배지·패널을 갱신한다.
  useEffect(() => {
    if (!user || !selectedProject) {
      setNotifs([]);
      return;
    }
    let alive = true;
    api.chat
      .notifications(selectedProject.id)
      .then(r => {
        if (alive) setNotifs(r.notifications || []);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [pathname, selectedProject, user]);

  // 알림 항목 클릭 — 해당 세션 채팅으로 이동 + 읽음 처리 후 목록에서 제거.
  const openNotif = (n: ChatNotif) => {
    setShowPanel(false);
    if (selectedProject) router.push(`/chat/${selectedProject.id}/${n.session_id}`);
    api.chat
      .markRead(n.session_id)
      .then(() => refreshSessions())
      .catch(() => {});
    setNotifs(prev => prev.filter(x => x.session_id !== n.session_id));
  };

  // 플로팅을 열면 쌓인 알림 배지를 비운다(T18).
  useEffect(() => {
    if (floatingOpen) clearUnread();
  }, [floatingOpen, clearUnread]);

  // 플로팅을 열었는데 활성 세션이 없으면 가장 최근 세션을 이어받는다(없으면 새 채팅).
  useEffect(() => {
    if (hidden || !floatingOpen || activeSessionId || !selectedProject) return;
    let cancelled = false;
    (async () => {
      try {
        const { sessions } = await api.chat.sessions(selectedProject.id);
        if (!cancelled && sessions[0]) setActiveSessionId(sessions[0].id);
      } catch {
        // 없으면 새 채팅 상태 유지
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [hidden, floatingOpen, activeSessionId, selectedProject, setActiveSessionId]);

  if (hidden) return null;

  // 패널은 접혀도 언마운트하지 않고 숨긴다(display:none) — 백그라운드 실행·완료 알림 유지(T18).
  return (
    <>
      {/* N5 알림 벨 — 접힘 상태에서 챗 버튼 좌측. 클릭 시 미확인 알림 패널 토글 */}
      {!floatingOpen && (
        <>
          <button
            onClick={() => setShowPanel(v => !v)}
            title="미확인 알림"
            className="fixed bottom-7 right-24 z-40 w-11 h-11 rounded-full bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] text-[#4E5968] dark:text-[#9CA3AF] shadow-lg hover:text-[#3182F6] hover:border-[#3182F6]/40 flex items-center justify-center transition-colors"
          >
            {notifs.length > 0 && (
              <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 flex items-center justify-center rounded-full bg-[#F04452] text-white text-[10px] font-bold shadow">
                {notifs.length > 9 ? '9+' : notifs.length}
              </span>
            )}
            <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
          </button>
          {/* 알림 패널 — 미확인 세션 목록(제목·미리보기·개수). 항목 클릭 시 세션 이동+읽음 */}
          {showPanel && (
            <div className="fixed bottom-20 right-20 z-40 w-80 max-w-[calc(100vw-2rem)] max-h-[60vh] flex flex-col rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#0F1117] shadow-2xl overflow-hidden">
              <div className="h-10 shrink-0 flex items-center justify-between px-3 border-b border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#161B27]">
                <span className="text-xs font-semibold text-[#191F28] dark:text-[#F2F4F6]">
                  미확인 알림 {notifs.length > 0 ? `(${notifs.length})` : ''}
                </span>
                <button
                  onClick={() => setShowPanel(false)}
                  className="text-[#8B95A1] hover:text-[#3182F6] text-xs"
                >
                  닫기
                </button>
              </div>
              <div className="flex-1 overflow-y-auto">
                {notifs.length === 0 ? (
                  <p className="px-3 py-6 text-center text-xs text-[#8B95A1] dark:text-[#6B7280]">
                    새로운 알림이 없어요.
                  </p>
                ) : (
                  notifs.map(n => (
                    <button
                      key={n.session_id}
                      onClick={() => openNotif(n)}
                      className="w-full text-left px-3 py-2.5 border-b border-[#F2F4F6] dark:border-[#252D3D] hover:bg-[#F9FAFB] dark:hover:bg-[#161B27] transition-colors"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-[#191F28] dark:text-[#F2F4F6] truncate">
                          {n.title || '채팅'}
                        </span>
                        <span className="shrink-0 min-w-[18px] h-[18px] px-1 flex items-center justify-center rounded-full bg-[#3182F6] text-white text-[10px] font-bold">
                          {n.unread_count > 9 ? '9+' : n.unread_count}
                        </span>
                      </div>
                      {n.preview && (
                        <p className="mt-0.5 text-[11px] text-[#8B95A1] dark:text-[#6B7280] truncate">
                          {n.preview}
                        </p>
                      )}
                    </button>
                  ))
                )}
              </div>
            </div>
          )}
        </>
      )}

      {/* 접힘 — 버튼(+진행 링 +알림 배지) */}
      {!floatingOpen && (
        <button
          onClick={() => setFloatingOpen(true)}
          title="AI 채팅 열기"
          className="fixed bottom-6 right-6 z-40 w-14 h-14 rounded-full bg-[#3182F6] text-white shadow-lg hover:bg-[#1B6EEB] flex items-center justify-center transition-colors"
        >
          {/* 진행 중이면 회전 링 표시(T17) */}
          {progress && (
            <span className="absolute inset-0 rounded-full border-2 border-white/40 border-t-white animate-spin" />
          )}
          {/* 안 읽은 완료 알림 배지(T18) */}
          {unread > 0 && (
            <span className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1 flex items-center justify-center rounded-full bg-[#F04452] text-white text-[11px] font-bold shadow">
              {unread > 9 ? '9+' : unread}
            </span>
          )}
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        </button>
      )}

      {/* 펼침 — 패널(접히면 hidden) */}
      <div
        className={`fixed bottom-6 right-6 z-40 w-[400px] max-w-[calc(100vw-2rem)] h-[600px] max-h-[calc(100vh-3rem)] flex-col rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#0F1117] shadow-2xl overflow-hidden ${
          floatingOpen ? 'flex' : 'hidden'
        }`}
      >
      {/* 헤더 */}
      <div className="h-12 shrink-0 flex items-center justify-between px-3 border-b border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#161B27]">
        <div className="flex items-center gap-2 min-w-0">
          <span className="w-6 h-6 flex items-center justify-center rounded-lg bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6] shrink-0">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </span>
          <span className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] truncate">
            {selectedProject ? selectedProject.name : 'AI 채팅'}
          </span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => setActiveSessionId(null)}
            title="새 채팅"
            className="w-7 h-7 flex items-center justify-center rounded-lg text-[#8B95A1] hover:text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>
          <button
            onClick={() => setFloatingOpen(false)}
            title="접기"
            className="w-7 h-7 flex items-center justify-center rounded-lg text-[#8B95A1] hover:text-[#3182F6] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>

      {/* 진행 트레이 — 백그라운드 작업 중 스피너 + 라벨(+진행률) (T17) */}
      {progress && (
        <div className="shrink-0 flex items-center gap-2 px-3 py-2 border-b border-[#E5E8EB] dark:border-[#2D3748] bg-[#F5F9FF] dark:bg-[#16243C]">
          <span className="w-4 h-4 rounded-full border-2 border-[#3182F6]/30 border-t-[#3182F6] dark:border-t-[#5B9DF9] animate-spin shrink-0" />
          <span className="text-xs text-[#3182F6] font-semibold truncate">{progress.label}</span>
          {typeof progress.pct === 'number' && (
            <span className="ml-auto text-xs text-[#3182F6] tabular-nums shrink-0">
              {progress.pct}%
            </span>
          )}
        </div>
      )}

      {/* 본체 */}
      <div className="flex-1 min-h-0">
        {selectedProject ? (
          <ChatConversation
            projectId={selectedProject.id}
            sessionId={activeSessionId}
            onSessionCreated={(id) => {
              setActiveSessionId(id);
              refreshSessions();
            }}
            onActivity={refreshSessions}
            onProgress={setProgress}
            onResultComplete={() => {
              // 결과 도착 — 패널이 닫혀 있으면 배지로 먼저 알린다(T18).
              if (!openRef.current) pushUnread();
            }}
          />
        ) : (
          <div className="h-full flex flex-col items-center justify-center px-6 text-center">
            <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-1">프로젝트를 먼저 선택하세요</p>
            <p className="text-xs text-[#8B95A1] dark:text-[#6B7280]">왼쪽 프로젝트 패널에서 프로젝트를 선택하면 채팅이 열립니다.</p>
          </div>
        )}
      </div>
      </div>
    </>
  );
}
