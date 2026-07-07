'use client';

// 팀 관리 — 팀 생성·삭제 + 칸반보드로 팀원 배정만. (COMPANY 전용)
// 직원(계정) 생성·수정·삭제는 '직원 관리'(/company/members)로 분리됨.

import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '@/components/AuthProvider';
import { authedFetch } from '@/lib/api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Member = {
  member_id: string;
  user_name: string;
  login_id: string;
  team_id: string | null;
};
type Team = { id: string; name: string; member_count: number; created_at: string };

const UNASSIGNED = '__unassigned__';

export default function TeamsPage() {
  const { user } = useAuth();
  const [members, setMembers] = useState<Member[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [dragOver, setDragOver] = useState<string | null>(null);
  const [addingTeam, setAddingTeam] = useState(false);
  const [newTeam, setNewTeam] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    const [m, t] = await Promise.all([
      authedFetch(`${API_BASE}/api/company/members`).then((r) => (r.ok ? r.json() : [])).catch(() => []),
      authedFetch(`${API_BASE}/api/company/teams`).then((r) => (r.ok ? r.json() : [])).catch(() => []),
    ]);
    if (Array.isArray(m)) setMembers(m);
    if (Array.isArray(t)) setTeams(t);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const assign = async (memberId: string, teamId: string | null) => {
    const snapshot = members;
    setMembers((prev) => prev.map((m) => (m.member_id === memberId ? { ...m, team_id: teamId } : m)));
    const res = await authedFetch(`${API_BASE}/api/company/members/${memberId}/team`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ team_id: teamId }),
    });
    if (!res.ok) { setMembers(snapshot); alert('팀 이동에 실패했습니다.'); }
  };

  const createTeam = async () => {
    if (!newTeam.trim()) return;
    const res = await authedFetch(`${API_BASE}/api/company/teams`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: newTeam.trim() }) });
    if (res.ok) { setNewTeam(''); setAddingTeam(false); load(); } else alert('팀 생성에 실패했습니다.');
  };

  const deleteTeam = async (id: string, name: string) => {
    if (!confirm(`'${name}' 팀을 삭제할까요?\n소속 팀원은 '미배정'으로 이동합니다.`)) return;
    const res = await authedFetch(`${API_BASE}/api/company/teams/${id}`, { method: 'DELETE' });
    if (res.ok) load(); else alert('삭제에 실패했습니다.');
  };

  if (user && user.role !== 'COMPANY') {
    return (
      <div className="px-8 py-20 text-center text-sm text-[#8B95A1] dark:text-[#6B7280]">기업(COMPANY) 계정만 접근할 수 있습니다.</div>
    );
  }

  const columns: { key: string; teamId: string | null; name: string }[] = [
    { key: UNASSIGNED, teamId: null, name: '팀 배정 안됨' },
    ...teams.map((t) => ({ key: t.id, teamId: t.id, name: t.name })),
  ];
  const membersOf = (teamId: string | null) => members.filter((m) => (m.team_id ?? null) === teamId);

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto space-y-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">팀 관리</h1>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">팀을 만들고, 카드를 드래그해 팀원을 배정하세요. 계정 생성·수정은 ‘직원 관리’에서 하세요.</p>
        </div>
      </div>

      {/* 팀 배정 칸반 */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">팀 배정</p>
          {addingTeam ? (
            <div className="flex items-center gap-2">
              <input autoFocus value={newTeam} onChange={(e) => setNewTeam(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') createTeam(); if (e.key === 'Escape') { setAddingTeam(false); setNewTeam(''); } }}
                placeholder="팀 이름"
                className="px-3 py-2 text-sm border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl bg-white dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] focus:outline-none focus:border-[#3182F6]" />
              <button onClick={createTeam} className="px-3 py-2 text-sm font-medium bg-[#3182F6] text-white rounded-xl hover:bg-[#1B6EEB] transition-colors">추가</button>
              <button onClick={() => { setAddingTeam(false); setNewTeam(''); }} className="px-3 py-2 text-sm text-[#8B95A1] rounded-xl hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] transition-colors">취소</button>
            </div>
          ) : (
            <button onClick={() => setAddingTeam(true)}
              className="px-3 py-2 text-sm font-medium text-[#3182F6] border border-[#3182F6]/30 rounded-xl hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors">+ 팀 추가</button>
          )}
        </div>

        {loading ? (
          <div className="py-12 text-center text-sm text-[#8B95A1]">불러오는 중...</div>
        ) : (
          <div className="flex gap-4 overflow-x-auto pb-4">
            {columns.map((col) => {
              const cards = membersOf(col.teamId);
              const isOver = dragOver === col.key;
              return (
                <div key={col.key}
                  onDragOver={(e) => { e.preventDefault(); setDragOver(col.key); }}
                  onDragLeave={() => setDragOver((v) => (v === col.key ? null : v))}
                  onDrop={(e) => { e.preventDefault(); const mid = e.dataTransfer.getData('text/plain'); setDragOver(null); if (mid) assign(mid, col.teamId); }}
                  className={`shrink-0 w-64 rounded-2xl border transition-colors ${
                    isOver ? 'border-[#3182F6] bg-[#EBF3FF] dark:bg-[#1E3A5F]' : 'border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#161B27]'
                  }`}>
                  <div className="flex items-center justify-between px-4 py-3 border-b border-[#E5E8EB] dark:border-[#2D3748]">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] truncate">{col.name}</span>
                      <span className="text-[10px] text-[#8B95A1] bg-[#E5E8EB] dark:bg-[#2D3748] rounded-full px-1.5 py-0.5">{cards.length}</span>
                    </div>
                    {col.teamId && (
                      <button onClick={() => deleteTeam(col.teamId!, col.name)} title="팀 삭제"
                        className="shrink-0 p-1 rounded-md text-[#B0B8C1] hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="3 6 5 6 21 6" />
                          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                        </svg>
                      </button>
                    )}
                  </div>
                  <div className="p-2 space-y-2 min-h-[120px]">
                    {cards.length === 0 ? (
                      <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563] text-center py-6">여기로 드래그</p>
                    ) : cards.map((m) => (
                      <div key={m.member_id} draggable
                        onDragStart={(e) => e.dataTransfer.setData('text/plain', m.member_id)}
                        className="px-3 py-2.5 rounded-xl bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] cursor-grab active:cursor-grabbing hover:border-[#3182F6] transition-colors">
                        <p className="text-sm font-medium text-[#191F28] dark:text-[#F2F4F6] truncate">{m.user_name}</p>
                        <p className="text-[11px] text-[#8B95A1] dark:text-[#6B7280] truncate">{m.login_id}</p>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
