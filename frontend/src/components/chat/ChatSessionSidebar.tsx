'use client';

// 채팅 세션 사이드바(F2) — 프로젝트의 과거 채팅 세션 목록·전환·삭제·현재 세션 하이라이트.
// 검색(F11) — 세션 제목은 즉시 클라이언트 필터, 메시지 본문은 세션별 메시지를 지연 적재·캐시해 검색.
// /chat/[pid]/[sid] 뷰 좌측 컬럼. 활성 세션은 ChatController(activeSessionId)를 출처로 본다.
import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useChatController } from '@/components/chat/ChatController';
import { api, type ChatSessionRow } from '@/lib/api';
import { formatKST as fmt } from '@/lib/datetime';

// 검색어 매칭 부분을 강조. (대소문자 무시, 첫 매칭만)
function highlight(text: string, q: string) {
  if (!q) return text;
  const i = text.toLowerCase().indexOf(q);
  if (i < 0) return text;
  return (
    <>
      {text.slice(0, i)}
      <mark className='rounded-sm bg-[#FFF1A8] px-0.5 text-inherit dark:bg-[#5B4D00] dark:text-[#F2F4F6]'>
        {text.slice(i, i + q.length)}
      </mark>
      {text.slice(i + q.length)}
    </>
  );
}

export default function ChatSessionSidebar({
  projectId,
}: {
  projectId: string;
}) {
  const router = useRouter();
  const { activeSessionId, sessionsVersion, refreshSessions } =
    useChatController();
  const [sessions, setSessions] = useState<ChatSessionRow[] | undefined>(
    undefined
  );
  const [deleting, setDeleting] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [dQuery, setDQuery] = useState(''); // 디바운스된 소문자 검색어
  const contentRef = useRef<Map<string, string>>(new Map()); // 세션별 메시지 본문 캐시(소문자)
  const [cacheVer, setCacheVer] = useState(0);
  const [searching, setSearching] = useState(false);

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
              messages
                .map(m => m.content)
                .join(' ')
                .toLowerCase()
            )
          )
          .catch(() => contentRef.current.set(s.id, ''))
      )
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
        (contentRef.current.get(s.id) || '').includes(dQuery)
    );
    // cacheVer를 의존성에 넣어 본문 적재 후 재계산.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessions, dQuery, cacheVer]);

  async function onDelete(id: string) {
    setDeleting(id);
    try {
      await api.chat.deleteSession(id);
    } catch {
      // 삭제 실패해도 목록은 갱신 시도
    }
    contentRef.current.delete(id);
    setDeleting(null);
    refreshSessions();
    if (id === activeSessionId) router.push(`/chat/${projectId}/new`);
  }

  return (
    <aside className='hidden md:flex w-60 shrink-0 flex-col border-r border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#161B26]'>
      <div className='p-3 border-b border-[#E5E8EB] dark:border-[#2D3748] space-y-2'>
        <button
          onClick={() => router.push(`/chat/${projectId}/new`)}
          className='w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-[#3182F6] text-white text-sm font-semibold hover:bg-[#1B6EEB] transition-colors'>
          <svg
            width='16'
            height='16'
            viewBox='0 0 24 24'
            fill='none'
            stroke='currentColor'
            strokeWidth='2.5'
            strokeLinecap='round'
            strokeLinejoin='round'>
            <line x1='12' y1='5' x2='12' y2='19' />
            <line x1='5' y1='12' x2='19' y2='12' />
          </svg>
          새 채팅
        </button>
        {/* 검색(F11) — 세션 제목·메시지 본문 */}
        <div className='relative'>
          <svg
            className='absolute left-2.5 top-1/2 -translate-y-1/2 text-[#B0B8C1]'
            width='13'
            height='13'
            viewBox='0 0 24 24'
            fill='none'
            stroke='currentColor'
            strokeWidth='2'
            strokeLinecap='round'
            strokeLinejoin='round'>
            <circle cx='11' cy='11' r='8' />
            <line x1='21' y1='21' x2='16.65' y2='16.65' />
          </svg>
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder='세션·메시지 검색'
            className='w-full pl-8 pr-7 py-1.5 rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] text-xs text-[#191F28] dark:text-[#F2F4F6] placeholder:text-[#B0B8C1] focus:outline-none focus:ring-2 focus:ring-[#3182F6]/40'
          />
          {query && (
            <button
              onClick={() => setQuery('')}
              title='지우기'
              className='absolute right-1.5 top-1/2 -translate-y-1/2 w-5 h-5 flex items-center justify-center rounded text-[#B0B8C1] hover:text-[#191F28] dark:hover:text-[#F2F4F6]'>
              ✕
            </button>
          )}
        </div>
      </div>

      <div className='flex-1 overflow-y-auto p-2 space-y-1'>
        {sessions === undefined ? (
          <p className='text-xs text-[#B0B8C1] px-2 py-3'>불러오는 중...</p>
        ) : sessions.length === 0 ? (
          <p className='text-xs text-[#B0B8C1] px-2 py-3'>
            아직 채팅이 없어요.
          </p>
        ) : filtered && filtered.length === 0 ? (
          <p className='text-xs text-[#B0B8C1] px-2 py-3'>
            {searching
              ? '메시지 내용 검색 중…'
              : `"${query}" 검색 결과가 없어요.`}
          </p>
        ) : (
          (filtered ?? []).map(s => {
            const active = s.id === activeSessionId;
            return (
              <div
                key={s.id}
                className={`group flex items-center gap-1 rounded-lg pr-1 transition-colors ${
                  active
                    ? 'bg-[#EBF3FF] dark:bg-[#1E3A5F]'
                    : 'hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D]'
                }`}>
                <button
                  onClick={() => router.push(`/chat/${projectId}/${s.id}`)}
                  className='flex-1 min-w-0 text-left px-2.5 py-2'
                  title={s.title}>
                  <div className='flex items-center gap-1.5'>
                    <p
                      className={`flex-1 min-w-0 text-[13px] truncate ${
                        active
                          ? 'text-[#3182F6] font-semibold'
                          : 'text-[#191F28] dark:text-[#F2F4F6]'
                      }`}>
                      {highlight(s.title || '새 채팅', dQuery)}
                    </p>
                    {/* N5 미확인 배지 — 활성 세션이 아닐 때만(활성은 보는 중이라 읽음) */}
                    {!active && (s.unread_count ?? 0) > 0 && (
                      <span className='shrink-0 min-w-[16px] h-4 px-1 flex items-center justify-center rounded-full bg-[#F04452] text-white text-[10px] font-bold'>
                        {(s.unread_count ?? 0) > 9 ? '9+' : s.unread_count}
                      </span>
                    )}
                  </div>
                  <p className='text-[10px] text-[#B0B8C1] dark:text-[#4B5563]'>
                    {s.message_count}개
                    {s.updated_at ? ` · ${fmt(s.updated_at)}` : ''}
                    {dQuery &&
                      !(s.title || '').toLowerCase().includes(dQuery) &&
                      (contentRef.current.get(s.id) || '').includes(dQuery) && (
                        <span className='text-[#3182F6]'> · 메시지 일치</span>
                      )}
                  </p>
                </button>
                <button
                  onClick={() => onDelete(s.id)}
                  disabled={deleting === s.id}
                  title='삭제'
                  className='shrink-0 w-7 h-7 flex items-center justify-center rounded-md text-[#B0B8C1] opacity-0 group-hover:opacity-100 hover:text-[#F04452] hover:bg-[#FEF2F2] dark:hover:bg-[#3B0D0D] transition-all disabled:opacity-40'>
                  <svg
                    width='14'
                    height='14'
                    viewBox='0 0 24 24'
                    fill='none'
                    stroke='currentColor'
                    strokeWidth='2'
                    strokeLinecap='round'
                    strokeLinejoin='round'>
                    <polyline points='3 6 5 6 21 6' />
                    <path d='M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2' />
                  </svg>
                </button>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
