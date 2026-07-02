'use client';

import { useCallback, useState } from 'react';
import { authedFetch } from '@/lib/api';
import { formatKST } from '@/lib/datetime';
import { AdminOrgPicker } from '@/components/manage/AdminOrgPicker';
import { useInfiniteList, useDebouncedValue } from '@/components/admin/useInfiniteList';
import {
  HistoryControls,
  historyQueryString,
  DEFAULT_HISTORY_QUERY,
  type HistoryQuery,
} from '@/components/admin/HistoryControls';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type ChatRow = {
  id: string;
  project_id: string | null;
  title: string | null;
  message_count: number;
  org_name: string | null;
  created_at: string;
};

function formatDate(iso: string) {
  return formatKST(iso);
}

export default function AdminChatsPage() {
  const [query, setQuery] = useState<HistoryQuery>(DEFAULT_HISTORY_QUERY);
  const debouncedSearch = useDebouncedValue(query.search, 300);
  const qs = historyQueryString({ ...query, search: debouncedSearch });

  const fetcher = useCallback(
    (offset: number, limit: number) =>
      authedFetch(
        `${API_BASE}/api/admin/chats?limit=${limit}&offset=${offset}${qs ? `&${qs}` : ''}`,
      )
        .then((r) => r.json())
        .then((d) => (Array.isArray(d) ? (d as ChatRow[]) : [])),
    [qs],
  );

  const { items, loading, loadingMore, hasMore, sentinelRef } = useInfiniteList<ChatRow>(
    fetcher,
    qs,
  );

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">채팅 내역</h1>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">전체 사용자 채팅 세션 목록</p>
        </div>
        <AdminOrgPicker />
      </div>

      <div className="mb-4">
        {/* 채팅은 상태 개념이 없어 상태순 미노출 */}
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
                <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">조직</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">메시지 수</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">생성일</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr
                  key={r.id}
                  className="border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0 hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors"
                >
                  <td className="px-6 py-3 text-[#191F28] dark:text-[#F2F4F6] font-medium">
                    {r.title || '새 채팅'}
                  </td>
                  <td className="px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">
                    {r.org_name ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">{r.message_count}개</td>
                  <td className="px-4 py-3 text-[#8B95A1]">{formatDate(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div ref={sentinelRef} className="h-1" />
        {loadingMore && (
          <p className="text-center text-[12px] text-[#8B95A1] py-3">더 불러오는 중…</p>
        )}
        {!hasMore && !loading && items.length > 0 && (
          <p className="text-center text-[12px] text-[#B0B8C1] py-3">모두 불러왔어요</p>
        )}
      </div>
    </div>
  );
}
