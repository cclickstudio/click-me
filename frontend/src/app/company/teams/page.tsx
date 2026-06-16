'use client';

// 팀 관리 — 팀원 리스트(추가·수정·삭제·상세) + 칸반보드 팀 배정. (COMPANY 전용)

import { useEffect, useState, useCallback } from 'react';
import AppLayout from '@/components/AppLayout';
import { useAuth } from '@/components/AuthProvider';
import { getToken } from '@/lib/authApi';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Member = {
  member_id: string;
  user_id: string;
  user_name: string;
  login_id: string;
  status: string;
  team_id: string | null;
  phone_num: string | null;
  user_email: string | null;
  joined_at: string | null;
  created_at: string;
};
type Team = { id: string; name: string; member_count: number; created_at: string };

const UNASSIGNED = '__unassigned__';

const inputCls =
  'w-full px-3 py-2.5 text-sm border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl bg-white dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] focus:outline-none focus:border-[#3182F6] transition-colors';

const fmt = (iso: string | null) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return `${d.getFullYear()}.${d.getMonth() + 1}.${d.getDate()}`;
};
const formatPhone = (v: string) => {
  const d = v.replace(/\D/g, '').slice(0, 11);
  if (d.length < 4) return d;
  if (d.length < 8) return `${d.slice(0, 3)}-${d.slice(3)}`;
  return `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}`;
};

const authHeaders = () => ({ Authorization: `Bearer ${getToken()}`, 'Content-Type': 'application/json' });

// ── 팀원 추가 모달 ──────────────────────────────────────────
function CreateMemberModal({ teams, onClose, onCreated }: { teams: Team[]; onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState('');
  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [teamId, setTeamId] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    setError('');
    if (!name.trim() || !loginId.trim() || password.length < 8) {
      setError('이름·아이디·비밀번호(8자 이상)를 확인해주세요.');
      return;
    }
    setSaving(true);
    const res = await fetch(`${API_BASE}/api/company/members`, {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ name: name.trim(), login_id: loginId.trim(), password, team_id: teamId || null }),
    });
    setSaving(false);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '생성 실패' }));
      setError(err.detail ?? '팀원 생성에 실패했습니다.');
      return;
    }
    onCreated();
  };

  return (
    <ModalShell title="팀원 추가" onClose={onClose} onSubmit={submit} saving={saving} submitLabel="팀원 추가">
      <Field label="이름"><input value={name} onChange={(e) => setName(e.target.value)} placeholder="홍길동" className={inputCls} /></Field>
      <Field label="아이디"><input value={loginId} onChange={(e) => setLoginId(e.target.value)} placeholder="로그인 아이디" className={inputCls} /></Field>
      <Field label="비밀번호"><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="8자 이상" className={inputCls} /></Field>
      <Field label="팀 (선택)">
        <select value={teamId} onChange={(e) => setTeamId(e.target.value)} className={inputCls}>
          <option value="">미배정</option>
          {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </Field>
      {error && <p className="text-xs text-red-500 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>}
    </ModalShell>
  );
}

// ── 팀원 수정 모달 (이름·비밀번호) ──────────────────────────
function EditMemberModal({ member, onClose, onSaved }: { member: Member; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(member.user_name);
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    setError('');
    if (!name.trim()) { setError('이름을 입력해주세요.'); return; }
    if (password && password.length < 8) { setError('비밀번호는 8자 이상이어야 합니다.'); return; }
    setSaving(true);
    const body: { name: string; password?: string } = { name: name.trim() };
    if (password) body.password = password;
    const res = await fetch(`${API_BASE}/api/company/members/${member.member_id}`, {
      method: 'PATCH', headers: authHeaders(), body: JSON.stringify(body),
    });
    setSaving(false);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '수정 실패' }));
      setError(err.detail ?? '수정에 실패했습니다.');
      return;
    }
    onSaved();
  };

  return (
    <ModalShell title="팀원 수정" subtitle={member.login_id} onClose={onClose} onSubmit={submit} saving={saving} submitLabel="저장">
      <Field label="이름"><input value={name} onChange={(e) => setName(e.target.value)} className={inputCls} /></Field>
      <Field label="새 비밀번호"><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="변경 시에만 입력 (8자 이상)" className={inputCls} /></Field>
      {error && <p className="text-xs text-red-500 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>}
    </ModalShell>
  );
}

