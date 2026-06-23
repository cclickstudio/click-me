'use client';

// /chat 탭 — 전체 화면 채팅. 세션 목록은 좌측 프로젝트 패널(ProjectPanel)에서 고른다(자체 사이드바 없음).
import AppLayout from '@/components/AppLayout';
import { useProjects } from '@/components/ProjectContext';
import { useChatController } from '@/components/chat/ChatController';
import ChatConversation from '@/components/chat/ChatConversation';

export default function Page() {
  const { projects, selectedProject, selectProject } = useProjects();
  const { activeSessionId, setActiveSessionId, refreshSessions } = useChatController();

  // ── 프로젝트 미선택 — 채팅 시작 전 프로젝트를 먼저 고르게 한다 ──
  if (!selectedProject) {
    return (
      <AppLayout>
        <div className="h-screen flex flex-col items-center justify-center px-4 bg-white dark:bg-[#0F1117] transition-colors">
          <div className="mb-3 w-12 h-12 flex items-center justify-center rounded-2xl bg-[#EBF3FF] dark:bg-[#1E3A5F]">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#3182F6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-[#191F28] dark:text-[#F2F4F6] mb-2">먼저 프로젝트를 선택하세요</h2>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mb-8 text-center leading-relaxed">
            채팅은 프로젝트에 저장됩니다.<br />프로젝트를 고르면 왼쪽 패널에서 그 프로젝트의 채팅 목록을 볼 수 있어요.
          </p>
          {projects.length === 0 ? (
            <p className="text-sm text-[#B0B8C1]">사용 가능한 프로젝트가 없습니다. 먼저 프로젝트를 생성하세요.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
              {projects.map((p) => (
                <button
                  key={p.id}
                  onClick={() => selectProject(p.id)}
                  className="p-4 text-left bg-[#F9FAFB] dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl hover:border-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-all"
                >
                  <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">{p.name}</p>
                  {p.organization_name && (
                    <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-0.5">{p.organization_name}</p>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="h-screen">
        <ChatConversation
          projectId={selectedProject.id}
          sessionId={activeSessionId}
          onSessionCreated={(id) => {
            setActiveSessionId(id);
            refreshSessions();
          }}
          onActivity={refreshSessions}
        />
      </div>
    </AppLayout>
  );
}
