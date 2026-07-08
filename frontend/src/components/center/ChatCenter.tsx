'use client';

// 채팅 센터 — 세션 목록(전체/프로젝트 통합) + 세션 선택 시 하단 50% 라이브 채팅. 스펙 §6.
// ProjectChatSection(목록·검색·새채팅·삭제·미확인) + FloatingChat(ChatConversation 대화)을 통합 이관.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useProjects } from '../ProjectContext';
import { useChatController } from '../chat/ChatController';
import ChatConversation from '../chat/ChatConversation';
import { api, type CenterSessionRow } from '@/lib/api';
import { formatKST as fmt } from '@/lib/datetime';
import type { CenterSegment } from './CenterFilterBar';

function highlight(text: string, q: string) {
  if (!q) return text;
  const i = text.toLowerCase().indexOf(q);
  if (i < 0) return text;
  return (
    <>
      {text.slice(0, i)}
      <mark className="rounded-sm bg-[#FFF1A8] px-0.5 text-inherit dark:bg-[#5B4D00] dark:text-[#F2F4F6]">
        {text.slice(i, i + q.length)}
      </mark>
      {text.slice(i + q.length)}
    </>
  );
}

export default function ChatCenter({
  projectId,
  segment,
  readOnly = false,
  orgKey,
  openTarget,
  onOpenConsumed,
}: {
  projectId: string;
  segment: CenterSegment;
  readOnly?: boolean;
  orgKey?: string; // 변경 시 재조회 트리거(ADMIN 기업 전환 — projectId 불변이어도 스코프가 바뀜)
  openTarget?: { sessionId: string; projectId: string } | null; // 알림 상담하기 → 세션 열기 신호
  onOpenConsumed?: () => void;
}) {
  const { selectProject, chatRefreshKey } = useProjects();
  const {
    activeSessionId,
    setActiveSessionId,
    sessionsVersion,
    refreshSessions,
    progress,
    setProgress,
  } = useChatController();

  const [sessions, setSessions] = useState<CenterSessionRow[] | undefined>(undefined);
  const [query, setQuery] = useState('');
  const [dQuery, setDQuery] = useState('');
  const contentRef = useRef<Map<string, string>>(new Map());
  const [cacheVer, setCacheVer] = useState(0);
  const [searching, setSearching] = useState(false);
  // 대화 열림 — 열린 세션의 프로젝트(전체 프로젝트 모드에서도 세션의 project_id로 대화 가능).
  const [convoProjectId, setConvoProjectId] = useState<string | null>(null);
  const [needProject, setNeedProject] = useState(false);

  const load = useCallback(async () => {
    try {
      const { sessions: rows } = await api.center.sessions(projectId || undefined);
      setSessions(rows);
    } catch {
      setSessions([]);
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [sessionsVersion, chatRefreshKey, orgKey, load]);

  // 알림 상담하기 신호 — 지정 세션을 하단 라이브 채팅으로 연다.
  useEffect(() => {
    if (!openTarget) return;
    if (openTarget.projectId) selectProject(openTarget.projectId);
    setActiveSessionId(openTarget.sessionId);
    setConvoProjectId(openTarget.projectId);
    setNeedProject(false);
    refreshSessions();
    onOpenConsumed?.();
  }, [openTarget, selectProject, setActiveSessionId, refreshSessions, onOpenConsumed]);

  // 검색어 디바운스.
  useEffect(() => {
    const t = setTimeout(() => setDQuery(query.trim().toLowerCase()), 250);
    return () => clearTimeout(t);
  }, [query]);

  // 메시지 본문 검색 — 미캐시 세션 본문 지연 적재 후 캐시(ProjectChatSection과 동일 규칙).
  useEffect(() => {
    if (!dQuery || !sessions) return;
    const missing = sessions.filter((s) => !contentRef.current.has(s.id));
    if (missing.length === 0) return;
    let alive = true;
    setSearching(true);
    Promise.all(
      missing.map((s) =>
        api.chat
          .messages(s.id)
          .then(({ messages }) =>
            contentRef.current.set(s.id, messages.map((m) => m.content).join(' ').toLowerCase()),
          )
          .catch(() => contentRef.current.set(s.id, '')),
      ),
    ).then(() => {
      if (!alive) return;
      setCacheVer((v) => v + 1);
      setSearching(false);
    });
    return () => {
      alive = false;
    };
  }, [dQuery, sessions]);

  // 세그먼트(unread_count) + 검색 필터.
  const rows = useMemo(() => {
    let list = sessions ?? [];
    if (segment === 'unread') list = list.filter((s) => (s.unread_count ?? 0) > 0);
    else if (segment === 'read') list = list.filter((s) => (s.unread_count ?? 0) === 0);
    if (dQuery)
      list = list.filter(
        (s) =>
          (s.title || '').toLowerCase().includes(dQuery) ||
          (contentRef.current.get(s.id) || '').includes(dQuery),
      );
    return list;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessions, segment, dQuery, cacheVer]);

  const openSession = (s: CenterSessionRow) => {
    if (s.project_id) selectProject(s.project_id);
    setActiveSessionId(s.id);
    setConvoProjectId(s.project_id);
    setNeedProject(false);
  };

  // 새 채팅 — 특정 프로젝트 선택 시 그 프로젝트로 새 대화. 전체 프로젝트면 선택 유도(스펙 §6).
  const startNew = () => {
    if (!projectId) {
      setNeedProject(true);
      return;
    }
    selectProject(projectId);
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
    contentRef.current.delete(id);
    if (activeSessionId === id) {
      setActiveSessionId(null);
      setConvoProjectId(null);
    }
    refreshSessions();
    load();
  };

  const closeConvo = () => {
    setConvoProjectId(null);
    setNeedProject(false);
  };

  const showConvo = convoProjectId !== null;

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* 세션 목록 — 대화 열리면 상단 50%, 아니면 전체 높이(스펙 §6). */}
      <div className={`flex flex-col overflow-hidden ${showConvo ? 'min-h-0 flex-1' : 'flex-1'}`}>
        <div className="flex items-center gap-2 px-3 py-2">
          {!readOnly && (
            <button
              type="button"
              onClick={startNew}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-primary hover:bg-primary-subtle"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              새 채팅
            </button>
          )}
          <div className="relative ml-auto flex-1">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="세션·메시지 검색"
              className="w-full rounded-md border border-line bg-white px-2 py-1 text-[11px] text-ink placeholder:text-ink-muted focus:outline-none focus:ring-2 focus:ring-primary/40 dark:bg-[#1C2333] dark:text-[#F2F4F6]"
            />
          </div>
        </div>
        {needProject && (
          <p className="px-3 pb-1 text-[11px] text-[#F04452]">
            상단 필터에서 프로젝트를 먼저 선택해 주세요.
          </p>
        )}
        <div className="flex-1 overflow-y-auto px-2">
          {sessions === undefined ? (
            <p className="px-2 py-3 text-xs text-ink-muted">불러오는 중…</p>
          ) : rows.length === 0 ? (
            <p className="px-2 py-3 text-xs text-ink-muted">
              {searching ? '메시지 내용 검색 중…' : dQuery ? `"${query}" 결과 없음` : '채팅 없음'}
            </p>
          ) : (
            rows.map((s) => {
              const isActive = s.id === activeSessionId;
              return (
                <div
                  key={s.id}
                  onClick={() => openSession(s)}
                  className={`group flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 transition-colors ${
                    isActive
                      ? 'bg-primary-subtle'
                      : 'hover:bg-primary-subtle'
                  }`}
                >
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${isActive ? 'bg-primary' : 'bg-[#B0B8C1]'}`} />
                  <div className="min-w-0 flex-1">
                    <p className={`flex items-center gap-1.5 text-xs ${isActive ? 'font-medium text-primary' : 'text-ink-secondary group-hover:text-primary'}`}>
                      <span className="truncate">{highlight(s.title || '새 채팅', dQuery)}</span>
                      {!isActive && (s.unread_count ?? 0) > 0 && (
                        <span className="flex h-4 min-w-[16px] shrink-0 items-center justify-center rounded-full bg-[#F04452] px-1 text-[10px] font-bold text-white">
                          {(s.unread_count ?? 0) > 9 ? '9+' : s.unread_count}
                        </span>
                      )}
                    </p>
                    <p className="text-[10px] text-ink-muted">
                      {!projectId && s.project_name ? `${s.project_name} · ` : ''}
                      {s.message_count}개{s.updated_at ? ` · ${fmt(s.updated_at)}` : ''}
                    </p>
                  </div>
                  {!readOnly && (
                    <button
                      onClick={(e) => remove(e, s.id)}
                      title="삭제"
                      className="shrink-0 px-1 text-xs text-ink-muted opacity-0 hover:text-[#F04452] group-hover:opacity-100"
                    >
                      ✕
                    </button>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* 라이브 채팅 — 세션 선택/새 채팅 시 하단 50%. 기존 ChatConversation 재사용. */}
      {showConvo && convoProjectId && (
        <div className="flex h-[50vh] shrink-0 flex-col overflow-hidden border-t border-line">
          <div className="flex h-8 shrink-0 items-center justify-between px-3">
            {progress ? (
              <span className="flex items-center gap-1.5 truncate text-xs font-semibold text-primary">
                <span className="h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-primary/30 border-t-[#2563EB]" />
                {progress.label}
                {typeof progress.pct === 'number' ? ` ${progress.pct}%` : ''}
              </span>
            ) : (
              <span className="text-[11px] text-ink-tertiary">
                {readOnly ? '읽기 전용' : activeSessionId ? '대화' : '새 채팅'}
              </span>
            )}
            <button
              type="button"
              onClick={closeConvo}
              title="목록만 보기"
              className="flex h-6 w-6 items-center justify-center rounded text-ink-tertiary hover:bg-accent"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
          <div className="min-h-0 flex-1">
            {readOnly ? (
              <ReadOnlyConversation projectId={convoProjectId} sessionId={activeSessionId} />
            ) : (
              <ChatConversation
                projectId={convoProjectId}
                sessionId={activeSessionId}
                onSessionCreated={(id) => {
                  setActiveSessionId(id);
                  refreshSessions();
                }}
                onActivity={refreshSessions}
                onProgress={setProgress}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// COMPANY 읽기전용 — 메시지 이력만 표시(입력·SSE·읽음처리 없음, 스펙 §7).
function ReadOnlyConversation({
  projectId,
  sessionId,
}: {
  projectId: string;
  sessionId: string | null;
}) {
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  useEffect(() => {
    void projectId;
    if (!sessionId) {
      setMessages([]);
      return;
    }
    let alive = true;
    api.chat
      .messages(sessionId)
      .then(({ messages: m }) => {
        if (alive) setMessages(m.map((x) => ({ role: x.role, content: x.content })));
      })
      .catch(() => {
        if (alive) setMessages([]);
      });
    return () => {
      alive = false;
    };
  }, [sessionId, projectId]);

  return (
    <div className="h-full space-y-2 overflow-y-auto px-3 py-2">
      {messages.length === 0 ? (
        <p className="py-6 text-center text-xs text-ink-tertiary">표시할 대화가 없어요.</p>
      ) : (
        messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[85%] rounded-lg px-2.5 py-1.5 text-xs ${
              m.role === 'user'
                ? 'ml-auto bg-primary text-primary-foreground'
                : 'bg-[#F2F4F6] text-ink dark:bg-[#252D3D] dark:text-[#F2F4F6]'
            }`}
          >
            {m.content}
          </div>
        ))
      )}
    </div>
  );
}