// ── 팀원 상세 모달 ──────────────────────────────────────────
function MemberDetailModal({ member, teamName, onClose, onEdit, onDelete }: {
  member: Member; teamName: string; onClose: () => void; onEdit: () => void; onDelete: () => void;
}) {
  const Row = ({ label, value }: { label: string; value: React.ReactNode }) => (
    <div className="flex items-center gap-4 py-2.5 border-b border-[#F2F4F6] dark:border-[#252D3D] last:border-0">
      <span className="w-20 shrink-0 text-xs text-[#8B95A1] dark:text-[#6B7280]">{label}</span>
      <span className="text-sm text-[#191F28] dark:text-[#F2F4F6] flex-1">{value}</span>
    </div>
  );
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white dark:bg-[#1C2333] rounded-2xl shadow-xl w-full max-w-md mx-4 p-6">
        <h2 className="text-lg font-bold text-[#191F28] dark:text-[#F2F4F6] mb-4">{member.user_name}</h2>
        <div className="mb-5">
          <Row label="아이디" value={member.login_id} />
          <Row label="팀" value={teamName} />
          <Row label="전화번호" value={member.phone_num || '—'} />
          <Row label="이메일" value={member.user_email || '—'} />
          <Row label="합류일" value={fmt(member.joined_at)} />
        </div>
        <div className="flex gap-2">
          <button onClick={onDelete}
            className="px-4 py-2.5 text-sm font-medium text-red-500 border border-red-200 dark:border-red-900/40 rounded-xl hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors">삭제</button>
          <div className="flex-1" />
          <button onClick={onClose}
            className="px-4 py-2.5 text-sm font-medium border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl text-[#4E5968] dark:text-[#9CA3AF] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] transition-colors">닫기</button>
          <button onClick={onEdit}
            className="px-4 py-2.5 text-sm font-medium bg-[#3182F6] text-white rounded-xl hover:bg-[#1B6EEB] transition-colors">수정</button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] block mb-1">{label}</label>
      {children}
    </div>
  );
}

