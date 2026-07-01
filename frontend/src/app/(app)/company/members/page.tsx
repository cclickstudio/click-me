'use client';

import { useEffect, useState } from 'react';
import { getToken } from '@/lib/authApi';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Member = { member_id: string; user_id: string; user_name: string; login_id: string; status: string; team_id: string | null; joined_at: string | null; created_at: string };
type Team = { id: string; name: string; member_count: number; created_at: string };

const fmt = (iso: string) => { const d = new Date(iso); return `${d.getFullYear()}.${d.getMonth()+1}.${d.getDate()}`; };
const statusStyle: Record<string, string> = {
  ACTIVE: 'text-emerald-500 bg-emerald-50 dark:bg-emerald-900/20',
};
const statusLabel: Record<string, string> = { ACTIVE: '활성' };

const inputCls =
  'w-full px-3 py-2.5 text-sm border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl bg-white dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] focus:outline-none focus:border-[#3182F6] transition-colors';

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
      method: 'POST',
      headers: { Authorization: `Bearer ${getToken()}`, 'Content-Type': 'application/json' },
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white dark:bg-[#1C2333] rounded-2xl shadow-xl w-full max-w-md mx-4 p-6">
        <h2 className="text-lg font-bold text-[#191F28] dark:text-[#F2F4F6] mb-4">팀원 추가</h2>
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] block mb-1">이름</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="홍길동" className={inputCls} />
          </div>
          <div>
            <label className="text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] block mb-1">아이디</label>
            <input value={loginId} onChange={(e) => setLoginId(e.target.value)} placeholder="로그인 아이디" className={inputCls} />
          </div>
          <div>
            <label className="text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] block mb-1">비밀번호</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="8자 이상" className={inputCls} />
          </div>
          <div>
            <label className="text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] block mb-1">팀 (선택)</label>
            <select value={teamId} onChange={(e) => setTeamId(e.target.value)} className={inputCls}>
              <option value="">미배정</option>
              {teams.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>
          {error && (
            <p className="text-xs text-red-500 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>
          )}
        </div>
        <div className="flex gap-2 mt-5">
          <button onClick={onClose}
            className="flex-1 py-2.5 text-sm font-medium border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl text-[#4E5968] dark:text-[#9CA3AF] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] transition-colors">
            취소
          </button>
          <button onClick={submit} disabled={saving}
            className="flex-1 py-2.5 text-sm font-medium bg-[#3182F6] text-white rounded-xl hover:bg-[#1B6EEB] transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
            {saving ? '생성 중...' : '팀원 추가'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── 팀원 수정 모달 (이름·비밀번호만) ──────────────────────────
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
      method: 'PATCH',
      headers: { Authorization: `Bearer ${getToken()}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white dark:bg-[#1C2333] rounded-2xl shadow-xl w-full max-w-md mx-4 p-6">
        <h2 className="text-lg font-bold text-[#191F28] dark:text-[#F2F4F6] mb-1">팀원 수정</h2>
        <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mb-4">{member.login_id}</p>
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] block mb-1">이름</label>
            <input value={name} onChange={(e) => setName(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className="text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] block mb-1">새 비밀번호</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="변경 시에만 입력 (8자 이상)" className={inputCls} />
          </div>
          {error && (
            <p className="text-xs text-red-500 bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{error}</p>
          )}
        </div>
        <div className="flex gap-2 mt-5">
          <button onClick={onClose}
            className="flex-1 py-2.5 text-sm font-medium border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl text-[#4E5968] dark:text-[#9CA3AF] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] transition-colors">
            취소
          </button>
          <button onClick={submit} disabled={saving}
            className="flex-1 py-2.5 text-sm font-medium bg-[#3182F6] text-white rounded-xl hover:bg-[#1B6EEB] transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
            {saving ? '저장 중...' : '저장'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function CompanyMembersPage() {
  const [members, setMembers] = useState<Member[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState<Member | null>(null);

  const authHeaders = () => ({ Authorization: `Bearer ${getToken()}`, 'Content-Type': 'application/json' });

  const fetchAll = async () => {
    setLoading(true);
    const [m, t] = await Promise.all([
      fetch(`${API_BASE}/api/company/members`, { headers: authHeaders() }).then((r) => r.json()).catch(() => []),
      fetch(`${API_BASE}/api/company/teams`, { headers: authHeaders() }).then((r) => r.json()).catch(() => []),
    ]);
    if (Array.isArray(m)) setMembers(m);
    if (Array.isArray(t)) setTeams(t);
    setLoading(false);
  };

  useEffect(() => { fetchAll(); }, []);

  const handleDelete = async (memberId: string, name: string) => {
    if (!confirm(`'${name}' 멤버를 삭제할까요?\n계정과 멤버십이 제거되며, 만든 작업물은 회사에 남아 본인에게 이전됩니다.`)) return;
    const res = await fetch(`${API_BASE}/api/company/members/${memberId}`, { method: 'DELETE', headers: authHeaders() });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '삭제 실패' }));
      alert(err.detail ?? '삭제에 실패했습니다.');
      return;
    }
    await fetchAll();
  };

  return (
    <>
      <div className="px-8 py-8 max-w-5xl mx-auto space-y-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">멤버 관리</h1>
            <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">팀원 계정을 직접 만들고, 소속 멤버를 관리하세요</p>
          </div>
          <button onClick={() => setShowModal(true)}
            className="shrink-0 px-4 py-2.5 text-sm font-medium bg-[#3182F6] text-white rounded-xl hover:bg-[#1B6EEB] transition-colors">
            + 팀원 추가
          </button>
        </div>

        {/* 전체 멤버 */}
        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
          <div className="px-6 py-4 border-b border-[#E5E8EB] dark:border-[#2D3748]">
            <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">전체 멤버</p>
          </div>
          {loading ? (
            <div className="py-12 text-center text-sm text-[#8B95A1]">불러오는 중...</div>
          ) : members.length === 0 ? (
            <div className="py-12 text-center text-sm text-[#8B95A1]">멤버가 없습니다</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#F2F4F6] dark:border-[#252D3D] bg-[#F9FAFB] dark:bg-[#252D3D]">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-[#8B95A1]">이름</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">아이디</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">팀</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">상태</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">합류일</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.member_id} className="border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0 group">
                    <td className="px-6 py-3 font-medium text-[#191F28] dark:text-[#F2F4F6]">{m.user_name}</td>
                    <td className="px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">{m.login_id}</td>
                    <td className="px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">
                      {m.team_id ? (teams.find((t) => t.id === m.team_id)?.name ?? '—') : <span className="text-[#B0B8C1]">미배정</span>}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${statusStyle[m.status] ?? ''}`}>
                        {statusLabel[m.status] ?? m.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-[#8B95A1]">{m.joined_at ? fmt(m.joined_at) : '—'}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2 justify-end">
                        <button onClick={() => setEditing(m)}
                          className="px-2.5 py-1 text-xs text-[#4E5968] dark:text-[#9CA3AF] border border-[#E5E8EB] dark:border-[#2D3748] rounded-lg hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] transition-colors">수정</button>
                        <button onClick={() => handleDelete(m.member_id, m.user_name)}
                          className="px-2.5 py-1 text-xs text-[#8B95A1] rounded-lg hover:bg-red-50 hover:text-red-500 transition-colors">삭제</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {showModal && (
        <CreateMemberModal
          teams={teams}
          onClose={() => setShowModal(false)}
          onCreated={() => { setShowModal(false); fetchAll(); }}
        />
      )}
      {editing && (
        <EditMemberModal
          member={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); fetchAll(); }}
        />
      )}
    </>
  );
}
