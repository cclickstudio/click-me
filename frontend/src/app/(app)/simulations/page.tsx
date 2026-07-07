'use client';
// 통합 시뮬레이션 내역 — Role별로 데이터 소스만 분기(ADMIN=전체, USER/COMPANY=소속 조직).
// 행 클릭 시 결과 대시보드(/simulation/[id])로 이동. 삭제·복원은 상세 페이지에서 처리.

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/AuthProvider';
import { authedFetch } from '@/lib/api';
import { formatKSTFull } from '@/lib/datetime';
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

type Row = {
  id: string;
  ad_id?: string;
  ad_title: string | null;
  status: string;
  sample_size: number;
  created_by_name: string | null;
  created_by_role: string | null;
  project_id: string | null;
  project_name: string | null;
  org_name: string | null;
  org_status: string | null;
  created_at: string;
};

const fmt = (iso: string) => formatKSTFull(iso);

const STATUS_LABEL: Record<string, { label: string; color: string }> = {
  QUEUED: { label: '대기', color: 'bg-[#F2F4F6] text-ink-tertiary' },
  RUNNING: { label: '실행중', color: 'bg-[#EEF2FF] text-[#4F46E5]' },
  COMPLETED: { label: '완료', color: 'bg-[#ECFDF5] text-[#059669]' },
  FAILED: { label: '실패', color: 'bg-[#FEF2F2] text-[#DC2626]' },
};

export default function SimulationsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const isAdmin = user?.role === 'ADMIN';
  const isCompany = user?.role === 'COMPANY';

  const [query, setQuery] = useState<HistoryQuery>(DEFAULT_HISTORY_QUERY);
  const [orgKey, setOrgKey] = useState(0); // AdminOrgPicker 선택·삭제 시 리스트만 재로드하는 키
  const debouncedSearch = useDebouncedValue(query.search, 300);
  const qs = historyQueryString({ ...query, search: debouncedSearch });

  // ADMIN은 전체 시뮬, 그 외(USER/COMPANY)는 소속 조직 시뮬 — 데이터 소스만 다르다.
  const path = isAdmin ? '/api/admin/simulations' : '/api/company/simulations';

  const fetcher = useCallback(
    (offset: number, limit: number) => {
      if (!user) return Promise.resolve<Row[]>([]);
      return authedFetch(`${API_BASE}${path}?limit=${limit}&offset=${offset}${qs ? `&${qs}` : ''}`)
        .then((r) => r.json())
        .then((d) => (Array.isArray(d) ? (d as Row[]) : []))
        .catch(() => [] as Row[]);
    },
    [user, path, qs],
  );

  const { items, loading, loadingMore, hasMore, sentinelRef } = useInfiniteList<Row>(
    fetcher,
    `${path}|${qs}|${user ? '1' : '0'}#${orgKey}`,
  );

  // COMPANY 내역 삭제(휴지통) — 소속 조직 시뮬만. 삭제 후 리스트만 재로드.
  const remove = async (r: Row) => {
    if (!confirm(`'${r.ad_title ?? '이 시뮬레이션'}'을(를) 휴지통으로 보낼까요?`)) return;
    const res = await authedFetch(`${API_BASE}/api/projects/simulations/${r.id}`, { method: 'DELETE' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '삭제 실패' }));
      alert(err.detail ?? '삭제에 실패했습니다.');
      return;
    }
    setOrgKey((n) => n + 1);
  };

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink">시뮬레이션 내역</h1>
          <p className="text-sm text-ink-tertiary mt-1">
            {isAdmin ? '전체 사용자 시뮬레이션 실행 목록' : '소속 조직의 시뮬레이션 실행 목록'}
          </p>
        </div>
        {isAdmin && (
          <div className="flex items-center gap-3">
            <OrgStatusFilter
              value={query.orgStatus}
              onChange={(v) => setQuery({ ...query, orgStatus: v })}
            />
            <AdminOrgPicker onSelect={() => setOrgKey((n) => n + 1)} />
          </div>
        )}
      </div>

      <div className="mb-4">
        <HistoryControls value={query} onChange={setQuery} titleLabel="광고명" />
      </div>

      <div className="bg-card border border-line rounded-2xl overflow-hidden">
        {loading ? (
          <div className="py-20 text-center text-sm text-ink-tertiary">불러오는 중...</div>
        ) : items.length === 0 ? (
          <div className="py-20 text-center text-sm text-ink-tertiary">시뮬레이션 내역이 없습니다</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line bg-surface-1">
                <th className="text-left px-6 py-3 text-xs font-semibold text-ink-tertiary">광고명</th>
                {isAdmin && (
                  <>
                    <th className="text-center px-4 py-3 text-xs font-semibold text-ink-tertiary">조직</th>
                    <th className="text-center px-4 py-3 text-xs font-semibold text-ink-tertiary">
                      조직 상태
                    </th>
                  </>
                )}
                <th className="text-center px-4 py-3 text-xs font-semibold text-ink-tertiary">프로젝트</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-ink-tertiary">실행자</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-ink-tertiary">상태</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-ink-tertiary">샘플 수</th>
                <th className={`${isCompany ? 'text-center' : 'text-right'} px-4 py-3 text-xs font-semibold text-ink-tertiary`}>실행일</th>
                {isCompany && <th className="text-right px-6 py-3 text-xs font-semibold text-ink-tertiary" />}
              </tr>
            </thead>
            <tbody>
              {items.map((r) => {
                const s = STATUS_LABEL[r.status] ?? {
                  label: r.status,
                  color: 'bg-[#F2F4F6] text-ink-tertiary',
                };
                return (
                  <tr
                    key={r.id}
                    onClick={() => router.push(`/simulation/${r.id}`)}
                    className="border-b border-line last:border-0 hover:bg-accent transition-colors cursor-pointer"
                  >
                    <td className="text-left px-6 py-3 text-ink font-medium">
                      {r.ad_title ?? '—'}
                    </td>
                    {isAdmin && (
                      <>
                        <td className="text-center px-4 py-3 text-ink-secondary">
                          {r.org_name ?? '—'}
                        </td>
                        <td className="text-center px-4 py-3">
                          <OrgStatusDot status={r.org_status} />
                        </td>
                      </>
                    )}
                    <td className="text-center px-4 py-3 text-ink-secondary">
                      {r.project_name ?? '—'}
                    </td>
                    <td className="text-center px-4 py-3 text-ink-secondary">
                      {executorLabel(r)}
                    </td>
                    <td className="text-center px-4 py-3">
                      <span
                        className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${s.color}`}
                      >
                        {s.label}
                      </span>
                    </td>
                    <td className="text-center px-4 py-3 text-ink-secondary">
                      {r.sample_size}명
                    </td>
                    <td className={`${isCompany ? 'text-center' : 'text-right'} px-4 py-3 text-ink-tertiary`}>{fmt(r.created_at)}</td>
                    {isCompany && (
                      <td className="text-right px-6 py-3">
                        <button
                          onClick={(e) => { e.stopPropagation(); remove(r); }}
                          className="px-2.5 py-1 text-xs text-ink-tertiary rounded-lg hover:bg-red-50 hover:text-red-500 transition-colors"
                        >
                          삭제
                        </button>
                      </td>
                    )}
                  </tr>
                );
              })}
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