function ModalShell({ title, subtitle, children, onClose, onSubmit, saving, submitLabel }: {
  title: string; subtitle?: string; children: React.ReactNode; onClose: () => void; onSubmit: () => void; saving: boolean; submitLabel: string;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white dark:bg-[#1C2333] rounded-2xl shadow-xl w-full max-w-md mx-4 p-6">
        <h2 className="text-lg font-bold text-[#191F28] dark:text-[#F2F4F6] mb-1">{title}</h2>
        {subtitle && <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mb-4">{subtitle}</p>}
        <div className={`space-y-3 ${subtitle ? '' : 'mt-3'}`}>{children}</div>
        <div className="flex gap-2 mt-5">
          <button onClick={onClose}
            className="flex-1 py-2.5 text-sm font-medium border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl text-[#4E5968] dark:text-[#9CA3AF] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] transition-colors">취소</button>
          <button onClick={onSubmit} disabled={saving}
            className="flex-1 py-2.5 text-sm font-medium bg-[#3182F6] text-white rounded-xl hover:bg-[#1B6EEB] transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
            {saving ? '처리 중...' : submitLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function TeamsPage() {
  const { user } = useAuth();
  const [members, setMembers] = useState<Member[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [dragOver, setDragOver] = useState<string | null>(null);
  const [addingTeam, setAddingTeam] = useState(false);
  const [newTeam, setNewTeam] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState<Member | null>(null);
  const [editing, setEditing] = useState<Member | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const [m, t] = await Promise.all([
      fetch(`${API_BASE}/api/company/members`, { headers: authHeaders() }).then((r) => (r.ok ? r.json() : [])).catch(() => []),
      fetch(`${API_BASE}/api/company/teams`, { headers: authHeaders() }).then((r) => (r.ok ? r.json() : [])).catch(() => []),
    ]);
    if (Array.isArray(m)) setMembers(m);
    if (Array.isArray(t)) setTeams(t);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const teamName = (id: string | null) => (id ? (teams.find((t) => t.id === id)?.name ?? '—') : '미배정');

  const assign = async (memberId: string, teamId: string | null) => {
    const snapshot = members;
    setMembers((prev) => prev.map((m) => (m.member_id === memberId ? { ...m, team_id: teamId } : m)));
    const res = await fetch(`${API_BASE}/api/company/members/${memberId}/team`, {
      method: 'PATCH', headers: authHeaders(), body: JSON.stringify({ team_id: teamId }),
    });
    if (!res.ok) { setMembers(snapshot); alert('팀 이동에 실패했습니다.'); }
  };

  const createTeam = async () => {
    if (!newTeam.trim()) return;
    const res = await fetch(`${API_BASE}/api/company/teams`, { method: 'POST', headers: authHeaders(), body: JSON.stringify({ name: newTeam.trim() }) });
    if (res.ok) { setNewTeam(''); setAddingTeam(false); load(); } else alert('팀 생성에 실패했습니다.');
  };

  const deleteTeam = async (id: string, name: string) => {
    if (!confirm(`'${name}' 팀을 삭제할까요?\n소속 팀원은 '미배정'으로 이동합니다.`)) return;
    const res = await fetch(`${API_BASE}/api/company/teams/${id}`, { method: 'DELETE', headers: authHeaders() });
    if (res.ok) load(); else alert('삭제에 실패했습니다.');
  };

  const deleteMember = async (m: Member) => {
    if (!confirm(`'${m.user_name}' 팀원을 삭제할까요?\n계정과 멤버십이 제거됩니다.`)) return;
    const res = await fetch(`${API_BASE}/api/company/members/${m.member_id}`, { method: 'DELETE', headers: authHeaders() });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '삭제 실패' }));
      alert(err.detail ?? '삭제에 실패했습니다.');
      return;
    }
    setDetail(null);
    load();
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
  const membersOf = (teamId: string | null) => members.filter((m) => (m.team_id ?? null) === teamId);

  return (
    <AppLayout>
      <div className="px-8 py-8 max-w-5xl mx-auto space-y-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">팀 관리</h1>
            <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">팀원을 추가·관리하고, 카드를 드래그해 팀에 배정하세요</p>
          </div>
          <button onClick={() => setShowCreate(true)}
            className="shrink-0 px-4 py-2.5 text-sm font-medium bg-[#3182F6] text-white rounded-xl hover:bg-[#1B6EEB] transition-colors">+ 팀원 추가</button>
        </div>

        {/* 팀원 목록 */}
        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
          <div className="px-6 py-4 border-b border-[#E5E8EB] dark:border-[#2D3748]">
            <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">팀원 ({members.length})</p>
          </div>
          {loading ? (
            <div className="py-12 text-center text-sm text-[#8B95A1]">불러오는 중...</div>
          ) : members.length === 0 ? (
            <div className="py-12 text-center text-sm text-[#8B95A1]">팀원이 없습니다</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#F2F4F6] dark:border-[#252D3D] bg-[#F9FAFB] dark:bg-[#252D3D]">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-[#8B95A1]">이름</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">아이디</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">팀</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">합류일</th>
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.member_id} onClick={() => setDetail(m)}
                    className="border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0 hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors cursor-pointer">
                    <td className="px-6 py-3 font-medium text-[#191F28] dark:text-[#F2F4F6]">{m.user_name}</td>
                    <td className="px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">{m.login_id}</td>
                    <td className="px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">
                      {m.team_id ? teamName(m.team_id) : <span className="text-[#B0B8C1]">미배정</span>}
                    </td>
                    <td className="px-4 py-3 text-[#8B95A1]">{fmt(m.joined_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
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
                          onClick={() => setDetail(m)}
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

      {showCreate && <CreateMemberModal teams={teams} onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); load(); }} />}
      {editing && <EditMemberModal member={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); setDetail(null); load(); }} />}
      {detail && !editing && (
        <MemberDetailModal
          member={detail}
          teamName={teamName(detail.team_id)}
          onClose={() => setDetail(null)}
          onEdit={() => setEditing(detail)}
          onDelete={() => deleteMember(detail)}
        />
      )}
    </AppLayout>
  );
}
