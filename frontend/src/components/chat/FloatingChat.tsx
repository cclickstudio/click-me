'use client';

// 우측 하단 플로팅 챗봇 — 접힘(버튼)/펼침(패널) 토글. /chat 탭에선 숨김.
// 열 때 활성 세션이 없으면 현재 프로젝트의 가장 최근 세션을 이어받는다. 세션 목록은 패널에서 고른다.
import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { useProjects } from '../ProjectContext';
import { useAuth } from '../AuthProvider';
import { useChatController } from './ChatController';
import ChatConversation from './ChatConversation';
import { api } from '@/lib/api';

export default function FloatingChat() {
  const pathname = usePathname();
  const { selectedProject } = useProjects();
  const { user } = useAuth();
  const {
    floatingOpen,
    setFloatingOpen,
    activeSessionId,
    setActiveSessionId,
    refreshSessions,
    progress,
    setProgress,
  } = useChatController();

  // /chat 탭(페이지 자체가 채팅) + 비로그인 화면에선 숨김.
  const hidden = pathname === '/chat' || !user;

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

  // ── 접힘 — 버튼만 ──
  if (!floatingOpen) {
    return (
      <button
        onClick={() => setFloatingOpen(true)}
        title="AI 채팅 열기"
        className="fixed bottom-6 right-6 z-40 w-14 h-14 rounded-full bg-[#3182F6] text-white shadow-lg hover:bg-[#1B6EEB] flex items-center justify-center transition-colors"
      >
        {/* 진행 중이면 회전 링 표시(T17) */}
        {progress && (
          <span className="absolute inset-0 rounded-full border-2 border-white/40 border-t-white animate-spin" />
        )}
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      </button>
    );
  }

  // ── 펼침 — 패널 ──
  return (
    <div className="fixed bottom-6 right-6 z-40 w-[400px] max-w-[calc(100vw-2rem)] h-[600px] max-h-[calc(100vh-3rem)] flex flex-col rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#0F1117] shadow-2xl overflow-hidden">
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
          <span className="w-4 h-4 rounded-full border-2 border-[#3182F6]/30 border-t-[#3182F6] animate-spin shrink-0" />
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
          />
        ) : (
          <div className="h-full flex flex-col items-center justify-center px-6 text-center">
            <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-1">프로젝트를 먼저 선택하세요</p>
            <p className="text-xs text-[#8B95A1] dark:text-[#6B7280]">왼쪽 프로젝트 패널에서 프로젝트를 선택하면 채팅이 열립니다.</p>
          </div>
        )}
      </div>
    </div>
  );
}
