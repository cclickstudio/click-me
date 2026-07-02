'use client';

// 프로젝트 패널의 채팅 섹션 — 세션 목록·검색·전환·삭제·새 채팅·미확인 알림.
// 검색(F11): 세션 제목은 즉시 클라이언트 필터, 메시지 본문은 세션별로 지연 적재·캐시해 검색.
// 항목 클릭 시 /chat 라우팅이 아니라 컨트롤러로 활성 세션 전환(플로팅/대화가 그 세션으로 바뀜).
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useProjects } from '../ProjectContext';
import { useChatController } from './ChatController';
import { api, type ChatSessionRow } from '@/lib/api';
import { formatKST as fmt } from '@/lib/datetime';

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

// 검색어 매칭 부분을 강조(대소문자 무시, 첫 매칭만).
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

export default function ProjectChatSection({ projectId }: { projectId: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const onChatPage = pathname?.startsWith('/chat') ?? false;
  const { selectProject, chatRefreshKey } = useProjects();
  const { activeSessionId, openChat, sessionsVersion, refreshSessions } = useChatController();
  const [open, setOpen] = useState(false);
  const [sessions, setSessions] = useState<ChatSessionRow[] | undefined>(undefined);
  const [query, setQuery] = useState('');
  const [dQuery, setDQuery] = useState(''); // 디바운스된 소문자 검색어
  const contentRef = useRef<Map<string, string>>(new Map()); // 세션별 메시지 본문 캐시(소문자)
  const [cacheVer, setCacheVer] = useState(0);
  const [searching, setSearching] = useState(false);

  const load = useCallback(async () => {
    try {
      const { sessions: rows } = await api.chat.sessions(projectId);
      setSessions(rows);
    } catch {
      setSessions([]);
    }
  }, [projectId]);

  // 마운트·갱신 시 항상 로드 — 접힌 상태에서도 헤더 미확인 배지를 보여주려면 데이터가 필요하다.
  // chatRefreshKey: 패널 새로고침 버튼(refreshAll)이 올리는 신호 → 채팅 세션도 함께 갱신.
  useEffect(() => {
    load();
  }, [sessionsVersion, chatRefreshKey, load]);

  // 검색어 디바운스.
  useEffect(() => {
    const t = setTimeout(() => setDQuery(query.trim().toLowerCase()), 250);
    return () => clearTimeout(t);
  }, [query]);

  // 검색 시작 시, 아직 캐시 안 된 세션의 메시지 본문을 적재(본문 검색용). 1회 적재 후 캐시.
  useEffect(() => {
    if (!dQuery || !sessions) return;
    const missing = sessions.filter(s => !contentRef.current.has(s.id));
    if (missing.length === 0) return;
    let alive = true;
    setSearching(true);
    Promise.all(
      missing.map(s =>
        api.chat
          .messages(s.id)
          .then(({ messages }) =>
            contentRef.current.set(
              s.id,
              messages.map(m => m.content).join(' ').toLowerCase(),
            ),
          )
          .catch(() => contentRef.current.set(s.id, '')),
      ),
    ).then(() => {
      if (!alive) return;
      setCacheVer(v => v + 1);
      setSearching(false);
    });
    return () => {
      alive = false;
    };
  }, [dQuery, sessions]);

  const filtered = useMemo(() => {
    if (!sessions || !dQuery) return sessions;
    return sessions.filter(
      s =>
        (s.title || '').toLowerCase().includes(dQuery) ||
        (contentRef.current.get(s.id) || '').includes(dQuery),
    );
    // cacheVer를 의존성에 넣어 본문 적재 후 재계산.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessions, dQuery, cacheVer]);

  const toggle = () => setOpen(v => !v);

  // 새 채팅은 항상 채팅 페이지(/chat/[pid]/new)로 라우팅한다.
  const startNew = (e: React.MouseEvent) => {
    e.stopPropagation();
    selectProject(projectId);
    router.push(`/chat/${projectId}/new`);
  };

  const openSession = (id: string) => {
    selectProject(projectId);
    if (onChatPage) router.push(`/chat/${projectId}/${id}`);
    else openChat(id);
  };

  const remove = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await api.chat.deleteSession(id);
    } catch {
      // ignore
    }
    contentRef.current.delete(id);
    if (activeSessionId === id) openChat(null);
    refreshSessions();
    load();
  };

  const count = sessions?.length ?? 0;
  // N5 미확인 합계 — 활성 세션은 보는 중이라 제외(읽음 처리).
  const totalUnread = (sessions ?? []).reduce(
    (a, s) => a + (s.id === activeSessionId ? 0 : s.unread_count ?? 0),
    0,
  );
  const rows = filtered ?? sessions;

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
        {/* N5 미확인 합계 배지 — 접힌 상태에서도 미확인 알림이 보이게 헤더에 노출 */}
        {totalUnread > 0 && (
          <span className="ml-auto shrink-0 min-w-[16px] h-4 px-1 flex items-center justify-center rounded-full bg-[#F04452] text-white text-[10px] font-bold">
            {totalUnread > 9 ? '9+' : totalUnread}
          </span>
        )}
      </button>

      {open && (
        <div className="ml-4 space-y-0.5">
          <button
            onClick={startNew}
            className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md text-xs text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            새 채팅
          </button>
          {/* 검색(F11) — 세션 제목·메시지 본문 */}
          <div className="relative px-2 py-1">
            <svg
              className="absolute left-4 top-1/2 -translate-y-1/2 text-[#B0B8C1]"
              width="12" height="12" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="세션·메시지 검색"
              className="w-full pl-7 pr-6 py-1 rounded-md border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] text-[11px] text-[#191F28] dark:text-[#F2F4F6] placeholder:text-[#B0B8C1] focus:outline-none focus:ring-2 focus:ring-[#3182F6]/40"
            />
            {query && (
              <button
                onClick={() => setQuery('')}
                title="지우기"
                className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 flex items-center justify-center rounded text-[#B0B8C1] hover:text-[#191F28] dark:hover:text-[#F2F4F6]"
              >
                ✕
              </button>
            )}
          </div>

          {sessions === undefined ? (
            <p className="text-xs text-[#B0B8C1] px-2 py-1">불러오는 중...</p>
          ) : sessions.length === 0 ? (
            <p className="text-xs text-[#B0B8C1] px-2 py-1">채팅 없음</p>
          ) : rows && rows.length === 0 ? (
            <p className="text-xs text-[#B0B8C1] px-2 py-1">
              {searching ? '메시지 내용 검색 중…' : `"${query}" 검색 결과가 없어요.`}
            </p>
          ) : (
            (rows ?? []).map((s) => {
              const isActive = s.id === activeSessionId;
              const contentHit =
                !!dQuery &&
                !(s.title || '').toLowerCase().includes(dQuery) &&
                (contentRef.current.get(s.id) || '').includes(dQuery);
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
                    <p className={`text-xs flex items-center gap-1.5 ${isActive ? 'text-[#3182F6] font-medium' : 'text-[#4E5968] dark:text-[#9CA3AF] group-hover:text-[#3182F6]'}`}>
                      <span className="truncate">{highlight(s.title || '새 채팅', dQuery)}</span>
                      {/* N5 미확인 배지 — 활성 세션이 아닐 때만(활성은 보는 중이라 읽음) */}
                      {!isActive && (s.unread_count ?? 0) > 0 && (
                        <span className="shrink-0 min-w-[16px] h-4 px-1 flex items-center justify-center rounded-full bg-[#F04452] text-white text-[10px] font-bold">
                          {(s.unread_count ?? 0) > 9 ? '9+' : s.unread_count}
                        </span>
                      )}
                    </p>
                    <p className="text-[10px] text-[#B0B8C1] dark:text-[#4B5563]">
                      {s.message_count}개
                      {s.updated_at ? ` · ${fmt(s.updated_at)}` : ''}
                      {contentHit && <span className="text-[#3182F6]"> · 메시지 일치</span>}
                    </p>
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
        </div>
      )}
    </div>
  );
}
