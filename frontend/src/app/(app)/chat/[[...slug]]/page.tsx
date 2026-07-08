'use client';

// 채팅 라우트(catch-all) — /chat(프로젝트 게이트) · /chat/[pid](새 채팅) · /chat/[pid]/[sid](세션).
// 단일 컴포넌트라 pid↔sid 전환 시 리마운트가 없다(새 세션 생성 후 URL만 갱신).
// (app) Route Group 안에 있어 AppLayout(사이드바·패널)은 그룹 레이아웃이 한 번만 제공한다.
import { useParams, useRouter } from 'next/navigation';
import { useProjects } from '@/components/ProjectContext';
import ChatRouteView from '@/components/chat/ChatRouteView';
import ChatSessionGate from '@/components/chat/ChatSessionGate';

export default function ChatRoutePage() {
  const params = useParams();
  const slug = (params?.slug as string[] | undefined) ?? [];
  const projectId = slug[0] ?? null;
  const sessionId = slug[1] ?? null;

  // /chat → 프로젝트 게이트
  if (!projectId) return <ChatProjectGate />;
  // /chat/[pid] → 세션 선택 게이트(기존 이어가기 / 새 채팅)
  if (!sessionId) return <ChatSessionGate projectId={projectId} />;
  // /chat/[pid]/new → 새 채팅, /chat/[pid]/[sid] → 기존 세션
  return <ChatRouteView projectId={projectId} sessionId={sessionId === 'new' ? null : sessionId} />;
}

function ChatProjectGate() {
  const router = useRouter();
  const { projects } = useProjects();

  return (
    <div className="h-screen flex flex-col items-center justify-center px-4 bg-white dark:bg-[#0F1117] transition-colors">
      <div className="mb-3 w-12 h-12 flex items-center justify-center rounded-2xl bg-primary-subtle">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#2563EB" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      </div>
      <h2 className="text-xl font-bold text-ink mb-2">먼저 프로젝트를 선택하세요</h2>
      <p className="text-sm text-ink-tertiary mb-8 text-center leading-relaxed">
        채팅은 프로젝트에 저장됩니다.<br />프로젝트를 고르면 그 프로젝트의 채팅으로 이동합니다.
      </p>
      {projects.length === 0 ? (
        <p className="text-sm text-ink-muted">사용 가능한 프로젝트가 없습니다. 먼저 프로젝트를 생성하세요.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => router.push(`/chat/${p.id}`)}
              className="p-4 text-left bg-surface-1 border border-line rounded-xl hover:border-primary hover:bg-primary-subtle transition-all"
            >
              <p className="text-sm font-semibold text-ink">{p.name}</p>
              {p.organization_name && (
                <p className="text-xs text-ink-tertiary mt-0.5">{p.organization_name}</p>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
