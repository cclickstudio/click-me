'use client';

// 프로젝트 관리 — 조직 전체 프로젝트를 팀별 칸반으로 보고, 카드를 드래그해 팀에 배정. (COMPANY 전용)

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import AppLayout from '@/components/AppLayout';
import { useAuth } from '@/components/AuthProvider';
import { getToken } from '@/lib/authApi';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Project = {
  id: string;
  name: string;
  description: string | null;
  status: string;
  created_by_name: string | null;
  team_id: string | null;
  team_name: string | null;
  created_at?: string;
};
type Team = { id: string; name: string; member_count: number; created_at: string };

const UNASSIGNED = '__unassigned__';

const authHeaders = () => ({ Authorization: `Bearer ${getToken()}`, 'Content-Type': 'application/json' });

const fmt = (iso?: string) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return `${d.getFullYear()}.${d.getMonth() + 1}.${d.getDate()}`;
};

export default function CompanyProjectsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [dragOver, setDragOver] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const [p, t] = await Promise.all([
      fetch(`${API_BASE}/api/projects`, { headers: authHeaders() }).then((r) => (r.ok ? r.json() : [])).catch(() => []),
      fetch(`${API_BASE}/api/company/teams`, { headers: authHeaders() }).then((r) => (r.ok ? r.json() : [])).catch(() => []),
    ]);
    if (Array.isArray(p)) setProjects(p);
    if (Array.isArray(t)) setTeams(t);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  // 낙관적 업데이트 후 실패 시 롤백 (팀 관리 칸반과 동일 패턴)
  const assign = async (projectId: string, teamId: string | null) => {
    const snapshot = projects;
    const teamName = teamId ? (teams.find((t) => t.id === teamId)?.name ?? null) : null;
    setProjects((prev) =>
      prev.map((p) => (p.id === projectId ? { ...p, team_id: teamId, team_name: teamName } : p))
    );
    const res = await fetch(`${API_BASE}/api/company/projects/${projectId}/team`, {
      method: 'PATCH', headers: authHeaders(), body: JSON.stringify({ team_id: teamId }),
    });
    if (!res.ok) { setProjects(snapshot); alert('팀 배정에 실패했습니다.'); }
  };

  if (user && user.role !== 'COMPANY') {
    return (
      <AppLayout>
        <div className="px-8 py-20 text-center text-sm text-[#8B95A1] dark:text-[#6B7280]">기업(COMPANY) 계정만 접근할 수 있습니다.</div>
      </AppLayout>
    );
  }

  const columns: { key: string; teamId: string | null; name: string }[] = [
    { key: UNASSIGNED, teamId: null, name: '팀 배정 안됨' },
    ...teams.map((t) => ({ key: t.id, teamId: t.id, name: t.name })),
  ];
  const projectsOf = (teamId: string | null) => projects.filter((p) => (p.team_id ?? null) === teamId);

  return (
    <AppLayout>
      <div className="px-8 py-8 max-w-6xl mx-auto space-y-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">프로젝트 관리</h1>
            <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">카드를 드래그해 프로젝트를 팀에 배정하세요. 같은 팀끼리만 프로젝트를 공유합니다.</p>
          </div>
          <button onClick={() => router.push('/company/teams')}
            className="shrink-0 px-4 py-2.5 text-sm font-medium text-[#3182F6] border border-[#3182F6]/30 rounded-xl hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors">팀 관리로 이동</button>
        </div>

        {loading ? (
          <div className="py-12 text-center text-sm text-[#8B95A1]">불러오는 중...</div>
        ) : projects.length === 0 ? (
          <div className="py-12 text-center text-sm text-[#8B95A1]">프로젝트가 없습니다</div>
        ) : (
          <div className="flex gap-4 overflow-x-auto pb-4">
            {columns.map((col) => {
              const cards = projectsOf(col.teamId);
              const isOver = dragOver === col.key;
              return (
                <div key={col.key}
                  onDragOver={(e) => { e.preventDefault(); setDragOver(col.key); }}
                  onDragLeave={() => setDragOver((v) => (v === col.key ? null : v))}
                  onDrop={(e) => { e.preventDefault(); const pid = e.dataTransfer.getData('text/plain'); setDragOver(null); if (pid) assign(pid, col.teamId); }}
                  className={`shrink-0 w-72 rounded-2xl border transition-colors ${
                    isOver ? 'border-[#3182F6] bg-[#EBF3FF] dark:bg-[#1E3A5F]' : 'border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#161B27]'
                  }`}>
                  <div className="flex items-center justify-between px-4 py-3 border-b border-[#E5E8EB] dark:border-[#2D3748]">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] truncate">{col.name}</span>
                      <span className="text-[10px] text-[#8B95A1] bg-[#E5E8EB] dark:bg-[#2D3748] rounded-full px-1.5 py-0.5">{cards.length}</span>
                    </div>
                  </div>
                  <div className="p-2 space-y-2 min-h-[160px]">
                    {cards.length === 0 ? (
                      <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563] text-center py-8">여기로 드래그</p>
                    ) : cards.map((p) => (
                      <div key={p.id} draggable
                        onDragStart={(e) => e.dataTransfer.setData('text/plain', p.id)}
                        onClick={() => router.push(`/projects/${p.id}`)}
                        className="px-3 py-2.5 rounded-xl bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] cursor-grab active:cursor-grabbing hover:border-[#3182F6] transition-colors">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="text-[#8B95A1] shrink-0">
                            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                          </svg>
                          <p className="text-sm font-medium text-[#191F28] dark:text-[#F2F4F6] truncate">{p.name}</p>
                        </div>
                        <p className="text-[11px] text-[#8B95A1] dark:text-[#6B7280] truncate mt-0.5">
                          {p.created_by_name ?? '—'} · {fmt(p.created_at)}
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
    </AppLayout>
  );
}
