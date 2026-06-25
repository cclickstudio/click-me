'use client';

// 채팅 세션 사이드바(F2) — 프로젝트의 과거 채팅 세션 목록·전환·삭제·현재 세션 하이라이트.
// /chat/[pid]/[sid] 뷰 좌측 컬럼. 활성 세션은 ChatController(activeSessionId)를 출처로 본다
// (새 채팅 첫 전송으로 세션이 생기면 URL은 shallow 갱신돼 prop이 안 바뀌므로 전역 상태로 하이라이트).
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useChatController } from '@/components/chat/ChatController';
import { api, type ChatSessionRow } from '@/lib/api';
import { formatKST as fmt } from '@/lib/datetime';

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

  async function onDelete(id: string) {
    setDeleting(id);
    try {
      await api.chat.deleteSession(id);
    } catch {
      // 삭제 실패해도 목록은 갱신 시도
    }
    setDeleting(null);
    refreshSessions();
    // 현재 보던 세션을 지웠으면 새 채팅으로 이동.
    if (id === activeSessionId) router.push(`/chat/${projectId}/new`);
  }

  return (
    <aside className='hidden md:flex w-60 shrink-0 flex-col border-r border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#161B26]'>
      <div className='p-3 border-b border-[#E5E8EB] dark:border-[#2D3748]'>
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
      </div>

      <div className='flex-1 overflow-y-auto p-2 space-y-1'>
        {sessions === undefined ? (
          <p className='text-xs text-[#B0B8C1] px-2 py-3'>불러오는 중...</p>
        ) : sessions.length === 0 ? (
          <p className='text-xs text-[#B0B8C1] px-2 py-3'>
            아직 채팅이 없어요.
          </p>
        ) : (
          sessions.map(s => {
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
                  <p
                    className={`text-[13px] truncate ${
                      active
                        ? 'text-[#3182F6] font-semibold'
                        : 'text-[#191F28] dark:text-[#F2F4F6]'
                    }`}>
                    {s.title || '새 채팅'}
                  </p>
                  <p className='text-[10px] text-[#B0B8C1] dark:text-[#4B5563]'>
                    {s.message_count}개
                    {s.updated_at ? ` · ${fmt(s.updated_at)}` : ''}
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
