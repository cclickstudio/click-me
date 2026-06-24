'use client';

// URL(/chat/[pid]/[sid]) ↔ 전역 상태 동기화 래퍼 — 플로팅도 같은 activeSessionId를 읽어 세션이 이어진다.
import { useEffect } from 'react';
import { useProjects } from '@/components/ProjectContext';
import { useChatController } from '@/components/chat/ChatController';
import ChatConversation from '@/components/chat/ChatConversation';

export default function ChatRouteView({
  projectId,
  sessionId,
}: {
  projectId: string;
  sessionId: string | null;
}) {
  const { selectProject, selectedProjectId } = useProjects();
  const { setActiveSessionId, refreshSessions } = useChatController();

  // URL의 프로젝트를 전역 선택과 동기화(패널 하이라이트·플로팅 공유용).
  useEffect(() => {
    if (selectedProjectId !== projectId) selectProject(projectId);
  }, [projectId, selectedProjectId, selectProject]);

  // URL의 세션을 활성 세션으로 — 플로팅·패널이 같은 세션을 보게 한다.
  useEffect(() => {
    setActiveSessionId(sessionId);
  }, [sessionId, setActiveSessionId]);

  return (
    <div className="h-screen">
      <ChatConversation
        projectId={projectId}
        sessionId={sessionId}
        onSessionCreated={(id) => {
          setActiveSessionId(id);
          refreshSessions();
          // Next 라우터(router.replace)는 catch-all에서도 페이지를 리마운트시켜 진행 중 대화를 날린다.
          // Next 14 공식 shallow routing(history.replaceState)으로 URL만 갱신 — 리마운트 없이 새로고침·딥링크 대응.
          window.history.replaceState(null, '', `/chat/${projectId}/${id}`);
        }}
        onActivity={refreshSessions}
      />
    </div>
  );
}
