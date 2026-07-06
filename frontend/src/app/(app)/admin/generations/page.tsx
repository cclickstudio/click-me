'use client';

import { useCallback } from 'react';
import { authedFetch } from '@/lib/api';
import { useProjects } from '@/components/ProjectContext';
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
import { useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
type Row = {
  id: string;
  status: string;
  product_name: string | null;
  created_by_name: string | null;
  created_by_role: string | null;
  project_id: string | null;
  project_name: string | null;
  org_name: string | null;
  org_status: string | null;
  created_at: string;
};
const fmt = (iso: string) => formatKST(iso);
const statusStyle: Record<string, string> = {
  completed: 'text-emerald-500 bg-emerald-50 dark:bg-emerald-900/20',
  running: 'text-blue-500 bg-blue-50 dark:bg-blue-900/20',
  pending: 'text-yellow-500 bg-yellow-50 dark:bg-yellow-900/20',
  failed: 'text-red-500 bg-red-50 dark:bg-red-900/20',
};
const statusLabel: Record<string, string> = {
  completed: '완료',
  running: '진행 중',
  pending: '대기',
  failed: '실패',
};

export default function AdminGenerationsPage() {
  const { revealProjectInPanel } = useProjects();
  const [query, setQuery] = useState<HistoryQuery>(DEFAULT_HISTORY_QUERY);
  const [orgKey, setOrgKey] = useState(0); // AdminOrgPicker 선택 변경 시 리스트만 재로드하는 키
  const debouncedSearch = useDebouncedValue(query.search, 300);
  const qs = historyQueryString({ ...query, search: debouncedSearch });

  const fetcher = useCallback(
    (offset: number, limit: number) =>
      authedFetch(
        `${API_BASE}/api/admin/generations?limit=${limit}&offset=${offset}${qs ? `&${qs}` : ''}`,
      )
        .then((r) => r.json())
        .then((d) => (Array.isArray(d) ? (d as Row[]) : [])),
    [qs],
  );

  const { items, loading, loadingMore, hasMore, sentinelRef } = useInfiniteList<Row>(
    fetcher,
    `${qs}#${orgKey}`,
  );

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">제너레이터 내역</h1>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">전체 사용자 광고 생성 목록</p>
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
        <HistoryControls value={query} onChange={setQuery} titleLabel="상품명" />
      </div>

      <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
        {loading ? (
          <div className="py-20 text-center text-sm text-[#8B95A1]">불러오는 중...</div>
        ) : items.length === 0 ? (
          <div className="py-20 text-center text-sm text-[#8B95A1]">제너레이터 내역이 없습니다</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#F2F4F6] dark:border-[#252D3D] bg-[#F9FAFB] dark:bg-[#252D3D]">
                <th className="text-left px-6 py-3 text-xs font-semibold text-[#8B95A1]">상품명</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-[#8B95A1]">조직</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-[#8B95A1]">조직 상태</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-[#8B95A1]">프로젝트</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-[#8B95A1]">실행자</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-[#8B95A1]">상태</th>
                <th className="text-right px-6 py-3 text-xs font-semibold text-[#8B95A1]">생성일</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => r.project_id && revealProjectInPanel(r.project_id)}
                  className={`border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0 hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors ${r.project_id ? 'cursor-pointer' : ''}`}
                >
                  <td className="text-left px-6 py-3 text-[#191F28] dark:text-[#F2F4F6] font-medium">
                    {r.product_name ?? '—'}
                  </td>
                  <td className="text-center px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">
                    {r.org_name ?? '—'}
                  </td>
                  <td className="text-center px-4 py-3">
                    <OrgStatusDot status={r.org_status} />
                  </td>
                  <td className="text-center px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">
                    {r.project_name ?? '—'}
                  </td>
                  <td className="text-center px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">
                    {executorLabel(r)}
                  </td>
                  <td className="text-center px-4 py-3">
                    <span
                      className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${statusStyle[r.status] ?? ''}`}
                    >
                      {statusLabel[r.status] ?? r.status}
                    </span>
                  </td>
                  <td className="text-right px-6 py-3 text-[#8B95A1]">{fmt(r.created_at)}</td>
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
