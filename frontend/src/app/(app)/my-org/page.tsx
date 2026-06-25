'use client';

// 내 조직 — 우리 조직의 팀·팀원을 조회(Read 전용). USER용.

import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '@/components/AuthProvider';
import { getToken } from '@/lib/authApi';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Member = { member_id: string; user_name: string; team_id: string | null };
type Team = { id: string; name: string; member_count: number };
type Org = { id: string; name: string; plan: string; status: string };

export default function MyOrgPage() {
  const { user } = useAuth();
  const [org, setOrg] = useState<Org | null>(null);
  const [teams, setTeams] = useState<Team[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const headers = { Authorization: `Bearer ${getToken()}` };
    const [o, t, m] = await Promise.all([
      fetch(`${API_BASE}/api/company/org`, { headers }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      fetch(`${API_BASE}/api/company/teams`, { headers }).then((r) => (r.ok ? r.json() : [])).catch(() => []),
      fetch(`${API_BASE}/api/company/members`, { headers }).then((r) => (r.ok ? r.json() : [])).catch(() => []),
    ]);
    if (o) setOrg(o);
    if (Array.isArray(t)) setTeams(t);
    if (Array.isArray(m)) setMembers(m);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const columns: { key: string; teamId: string | null; name: string }[] = [
    { key: '__unassigned__', teamId: null, name: '팀 배정 안됨' },
    ...teams.map((t) => ({ key: t.id, teamId: t.id, name: t.name })),
  ];
  const membersOf = (teamId: string | null) => members.filter((m) => (m.team_id ?? null) === teamId);

  return (
      <div className="px-8 py-8 max-w-5xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">내 조직</h1>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">
            {org ? `${org.name} · 팀원 ${members.length}명` : '우리 조직의 팀과 팀원을 확인하세요'}
          </p>
        </div>

        {loading ? (
          <div className="py-20 text-center text-sm text-[#8B95A1]">불러오는 중...</div>
        ) : (
          <div className="flex gap-4 overflow-x-auto pb-4">
            {columns.map((col) => {
              const list = membersOf(col.teamId);
              const isMyTeam = col.teamId != null && col.teamId === user?.team_id;
              return (
                <div
                  key={col.key}
                  className={`shrink-0 w-64 rounded-2xl border ${
                    isMyTeam
                      ? 'border-[#3182F6] bg-[#EBF3FF] dark:bg-[#1E3A5F]'
                      : 'border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#161B27]'
                  }`}
                >
                  <div className="flex items-center justify-between px-4 py-3 border-b border-[#E5E8EB] dark:border-[#2D3748]">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] truncate">{col.name}</span>
                      <span className="text-[10px] text-[#8B95A1] bg-[#E5E8EB] dark:bg-[#2D3748] rounded-full px-1.5 py-0.5">{list.length}</span>
                    </div>
                    {isMyTeam && (
                      <span className="shrink-0 text-[10px] font-medium text-[#3182F6] bg-white dark:bg-[#1C2333] rounded-full px-2 py-0.5">우리 팀</span>
                    )}
                  </div>
                  <div className="p-2 space-y-2 min-h-[80px]">
                    {list.length === 0 ? (
                      <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563] text-center py-6">팀원 없음</p>
                    ) : list.map((m) => (
                      <div key={m.member_id}
                        className="px-3 py-2.5 rounded-xl bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748]">
                        <p className="text-sm font-medium text-[#191F28] dark:text-[#F2F4F6] truncate">
                          {m.user_name}{m.user_name === user?.name ? ' (나)' : ''}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
  );
}
