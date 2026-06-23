'use client';

// 채팅 컨트롤러 — 플로팅 열림 상태 + 활성 세션을 패널·플로팅·/chat이 공유하는 전역 컨텍스트
import { createContext, useCallback, useContext, useState } from 'react';

export type ChatProgress = { label: string; pct?: number | null; run_id?: string } | null;

type ChatControllerValue = {
  activeSessionId: string | null; // 현재 보고 있는 세션(없으면 새 채팅)
  floatingOpen: boolean;
  sessionsVersion: number; // 패널 세션 목록 새로고침 트리거(증가 시 재로드)
  progress: ChatProgress; // 진행 중 표시(스피너 트레이, T17)
  unread: number; // 플로팅이 닫힌 동안 쌓인 알림 수(T18)
  openChat: (sessionId: string | null) => void; // 세션 열기(+플로팅 열기)
  setActiveSessionId: (id: string | null) => void;
  setFloatingOpen: (open: boolean) => void;
  refreshSessions: () => void;
  setProgress: (p: ChatProgress) => void;
  pushUnread: () => void;
  clearUnread: () => void;
};

const ChatControllerContext = createContext<ChatControllerValue | null>(null);

export function ChatControllerProvider({ children }: { children: React.ReactNode }) {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [floatingOpen, setFloatingOpen] = useState(false);
  const [sessionsVersion, setSessionsVersion] = useState(0);
  const [progress, setProgress] = useState<ChatProgress>(null);
  const [unread, setUnread] = useState(0);

  const refreshSessions = useCallback(() => setSessionsVersion((v) => v + 1), []);
  const pushUnread = useCallback(() => setUnread((n) => n + 1), []);
  const clearUnread = useCallback(() => setUnread(0), []);

  // 패널 등에서 세션 클릭/새 채팅 → 활성 세션 지정 + 플로팅 열기(/chat에선 플로팅이 숨겨져 무해).
  const openChat = useCallback((sessionId: string | null) => {
    setActiveSessionId(sessionId);
    setFloatingOpen(true);
  }, []);

  return (
    <ChatControllerContext.Provider
      value={{
        activeSessionId,
        floatingOpen,
        sessionsVersion,
        progress,
        unread,
        openChat,
        setActiveSessionId,
        setFloatingOpen,
        refreshSessions,
        setProgress,
        pushUnread,
        clearUnread,
      }}
    >
      {children}
    </ChatControllerContext.Provider>
  );
}

export function useChatController() {
  const ctx = useContext(ChatControllerContext);
  if (!ctx) throw new Error('useChatController must be used within ChatControllerProvider');
  return ctx;
}
