'use client';

// 조직 관리 — 전체 조직 목록(정렬·무한스크롤). ACTIVE는 메인 테이블, INACTIVE는 하단 패널(복원/영구삭제).

import { useCallback, useState } from 'react';
import { authedFetch } from '@/lib/api';
import { formatKSTDate } from '@/lib/datetime';
import { useInfiniteList } from '@/components/admin/useInfiniteList';
import {
  OrgUserControls,
  ORG_SORT_OPTIONS,
  sortToParams,
  type SortValue,
} from '@/components/admin/OrgUserControls';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Organization = {
  id: string;
  name: string;
  status: string;
  created_at: string;
};

const orgStatusStyle: Record<string, string> = {
  ACTIVE: 'text-emerald-500 bg-emerald-50 dark:bg-emerald-900/20',
  INACTIVE: 'text-red-500 bg-red-50 dark:bg-red-900/20',
};
const orgStatusLabel: Record<string, string> = { ACTIVE: '활성', INACTIVE: '비활성' };

export default function AdminCompaniesPage() {
  const [sort, setSort] = useState<SortValue>('created_at:desc');
  const [refresh, setRefresh] = useState(0);
  const { sort: sortCol, order } = sortToParams(sort);

  const fetcher = useCallback(
    (offset: number, limit: number) =>
      authedFetch(
        `${API_BASE}/api/admin/organizations?limit=${limit}&offset=${offset}&sort=${sortCol}&order=${order}`,
      )
        .then((r) => (r.ok ? r.json() : []))
        .then((d) => (Array.isArray(d) ? (d as Organization[]) : [])),
    [sortCol, order],
  );

  // resetKey에 refresh를 섞어 삭제/복원/영구삭제 후 첫 페이지부터 재로드.
  const resetKey = `${sort}#${refresh}`;
  const { items, loading, loadingMore, hasMore, sentinelRef } = useInfiniteList<Organization>(
    fetcher,
    resetKey,
  );

  // 무한스크롤로 받은 목록을 상태별로 분리 — 활성은 메인, 비활성은 하단 패널.
  const activeOrgs = items.filter((o) => o.status === 'ACTIVE');
  const inactiveOrgs = items.filter((o) => o.status === 'INACTIVE');

  const handleDelete = async (id: string, name: string) => {
    if (
      !confirm(
        `'${name}' 조직을 비활성화할까요?\n소속 계정 로그인이 차단됩니다. (데이터는 보존되며 복원할 수 있습니다.)`,
      )
    )
      return;
    const res = await authedFetch(`${API_BASE}/api/admin/companies/${id}`, { method: 'DELETE' });
    if (!res.ok) {
      alert('비활성화에 실패했습니다.');
      return;
    }
    setRefresh((n) => n + 1);
  };

  const handleRestore = async (id: string, name: string) => {
    const res = await authedFetch(`${API_BASE}/api/admin/companies/${id}/restore`, {
      method: 'POST',
    });
    if (!res.ok) {
      alert(`'${name}' 복원에 실패했습니다.`);
      return;
    }
    setRefresh((n) => n + 1);
  };

  const handlePurge = async (id: string, name: string) => {
    if (
      !confirm(
        `'${name}' 조직을 영구 삭제할까요?\n\n소속 프로젝트/시뮬/제너/채팅까지 전부 삭제됩니다. 이 작업은 되돌릴 수 없습니다.`,
      )
    )
      return;
    const res = await authedFetch(`${API_BASE}/api/admin/companies/${id}/purge`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      alert('영구 삭제에 실패했습니다.');
      return;
    }
    setRefresh((n) => n + 1);
  };

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-ink">조직 관리</h1>
        <p className="text-sm text-ink-tertiary mt-1">전체 조직을 조회·관리하세요</p>
      </div>

      <OrgUserControls sort={sort} onSort={setSort} sortOptions={ORG_SORT_OPTIONS} />

      {/* 활성 조직 */}
      <div className="bg-card border border-line rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-line">
          <p className="text-sm font-semibold text-ink">전체 조직</p>
        </div>
        {loading ? (
          <div className="py-16 text-center text-sm text-ink-tertiary">불러오는 중...</div>
        ) : activeOrgs.length === 0 ? (
          <div className="py-16 text-center text-sm text-ink-tertiary">활성 조직이 없습니다</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line bg-surface-1">
                <th className="text-left px-6 py-3 text-xs font-semibold text-ink-tertiary">회사명</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-ink-tertiary">상태</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-ink-tertiary">생성일</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {activeOrgs.map((o) => (
                <tr key={o.id} className="border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0 hover:bg-accent transition-colors">
                  <td className="px-6 py-4 font-medium text-ink">{o.name}</td>
                  <td className="px-4 py-4">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${orgStatusStyle[o.status] ?? ''}`}>
                      {orgStatusLabel[o.status] ?? o.status}
                    </span>
                  </td>
                  <td className="px-4 py-4 text-ink-tertiary">{formatKSTDate(o.created_at)}</td>
                  <td className="px-4 py-4 text-right">
                    <button onClick={() => handleDelete(o.id, o.name)}
                      className="px-3 py-1.5 text-xs text-ink-tertiary rounded-lg hover:bg-red-50 hover:text-red-500 transition-colors">삭제</button>
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

      {/* 비활성화된 조직 — 무한스크롤로 로드된 목록에서 INACTIVE만 모아 표시. */}
      {inactiveOrgs.length > 0 && (
        <div className="bg-card border border-red-100 dark:border-red-900/30 rounded-2xl overflow-hidden">
          <div className="px-6 py-4 border-b border-line">
            <p className="text-sm font-semibold text-red-500">비활성화된 조직</p>
            <p className="text-xs text-ink-tertiary mt-0.5">복원하거나 영구 삭제할 수 있습니다</p>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line bg-surface-1">
                <th className="text-left px-6 py-3 text-xs font-semibold text-ink-tertiary">회사명</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-ink-tertiary">상태</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-ink-tertiary">생성일</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {inactiveOrgs.map((o) => (
                <tr key={o.id} className="border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0 hover:bg-accent transition-colors">
                  <td className="px-6 py-4 font-medium text-ink">{o.name}</td>
                  <td className="px-4 py-4">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${orgStatusStyle[o.status] ?? ''}`}>
                      {orgStatusLabel[o.status] ?? o.status}
                    </span>
                  </td>
                  <td className="px-4 py-4 text-ink-tertiary">{formatKSTDate(o.created_at)}</td>
                  <td className="px-4 py-4">
                    <div className="flex items-center gap-2 justify-end">
                      <button onClick={() => handleRestore(o.id, o.name)}
                        className="px-3 py-1.5 text-xs text-primary border border-primary/30 rounded-lg hover:bg-primary-subtle transition-colors">복원</button>
                      <button onClick={() => handlePurge(o.id, o.name)}
                        className="px-3 py-1.5 text-xs text-white bg-red-500 rounded-lg hover:bg-red-600 transition-colors">영구삭제</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
