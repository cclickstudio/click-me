'use client';

// /chat/[pid] 진입 게이트 — 기존 세션 이어가기 / 새 채팅 시작 선택.
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useProjects } from '@/components/ProjectContext';
import { useChatController } from '@/components/chat/ChatController';
import { api, type ChatSessionRow } from '@/lib/api';

const fmt = (iso?: string | null) => {
  if (!iso) return '';
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};

export default function ChatSessionGate({ projectId }: { projectId: string }) {
  const router = useRouter();
  const { selectProject, selectedProjectId, projects } = useProjects();
  const { sessionsVersion } = useChatController();
  const [sessions, setSessions] = useState<ChatSessionRow[] | undefined>(undefined);

  const projectName = projects.find((p) => p.id === projectId)?.name ?? '프로젝트';

  // 패널 하이라이트 동기화.
  useEffect(() => {
    if (selectedProjectId !== projectId) selectProject(projectId);
  }, [projectId, selectedProjectId, selectProject]);

  useEffect(() => {
    let alive = true;
    api.chat
      .sessions(projectId)
      .then(({ sessions }) => alive && setSessions(sessions))
      .catch(() => alive && setSessions([]));
    return () => {
      alive = false;
    };
  }, [projectId, sessionsVersion]);

  return (
    <div className="h-screen flex flex-col items-center justify-center px-4 bg-white dark:bg-[#0F1117] transition-colors">
      <div className="w-full max-w-lg">
          <p className="text-[11px] font-semibold text-[#8B95A1] dark:text-[#6B7280] uppercase tracking-wide mb-1">
            {projectName}
          </p>
          <h2 className="text-xl font-bold text-[#191F28] dark:text-[#F2F4F6] mb-5">채팅 시작</h2>

          <button
            onClick={() => router.push(`/chat/${projectId}/new`)}
            className="w-full flex items-center gap-3 p-4 rounded-xl bg-[#3182F6] text-white hover:bg-[#1B6EEB] transition-colors mb-5"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            <span className="text-sm font-semibold">새 채팅 시작</span>
          </button>

          <p className="text-[11px] font-semibold text-[#8B95A1] dark:text-[#6B7280] uppercase tracking-wide mb-2">
            기존 채팅 이어가기
          </p>
          {sessions === undefined ? (
            <p className="text-sm text-[#B0B8C1] px-1 py-2">불러오는 중...</p>
          ) : sessions.length === 0 ? (
            <p className="text-sm text-[#B0B8C1] px-1 py-2">아직 채팅이 없어요. 새 채팅으로 시작하세요.</p>
          ) : (
            <div className="space-y-1.5 max-h-[40vh] overflow-y-auto">
              {sessions.map((s) => (
                <button
                  key={s.id}
                  onClick={() => router.push(`/chat/${projectId}/${s.id}`)}
                  className="w-full flex items-center gap-3 p-3 text-left rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] hover:border-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors"
                >
                  <span className="w-7 h-7 shrink-0 flex items-center justify-center rounded-lg bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6]">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                    </svg>
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-[#191F28] dark:text-[#F2F4F6] truncate">{s.title}</p>
                    <p className="text-[10px] text-[#B0B8C1] dark:text-[#4B5563]">
                      {s.message_count}개 메시지{s.updated_at ? ` · ${fmt(s.updated_at)}` : ''}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          )}
      </div>
    </div>
  );
}
