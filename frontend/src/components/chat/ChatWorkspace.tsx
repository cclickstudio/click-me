'use client';

// /chat 전용 채팅 워크스페이스 — 좌: 세션 사이드바(새 채팅·검색·목록) / 우: 대화.
// 센터 ChatCenter(좁은 스택형·패널 결합)와 달리, 넓은 페이지용 좌우 2단이며 좌측 패널(프로젝트 선택)과
// 결합하지 않는다(세션 클릭이 패널을 건드리지 않음).

import { useState, useEffect, useCallback, useMemo } from 'react';
import { MessageSquarePlus, Search, X, MessagesSquare } from 'lucide-react';
import { useAuth } from '@/components/AuthProvider';
import { useProjects } from '@/components/ProjectContext';
import { useChatController } from '@/components/chat/ChatController';
import ChatConversation from '@/components/chat/ChatConversation';
import Select from '@/components/ui/Select';
import { api, setAdminOrgId, getAdminOrgId, type CenterSessionRow } from '@/lib/api';
import { formatKST as fmt } from '@/lib/datetime';

export default function ChatWorkspace() {
  const { user } = useAuth();
  const { projects, refresh: refreshProjects } = useProjects();
  const isAdmin = user?.role === 'ADMIN';
  const { activeSessionId, setActiveSessionId, sessionsVersion, refreshSessions, setProgress } =
    useChatController();

  const [sessions, setSessions] = useState<CenterSessionRow[]>([]);
  const [query, setQuery] = useState('');
  const [projectId, setProjectId] = useState('');
  const [orgId, setOrgId] = useState('');
  const [orgs, setOrgs] = useState<{ id: string; name: string }[]>([]);
  // 대화 열림 — 열린 세션의 프로젝트(새 채팅이면 선택 프로젝트). null이면 우측은 빈 상태.
  const [convoProjectId, setConvoProjectId] = useState<string | null>(null);
  const [needProject, setNeedProject] = useState(false);

  // ADMIN — 기업 목록 + 마지막 선택 복원(센터와 동일 규칙).
  useEffect(() => {
    if (!isAdmin) return;
    api.admin.organizations().then(setOrgs).catch(() => setOrgs([]));
    const saved = getAdminOrgId() || '';
    if (saved) setOrgId(saved);
  }, [isAdmin]);

  const loadSessions = useCallback(() => {
    api.center
      .sessions(projectId || undefined)
      .then(({ sessions: rows }) => setSessions(rows))
      .catch(() => setSessions([]));
  }, [projectId]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions, sessionsVersion, orgId]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter(s => (s.title || '').toLowerCase().includes(q));
  }, [sessions, query]);

  // 세션 열기 — 좌측 패널(selectProject)은 건드리지 않는다.
  const openSession = (s: CenterSessionRow) => {
    setActiveSessionId(s.id);
    setConvoProjectId(s.project_id);
    setNeedProject(false);
  };

  // 새 채팅 — 프로젝트가 선택돼 있어야 저장 위치가 정해진다.
  const startNew = () => {
    if (!projectId) {
      setNeedProject(true);
      return;
    }
    setActiveSessionId(null);
    setConvoProjectId(projectId);
    setNeedProject(false);
  };

  const remove = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await api.chat.deleteSession(id);
    } catch {
      /* ignore */
    }
    if (activeSessionId === id) {
      setActiveSessionId(null);
      setConvoProjectId(null);
    }
    refreshSessions();
    loadSessions();
  };

  const handleOrg = (v: string) => {
    setOrgId(v);
    setAdminOrgId(v);
    void refreshProjects();
  };

  const projectOptions = [
    { value: '', label: '전체 프로젝트' },
    ...projects.map(p => ({ value: p.id, label: p.name })),
  ];
  const orgOptions = orgs.map(o => ({ value: o.id, label: o.name }));

  const adminBlocked = isAdmin && !orgId;

  return (
    <div className="flex h-screen bg-surface-0">
      {/* ── 좌: 세션 사이드바 ── */}
      <aside className="flex w-72 shrink-0 flex-col border-r border-line bg-surface-1/40">
        <div className="space-y-2 border-b border-line p-3">
          <div className="flex items-center justify-between">
            <h1 className="text-sm font-bold text-ink">채팅</h1>
            <button
              type="button"
              onClick={startNew}
              className="inline-flex items-center gap-1 rounded-lg bg-primary px-2.5 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary-hover"
            >
              <MessageSquarePlus size={14} />
              새 채팅
            </button>
          </div>
          {isAdmin && (
            <Select
              options={orgOptions}
              value={orgId}
              onChange={handleOrg}
              placeholder="기업 선택"
              aria-label="기업 선택"
            />
          )}
          <Select
            options={projectOptions}
            value={projectId}
            onChange={setProjectId}
            placeholder="전체 프로젝트"
            aria-label="프로젝트 필터"
          />
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-muted" />
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="세션 검색"
              className="w-full rounded-lg border border-line bg-surface-2 py-2 pl-8 pr-2 text-xs text-ink placeholder:text-ink-muted focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </div>
          {needProject && (
            <p className="text-[11px] text-danger">먼저 프로젝트를 선택하면 새 채팅이 열립니다.</p>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {adminBlocked ? (
            <p className="px-2 py-6 text-center text-xs text-ink-muted">기업을 먼저 선택하세요.</p>
          ) : rows.length === 0 ? (
            <p className="px-2 py-6 text-center text-xs text-ink-muted">
              {query ? `"${query}" 결과 없음` : '채팅이 없습니다. 새 채팅으로 시작하세요.'}
            </p>
          ) : (
            rows.map(s => {
              const isActive = s.id === activeSessionId;
              return (
                <div
                  key={s.id}
                  onClick={() => openSession(s)}
                  className={`group flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2 transition-colors ${
                    isActive ? 'bg-primary-subtle' : 'hover:bg-surface-1'
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 shrink-0 rounded-full ${isActive ? 'bg-primary' : 'bg-border-strong'}`}
                  />
                  <div className="min-w-0 flex-1">
                    <p
                      className={`flex items-center gap-1.5 text-xs ${
                        isActive ? 'font-medium text-primary' : 'text-ink-secondary group-hover:text-ink'
                      }`}
                    >
                      <span className="truncate">{s.title || '새 채팅'}</span>
                      {!isActive && (s.unread_count ?? 0) > 0 && (
                        <span className="flex h-4 min-w-[16px] shrink-0 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold text-danger-foreground">
                          {(s.unread_count ?? 0) > 9 ? '9+' : s.unread_count}
                        </span>
                      )}
                    </p>
                    <p className="truncate text-[10px] text-ink-muted">
                      {s.project_name ? `${s.project_name} · ` : ''}
                      {s.message_count}개{s.updated_at ? ` · ${fmt(s.updated_at)}` : ''}
                    </p>
                  </div>
                  <button
                    onClick={e => remove(e, s.id)}
                    title="삭제"
                    className="shrink-0 rounded p-1 text-ink-muted opacity-0 transition-opacity hover:text-danger group-hover:opacity-100"
                  >
                    <X size={13} />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </aside>

      {/* ── 우: 대화 ── */}
      <div className="flex min-w-0 flex-1 flex-col">
        {adminBlocked ? (
          <EmptyPane title="기업을 선택해주세요" desc="좌측 상단에서 기업을 고르면 채팅이 열립니다." />
        ) : convoProjectId === null ? (
          <EmptyPane
            title="세션을 선택하거나 새 채팅을 시작하세요"
            desc="왼쪽에서 대화를 고르거나, ‘새 채팅’으로 CLIO에게 물어보세요."
          />
        ) : (
          <ChatConversation
            projectId={convoProjectId}
            sessionId={activeSessionId}
            onSessionCreated={id => {
              setActiveSessionId(id);
              refreshSessions();
              loadSessions();
            }}
            onActivity={() => {
              refreshSessions();
              loadSessions();
            }}
            onProgress={setProgress}
          />
        )}
      </div>
    </div>
  );
}

function EmptyPane({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
      <div className="mb-1 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary-subtle text-primary">
        <MessagesSquare size={22} />
      </div>
      <p className="text-sm font-semibold text-ink">{title}</p>
      <p className="max-w-xs text-xs leading-relaxed text-ink-tertiary">{desc}</p>
    </div>
  );
}
