'use client';

// 채팅 내역(COMPANY) — 소속 조직 채팅 조회 + 삭제. 행 클릭 시 플로팅 챗에 세션 오픈 + 좌측 패널 프로젝트 열림.

import { useCallback, useState } from 'react';
import { authedFetch } from '@/lib/api';
import { useProjects } from '@/components/ProjectContext';
import { useChatController } from '@/components/chat/ChatController';
import { formatKST } from '@/lib/datetime';
import { useInfiniteList, useDebouncedValue } from '@/components/admin/useInfiniteList';
import {
  HistoryControls,
  executorLabel,
  historyQueryString,
  DEFAULT_HISTORY_QUERY,
  type HistoryQuery,
} from '@/components/admin/HistoryControls';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Row = {
  id: string;
  project_id: string | null;
  title: string | null;
  message_count: number;
  created_by_name: string | null;
  created_by_role: string | null;
  project_name: string | null;
  created_at: string;
};

const fmt = (iso: string) => formatKST(iso);

export default function CompanyChatsPage() {
  const { revealProjectInPanel } = useProjects();
  const { openChat } = useChatController();
  const [query, setQuery] = useState<HistoryQuery>(DEFAULT_HISTORY_QUERY);
  const [refresh, setRefresh] = useState(0);
  const debouncedSearch = useDebouncedValue(query.search, 300);
  const qs = historyQueryString({ ...query, search: debouncedSearch });

  const fetcher = useCallback(
    (offset: number, limit: number) =>
      authedFetch(
        `${API_BASE}/api/company/chats?limit=${limit}&offset=${offset}${qs ? `&${qs}` : ''}`,
      )
        .then((r) => r.json())
        .then((d) => (Array.isArray(d) ? (d as Row[]) : [])),
    [qs],
  );

  const { items, loading, loadingMore, hasMore, sentinelRef } = useInfiniteList<Row>(
    fetcher,
    `${qs}#${refresh}`,
  );

  // 행 클릭 — 플로팅 챗에 세션 오픈 + 프로젝트를 좌측 패널에서 펼침.
  const openRow = (r: Row) => {
    if (r.project_id) revealProjectInPanel(r.project_id);
    openChat(r.id);
  };

  const remove = async (r: Row) => {
    if (!confirm(`'${r.title || '이 채팅'}'을(를) 삭제할까요?\n메시지도 함께 삭제되며 되돌릴 수 없습니다.`)) return;
    const res = await authedFetch(`${API_BASE}/api/company/chats/${r.id}`, { method: 'DELETE' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '삭제 실패' }));
      alert(err.detail ?? '삭제에 실패했습니다.');
      return;
    }
    setRefresh((n) => n + 1);
  };

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">채팅 내역</h1>
        <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">소속 조직의 채팅 세션 목록</p>
      </div>

      <div className="mb-4">
        <HistoryControls value={query} onChange={setQuery} hasStatus={false} titleLabel="제목" />
      </div>

      <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
        {loading ? (
          <div className="py-20 text-center text-sm text-[#8B95A1]">불러오는 중...</div>
        ) : items.length === 0 ? (
          <div className="py-20 text-center text-sm text-[#8B95A1]">채팅 내역이 없습니다</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#F2F4F6] dark:border-[#252D3D] bg-[#F9FAFB] dark:bg-[#252D3D]">
                <th className="text-left px-6 py-3 text-xs font-semibold text-[#8B95A1]">제목</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-[#8B95A1]">프로젝트</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-[#8B95A1]">실행자</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-[#8B95A1]">메시지 수</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-[#8B95A1]">생성일</th>
                <th className="text-right px-6 py-3 text-xs font-semibold text-[#8B95A1]" />
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => openRow(r)}
                  className="border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0 hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] cursor-pointer transition-colors"
                >
                  <td className="text-left px-6 py-3 text-[#191F28] dark:text-[#F2F4F6] font-medium">
                    {r.title || '새 채팅'}
                  </td>
                  <td className="text-center px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">
                    {r.project_name ?? '—'}
                  </td>
                  <td className="text-center px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">
                    {executorLabel(r)}
                  </td>
                  <td className="text-center px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">{r.message_count}개</td>
                  <td className="text-center px-4 py-3 text-[#8B95A1]">{fmt(r.created_at)}</td>
                  <td className="text-right px-6 py-3">
                    <button
                      onClick={(e) => { e.stopPropagation(); remove(r); }}
                      className="px-2.5 py-1 text-xs text-[#8B95A1] rounded-lg hover:bg-red-50 hover:text-red-500 transition-colors"
                    >
                      삭제
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div ref={sentinelRef} className="h-1" />
        {loadingMore && <p className="text-center text-[12px] text-[#8B95A1] py-3">더 불러오는 중…</p>}
        {!hasMore && !loading && items.length > 0 && (
          <p className="text-center text-[12px] text-[#B0B8C1] py-3">모두 불러왔어요</p>
        )}
      </div>
    </div>
  );
}
