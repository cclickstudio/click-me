'use client';

// 프로젝트 패널의 채팅 섹션 — 그 프로젝트의 채팅 세션 목록 + 새 채팅.
// 항목 클릭 시 /chat 라우팅이 아니라 컨트롤러로 활성 세션 전환(플로팅/대화가 그 세션으로 바뀜).
import { useCallback, useEffect, useState } from 'react';
import { useProjects } from '../ProjectContext';
import { useChatController } from './ChatController';
import { api, type ChatSessionRow } from '@/lib/api';

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="13" height="13" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
      className={`transition-transform duration-150 shrink-0 ${open ? 'rotate-90' : ''}`}
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

export default function ProjectChatSection({ projectId }: { projectId: string }) {
  const { selectProject } = useProjects();
  const { activeSessionId, openChat, sessionsVersion, refreshSessions } = useChatController();
  const [open, setOpen] = useState(false);
  const [sessions, setSessions] = useState<ChatSessionRow[] | undefined>(undefined);

  const load = useCallback(async () => {
    try {
      const { sessions: rows } = await api.chat.sessions(projectId);
      setSessions(rows);
    } catch {
      setSessions([]);
    }
  }, [projectId]);

  // 펼쳐져 있을 때 다른 곳에서 채팅이 생기거나 제목이 바뀌면(sessionsVersion) 새로고침.
  useEffect(() => {
    if (open) load();
  }, [open, sessionsVersion, load]);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && sessions === undefined) load();
  };

  const startNew = (e: React.MouseEvent) => {
    e.stopPropagation();
    selectProject(projectId);
    openChat(null);
  };

  const openSession = (id: string) => {
    selectProject(projectId);
    openChat(id);
  };

  const remove = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await api.chat.deleteSession(id);
    } catch {
      // ignore
    }
    if (activeSessionId === id) openChat(null);
    refreshSessions();
    load();
  };

  const count = sessions?.length ?? 0;

  return (
    <div>
      <button
        onClick={toggle}
        className="w-full flex items-center gap-2 px-2 py-1.5 hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] rounded-md transition-colors"
      >
        <Chevron open={open} />
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[#8B95A1] shrink-0">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        <span className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] uppercase tracking-wide">
          채팅{count > 0 ? ` (${count})` : ''}
        </span>
      </button>

      {open && (
        <div className="ml-4 space-y-0.5">
          {sessions === undefined ? (
            <p className="text-xs text-[#B0B8C1] px-2 py-1">불러오는 중...</p>
          ) : sessions.length === 0 ? (
            <p className="text-xs text-[#B0B8C1] px-2 py-1">채팅 없음</p>
          ) : (
            sessions.map((s) => {
              const isActive = s.id === activeSessionId;
              return (
                <div
                  key={s.id}
                  onClick={() => openSession(s.id)}
                  className={`group flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer transition-colors ${
                    isActive ? 'bg-[#EBF3FF] dark:bg-[#1E3A5F]' : 'hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F]'
                  }`}
                >
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isActive ? 'bg-[#3182F6]' : 'bg-[#B0B8C1]'}`} />
                  <div className="flex-1 min-w-0">
                    <p className={`text-xs truncate ${isActive ? 'text-[#3182F6] font-medium' : 'text-[#4E5968] dark:text-[#9CA3AF] group-hover:text-[#3182F6]'}`}>
                      {s.title}
                    </p>
                    <p className="text-[10px] text-[#B0B8C1] dark:text-[#4B5563]">{s.message_count}개 메시지</p>
                  </div>
                  <button
                    onClick={(e) => remove(e, s.id)}
                    title="삭제"
                    className="opacity-0 group-hover:opacity-100 text-[#B0B8C1] hover:text-[#F04452] text-xs shrink-0 px-1"
                  >
                    ✕
                  </button>
                </div>
              );
            })
          )}
          <button
            onClick={startNew}
            className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md text-xs text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            새 채팅
          </button>
        </div>
      )}
    </div>
  );
}
