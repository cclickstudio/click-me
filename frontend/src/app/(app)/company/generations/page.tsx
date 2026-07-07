'use client';

// 제너레이터 내역(COMPANY) — 소속 조직 생성물 조회 + 삭제(휴지통). 행 클릭 시 좌측 패널에서 프로젝트 열림.

import { useCallback, useState } from 'react';
import { authedFetch } from '@/lib/api';
import { useProjects } from '@/components/ProjectContext';
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
  status: string;
  product_name: string | null;
  project_id: string | null;
  project_name: string | null;
  created_by_name: string | null;
  created_by_role: string | null;
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

export default function CompanyGenerationsPage() {
  const { revealProjectInPanel } = useProjects();
  const [query, setQuery] = useState<HistoryQuery>(DEFAULT_HISTORY_QUERY);
  const [refresh, setRefresh] = useState(0);
  const debouncedSearch = useDebouncedValue(query.search, 300);
  const qs = historyQueryString({ ...query, search: debouncedSearch });

  const fetcher = useCallback(
    (offset: number, limit: number) =>
      authedFetch(
        `${API_BASE}/api/company/generations?limit=${limit}&offset=${offset}${qs ? `&${qs}` : ''}`,
      )
        .then((r) => r.json())
        .then((d) => (Array.isArray(d) ? (d as Row[]) : [])),
    [qs],
  );

  const { items, loading, loadingMore, hasMore, sentinelRef } = useInfiniteList<Row>(
    fetcher,
    `${qs}#${refresh}`,
  );

  const remove = async (r: Row) => {
    if (!confirm(`'${r.product_name ?? '이 생성물'}'을(를) 휴지통으로 보낼까요?`)) return;
    const res = await authedFetch(`${API_BASE}/api/projects/generations/${r.id}`, { method: 'DELETE' });
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
        <h1 className="text-2xl font-bold text-ink">제너레이터 내역</h1>
        <p className="text-sm text-ink-tertiary mt-1">소속 조직의 광고 생성 목록</p>
      </div>

      <div className="mb-4">
        <HistoryControls value={query} onChange={setQuery} titleLabel="상품명" />
      </div>

      <div className="bg-card border border-line rounded-2xl overflow-hidden">
        {loading ? (
          <div className="py-20 text-center text-sm text-ink-tertiary">불러오는 중...</div>
        ) : items.length === 0 ? (
          <div className="py-20 text-center text-sm text-ink-tertiary">제너레이터 내역이 없습니다</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line bg-surface-1">
                <th className="text-left px-6 py-3 text-xs font-semibold text-ink-tertiary">상품명</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-ink-tertiary">프로젝트</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-ink-tertiary">실행자</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-ink-tertiary">상태</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-ink-tertiary">생성일</th>
                <th className="text-right px-6 py-3 text-xs font-semibold text-ink-tertiary" />
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => r.project_id && revealProjectInPanel(r.project_id)}
                  className={`border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0 hover:bg-accent transition-colors ${r.project_id ? 'cursor-pointer' : ''}`}
                >
                  <td className="text-left px-6 py-3 text-ink font-medium">
                    {r.product_name ?? '—'}
                  </td>
                  <td className="text-center px-4 py-3 text-ink-secondary">
                    {r.project_name ?? '—'}
                  </td>
                  <td className="text-center px-4 py-3 text-ink-secondary">
                    {executorLabel(r)}
                  </td>
                  <td className="text-center px-4 py-3">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${statusStyle[r.status] ?? ''}`}>
                      {statusLabel[r.status] ?? r.status}
                    </span>
                  </td>
                  <td className="text-center px-4 py-3 text-ink-tertiary">{fmt(r.created_at)}</td>
                  <td className="text-right px-6 py-3">
                    <button
                      onClick={(e) => { e.stopPropagation(); remove(r); }}
                      className="px-2.5 py-1 text-xs text-ink-tertiary rounded-lg hover:bg-red-50 hover:text-red-500 transition-colors"
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
        {loadingMore && <p className="text-center text-[12px] text-ink-tertiary py-3">더 불러오는 중…</p>}
        {!hasMore && !loading && items.length > 0 && (
          <p className="text-center text-[12px] text-ink-muted py-3">모두 불러왔어요</p>
        )}
      </div>
    </div>
  );
}
