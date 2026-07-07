'use client';

import { useCallback, useState } from 'react';
import { authedFetch } from '@/lib/api';
import { useProjects } from '@/components/ProjectContext';
import { useChatController } from '@/components/chat/ChatController';
import { formatKST } from '@/lib/datetime';
import { AdminOrgPicker } from '@/components/manage/AdminOrgPicker';
import { useInfiniteList, useDebouncedValue } from '@/components/admin/useInfiniteList';
import {
  HistoryControls,
  OrgStatusDot,
  OrgStatusFilter,
  executorLabel,
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
  created_by_name: string | null;
  created_by_role: string | null;
  project_name: string | null;
  org_name: string | null;
  org_status: string | null;
  created_at: string;
};

function formatDate(iso: string) {
  return formatKST(iso);
}

export default function AdminChatsPage() {
  const { revealProjectInPanel } = useProjects();
  const { openChat } = useChatController();
  const [query, setQuery] = useState<HistoryQuery>(DEFAULT_HISTORY_QUERY);
  const [orgKey, setOrgKey] = useState(0); // AdminOrgPicker 선택 변경 시 리스트만 재로드하는 키

  // 행 클릭 — 해당 채팅을 플로팅 챗에 띄우고(item4), 프로젝트를 왼쪽 패널에서 펼친다(item5).
  const openRow = (r: ChatRow) => {
    if (r.project_id) revealProjectInPanel(r.project_id);
    openChat(r.id);
  };
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
    `${qs}#${orgKey}`,
  );

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink">채팅 내역</h1>
          <p className="text-sm text-ink-tertiary mt-1">전체 사용자 채팅 세션 목록</p>
        </div>
        <div className="flex items-center gap-3">
          <OrgStatusFilter
            value={query.orgStatus}
            onChange={(v) => setQuery({ ...query, orgStatus: v })}
          />
          <AdminOrgPicker onSelect={() => setOrgKey((n) => n + 1)} />
        </div>
      </div>

      <div className="mb-4">
        {/* 채팅은 상태 개념이 없어 상태순 미노출 */}
        <HistoryControls value={query} onChange={setQuery} hasStatus={false} titleLabel="제목" />
      </div>

      <div className="bg-card border border-line rounded-2xl overflow-hidden">
        {loading ? (
          <div className="py-20 text-center text-sm text-ink-tertiary">불러오는 중...</div>
        ) : items.length === 0 ? (
          <div className="py-20 text-center text-sm text-ink-tertiary">채팅 내역이 없습니다</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line bg-surface-1">
                <th className="text-left px-6 py-3 text-xs font-semibold text-ink-tertiary">제목</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-ink-tertiary">조직</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-ink-tertiary">조직 상태</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-ink-tertiary">프로젝트</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-ink-tertiary">실행자</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-ink-tertiary">메시지 수</th>
                <th className="text-right px-6 py-3 text-xs font-semibold text-ink-tertiary">생성일</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => openRow(r)}
                  className="border-b border-line last:border-0 hover:bg-accent cursor-pointer transition-colors"
                >
                  <td className="text-left px-6 py-3 text-ink font-medium">
                    {r.title || '새 채팅'}
                  </td>
                  <td className="text-center px-4 py-3 text-ink-secondary">
                    {r.org_name ?? '—'}
                  </td>
                  <td className="text-center px-4 py-3">
                    <OrgStatusDot status={r.org_status} />
                  </td>
                  <td className="text-center px-4 py-3 text-ink-secondary">
                    {r.project_name ?? '—'}
                  </td>
                  <td className="text-center px-4 py-3 text-ink-secondary">
                    {executorLabel(r)}
                  </td>
                  <td className="text-center px-4 py-3 text-ink-secondary">{r.message_count}개</td>
                  <td className="text-right px-6 py-3 text-ink-tertiary">{formatDate(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div ref={sentinelRef} className="h-1" />
        {loadingMore && (
          <p className="text-center text-[12px] text-ink-tertiary py-3">더 불러오는 중…</p>
        )}
        {!hasMore && !loading && items.length > 0 && (
          <p className="text-center text-[12px] text-ink-muted py-3">모두 불러왔어요</p>
        )}
      </div>
    </div>
  );
}
