'use client';

// /chat — 채팅 워크스페이스(패널 옆 메인에 세션 사이드바 + 대화). 센터 채팅 섹션(ChatCenter)과 동일 구성 재사용.
// URL(/chat/[pid]/[sid])은 진입 시 프로젝트·세션 프리셋으로만 사용(이후 선택은 상태로 관리).
import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { useAuth } from '@/components/AuthProvider';
import { useProjects } from '@/components/ProjectContext';
import { getAdminOrgId, setAdminOrgId } from '@/lib/api';
import CenterFilterBar, { type CenterSegment } from '@/components/center/CenterFilterBar';
import ChatCenter from '@/components/center/ChatCenter';

export default function ChatRoutePage() {
  const params = useParams();
  const slug = (params?.slug as string[] | undefined) ?? [];
  const urlProjectId = slug[0] ?? '';
  const urlSessionId = slug[1] && slug[1] !== 'new' ? slug[1] : null;

  const { user } = useAuth();
  const { projects, refresh: refreshProjects } = useProjects();
  const isAdmin = user?.role === 'ADMIN';

  const [segment, setSegment] = useState<CenterSegment>('all');
  const [projectId, setProjectId] = useState(urlProjectId);
  const [orgId, setOrgId] = useState('');
  // URL에 세션이 있으면 진입 즉시 그 세션을 대화로 연다(센터의 openTarget과 동일 신호).
  const [openTarget, setOpenTarget] = useState<{ sessionId: string; projectId: string } | null>(
    urlSessionId ? { sessionId: urlSessionId, projectId: urlProjectId } : null,
  );

  // ADMIN 마지막 선택 기업 복원(센터와 동일 규칙) — 없으면 기업 선택 유도.
  useEffect(() => {
    if (!isAdmin) return;
    const saved = getAdminOrgId() || '';
    if (saved) setOrgId(saved);
  }, [isAdmin]);

  const handleOrgId = (v: string) => {
    setOrgId(v);
    setAdminOrgId(v);
    void refreshProjects();
  };

  if (!user) return null;

  return (
    <div className="flex h-screen flex-col bg-surface-0">
      <CenterFilterBar
        segment={segment}
        onSegment={setSegment}
        projectId={projectId}
        onProjectId={setProjectId}
        projects={projects}
        isAdmin={isAdmin}
        orgId={orgId}
        onOrgId={handleOrgId}
      />
      {isAdmin && !orgId ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-1 p-6 text-center">
          <p className="text-sm font-medium text-ink">기업을 선택해주세요</p>
          <p className="text-xs text-ink-tertiary">
            상단 기업 드롭다운에서 기업을 고르면 채팅이 열립니다.
          </p>
        </div>
      ) : (
        <div className="flex flex-1 flex-col overflow-hidden">
          <ChatCenter
            projectId={projectId}
            segment={segment}
            readOnly={user?.role === 'COMPANY'}
            orgKey={orgId}
            openTarget={openTarget}
            onOpenConsumed={() => setOpenTarget(null)}
          />
        </div>
      )}
    </div>
  );
}
