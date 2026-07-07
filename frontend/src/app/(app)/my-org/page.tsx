'use client';

// 내 조직 — 우리 조직의 전체 인원(테이블·10명씩 페이지네이션) + 팀 뷰(칸반). USER용, Read 전용.

import { useEffect, useMemo, useState, useCallback } from 'react';
import { useAuth } from '@/components/AuthProvider';
import { authedFetch } from '@/lib/api';
import { formatKSTDate } from '@/lib/datetime';
import { Pagination } from '@/components/ui/Pagination';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Member = {
  member_id: string;
  user_name: string;
  login_id: string;
  team_id: string | null;
  joined_at: string | null;
};
type Team = { id: string; name: string; member_count: number };
type Org = { id: string; name: string; plan: string; status: string };

const PAGE_SIZE = 10;
const fmt = (iso: string | null) => (iso ? formatKSTDate(iso) : '—');

export default function MyOrgPage() {
  const { user } = useAuth();
  const [org, setOrg] = useState<Org | null>(null);
  const [teams, setTeams] = useState<Team[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    setLoading(true);
    const [o, t, m] = await Promise.all([
      authedFetch(`${API_BASE}/api/company/org`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      authedFetch(`${API_BASE}/api/company/teams`).then((r) => (r.ok ? r.json() : [])).catch(() => []),
      authedFetch(`${API_BASE}/api/company/members`).then((r) => (r.ok ? r.json() : [])).catch(() => []),
    ]);
    if (o) setOrg(o);
    if (Array.isArray(t)) setTeams(t);
    if (Array.isArray(m)) setMembers(m);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const teamName = (id: string | null) => (id ? (teams.find((t) => t.id === id)?.name ?? '—') : null);

  // 전체 인원 테이블 — 10명씩 페이지네이션(클라이언트).
  const totalPages = Math.max(1, Math.ceil(members.length / PAGE_SIZE));
  const pageMembers = useMemo(
    () => members.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [members, page],
  );
  // 목록이 줄어 현재 페이지가 범위를 벗어나면 마지막 페이지로 보정.
  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const columns: { key: string; teamId: string | null; name: string }[] = [
    { key: '__unassigned__', teamId: null, name: '팀 배정 안됨' },
    ...teams.map((t) => ({ key: t.id, teamId: t.id, name: t.name })),
  ];
  const membersOf = (teamId: string | null) => members.filter((m) => (m.team_id ?? null) === teamId);

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-ink">내 조직</h1>
        <p className="text-sm text-ink-tertiary mt-1">
          {org ? `${org.name} · 전체 인원 ${members.length}명 · 팀 ${teams.length}개` : '우리 조직의 인원과 팀을 확인하세요'}
        </p>
      </div>

      {loading ? (
        <div className="py-20 text-center text-sm text-ink-tertiary">불러오는 중...</div>
      ) : (
        <>
          {/* 전체 인원 — 테이블(10명씩 페이지네이션) */}
          <div>
            <div className="bg-card border border-line rounded-2xl overflow-hidden">
              <div className="px-6 py-4 border-b border-line">
                <p className="text-sm font-semibold text-ink">전체 인원</p>
              </div>
              {members.length === 0 ? (
                <div className="py-12 text-center text-sm text-ink-tertiary">인원이 없습니다</div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line bg-surface-1">
                      <th className="text-left px-6 py-3 text-xs font-semibold text-ink-tertiary">이름</th>
                      <th className="text-center px-4 py-3 text-xs font-semibold text-ink-tertiary">아이디</th>
                      <th className="text-center px-4 py-3 text-xs font-semibold text-ink-tertiary">팀</th>
                      <th className="text-right px-6 py-3 text-xs font-semibold text-ink-tertiary">합류일</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pageMembers.map((m) => (
                      <tr key={m.member_id} className="border-b border-line last:border-0">
                        <td className="text-left px-6 py-3 font-medium text-ink">
                          {m.user_name}{m.user_name === user?.name ? ' (나)' : ''}
                        </td>
                        <td className="text-center px-4 py-3 text-ink-secondary">{m.login_id}</td>
                        <td className="text-center px-4 py-3 text-ink-secondary">
                          {teamName(m.team_id) ?? <span className="text-ink-muted">미배정</span>}
                        </td>
                        <td className="text-right px-6 py-3 text-ink-tertiary">{fmt(m.joined_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            <Pagination page={page} totalPages={totalPages} onChange={setPage} />
          </div>

          {/* 팀 — 팀별 팀원 칸반(조회 전용) */}
          <div>
            <p className="text-sm font-semibold text-ink mb-3">팀</p>
            <div className="flex gap-4 overflow-x-auto pb-4">
              {columns.map((col) => {
                const list = membersOf(col.teamId);
                const isMyTeam = col.teamId != null && col.teamId === user?.team_id;
                return (
                  <div
                    key={col.key}
                    className={`shrink-0 w-64 rounded-2xl border ${
                      isMyTeam
                        ? 'border-primary bg-primary-subtle'
                        : 'border-line bg-surface-1'
                    }`}
                  >
                    <div className="flex items-center justify-between px-4 py-3 border-b border-line">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-sm font-semibold text-ink truncate">{col.name}</span>
                        <span className="text-[10px] text-ink-tertiary bg-surface-1 rounded-full px-1.5 py-0.5">{list.length}</span>
                      </div>
                      {isMyTeam && (
                        <span className="shrink-0 text-[10px] font-medium text-primary bg-card rounded-full px-2 py-0.5">우리 팀</span>
                      )}
                    </div>
                    <div className="p-2 space-y-2 min-h-[80px]">
                      {list.length === 0 ? (
                        <p className="text-xs text-ink-muted text-center py-6">팀원 없음</p>
                      ) : list.map((m) => (
                        <div key={m.member_id}
                          className="px-3 py-2.5 rounded-xl bg-card border border-line">
                          <p className="text-sm font-medium text-ink truncate">
                            {m.user_name}{m.user_name === user?.name ? ' (나)' : ''}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
