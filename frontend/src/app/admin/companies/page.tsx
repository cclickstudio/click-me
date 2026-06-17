'use client';

// 조직 관리 — 기업 승인·조직 목록 + 계정(ADMIN/COMPANY/USER) 직접 생성·삭제.

import { useEffect, useState } from 'react';
import AppLayout from '@/components/AppLayout';
import { getToken } from '@/lib/authApi';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Organization = {
  id: string;
  name: string;
  status: string;
  created_at: string;
};

type AccountRole = 'ADMIN' | 'COMPANY' | 'USER';
type Account = {
  id: string;
  login_id: string;
  name: string;
  role: AccountRole;
  status: string;
  created_at: string;
};

function formatDate(iso: string) {
  const d = new Date(iso);
  return `${d.getFullYear()}.${d.getMonth() + 1}.${d.getDate()}`;
}

const orgStatusStyle: Record<string, string> = {
  ACTIVE: 'text-emerald-500 bg-emerald-50 dark:bg-emerald-900/20',
  PENDING: 'text-yellow-500 bg-yellow-50 dark:bg-yellow-900/20',
  REJECTED: 'text-red-500 bg-red-50 dark:bg-red-900/20',
};
const orgStatusLabel: Record<string, string> = { ACTIVE: '활성', PENDING: '대기', REJECTED: '반려' };

const roleStyle: Record<AccountRole, string> = {
  ADMIN: 'text-purple-500 bg-purple-50 dark:bg-purple-900/20',
  COMPANY: 'text-[#3182F6] bg-[#EBF3FF] dark:bg-[#1E3A5F]',
  USER: 'text-[#4E5968] bg-[#F2F4F6] dark:bg-[#252D3D] dark:text-[#9CA3AF]',
};

const inputCls =
  'w-full px-3 py-2.5 text-sm border border-[#E5E8EB] dark:border-[#2D3748] rounded-xl bg-white dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] focus:outline-none focus:border-[#3182F6] transition-colors';

// ── 계정 생성 모달 ──────────────────────────────────────────
function CreateAccountModal({
  orgs,
  onClose,
  onCreated,
}: {
  orgs: Organization[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [role, setRole] = useState<AccountRole>('USER');
  const [name, setName] = useState('');
  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [orgId, setOrgId] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const activeOrgs = orgs.filter((o) => o.status === 'ACTIVE');

  const submit = async () => {
    setError('');
    if (!name.trim() || !loginId.trim() || password.length < 8) {
      setError('이름·아이디·비밀번호(8자 이상)를 확인해주세요.');
      return;
    }
    if (role === 'COMPANY' && !companyName.trim()) {
      setError('회사명을 입력해주세요.');
      return;
    }
    if (role === 'USER' && !orgId) {
      setError('소속 조직을 선택해주세요.');
      return;
    }
    setSaving(true);
    const res = await fetch(`${API_BASE}/api/admin/users`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${getToken()}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name.trim(),
        login_id: loginId.trim(),
        password,
        role,
        company_name: role === 'COMPANY' ? companyName.trim() : null,
        organization_id: role === 'USER' ? orgId : null,
      }),
    });
    setSaving(false);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '생성 실패' }));
      setError(err.detail ?? '계정 생성에 실패했습니다.');
      return;
    }
    onCreated();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white dark:bg-[#1C2333] rounded-2xl shadow-xl w-full max-w-md mx-4 p-6">
        <h2 className="text-lg font-bold text-[#191F28] dark:text-[#F2F4F6] mb-4">계정 생성</h2>
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] block mb-1">역할</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as AccountRole)}
              className={inputCls}
            >
              <option value="ADMIN">ADMIN — 관리자</option>
              <option value="COMPANY">COMPANY — 기업(신규 조직 생성)</option>
              <option value="USER">USER — 팀원(기존 조직 소속)</option>
            </select>
          </div>
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

          {role === 'COMPANY' && (
            <div>
              <label className="text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] block mb-1">회사명 (새 조직)</label>
              <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="(주)클릭미" className={inputCls} />
            </div>
          )}
          {role === 'USER' && (
            <div>
              <label className="text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] block mb-1">소속 조직</label>
              <select value={orgId} onChange={(e) => setOrgId(e.target.value)} className={inputCls}>
                <option value="">조직 선택…</option>
                {activeOrgs.map((o) => (
                  <option key={o.id} value={o.id}>{o.name}</option>
                ))}
              </select>
              {activeOrgs.length === 0 && (
                <p className="text-xs text-[#B0B8C1] mt-1">활성 조직이 없습니다. 먼저 COMPANY 계정을 만드세요.</p>
              )}
            </div>
          )}

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
            {saving ? '생성 중...' : '계정 생성'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── 계정 수정 모달 (이름·비밀번호만) ──────────────────────────
function EditAccountModal({
  account,
  onClose,
  onSaved,
}: {
  account: Account;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(account.name);
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
    const res = await fetch(`${API_BASE}/api/admin/users/${account.id}`, {
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
        <h2 className="text-lg font-bold text-[#191F28] dark:text-[#F2F4F6] mb-1">계정 수정</h2>
        <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mb-4">{account.login_id} · {account.role}</p>
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

export default function AdminCompaniesPage() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState<Account | null>(null);

  const authHeaders = () => ({ Authorization: `Bearer ${getToken()}`, 'Content-Type': 'application/json' });

  const fetchList = async () => {
    setLoading(true);
    const [orgsRes, usersRes] = await Promise.all([
      fetch(`${API_BASE}/api/admin/organizations`, { headers: authHeaders() }),
      fetch(`${API_BASE}/api/admin/users`, { headers: authHeaders() }),
    ]);
    if (orgsRes.ok) setOrgs(await orgsRes.json());
    if (usersRes.ok) setAccounts(await usersRes.json());
    setLoading(false);
  };

  useEffect(() => { fetchList(); }, []);

  const handleDeleteOrg = async (orgId: string, name: string) => {
    if (!confirm(`'${name}' 회사를 삭제할까요?\n소속 프로젝트·시뮬·생성·멤버·계정이 전부 삭제되며 되돌릴 수 없습니다.`)) return;
    const res = await fetch(`${API_BASE}/api/admin/companies/${orgId}`, { method: 'DELETE', headers: authHeaders() });
    if (!res.ok) { alert('삭제에 실패했습니다.'); return; }
    await fetchList();
  };

  // COMPANY(조직 계정)는 '전체 조직'에서만 관리 — 전체 계정 목록에서는 제외
  const visibleAccounts = accounts.filter((a) => a.role !== 'COMPANY');

  const handleDeleteAccount = async (id: string, name: string) => {
    if (!confirm(`'${name}' 계정을 삭제할까요?\n계정과 멤버십이 제거됩니다. 만든 작업물은 관리자에게 이전됩니다.`)) return;
    const res = await fetch(`${API_BASE}/api/admin/users/${id}`, { method: 'DELETE', headers: authHeaders() });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '삭제 실패' }));
      alert(err.detail ?? '삭제에 실패했습니다.');
      return;
    }
    await fetchList();
  };

  return (
    <AppLayout>
      <div className="px-8 py-8 max-w-5xl mx-auto space-y-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">조직 관리</h1>
            <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">계정을 직접 생성하고, 조직·계정을 관리·삭제하세요</p>
          </div>
          <button onClick={() => setShowModal(true)}
            className="shrink-0 px-4 py-2.5 text-sm font-medium bg-[#3182F6] text-white rounded-xl hover:bg-[#1B6EEB] transition-colors">
            + 계정 생성
          </button>
        </div>

        {/* 전체 계정 */}
        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
          <div className="px-6 py-4 border-b border-[#E5E8EB] dark:border-[#2D3748]">
            <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">전체 계정</p>
          </div>
          {loading ? (
            <div className="py-12 text-center text-sm text-[#8B95A1] dark:text-[#6B7280]">불러오는 중...</div>
          ) : visibleAccounts.length === 0 ? (
            <div className="py-12 text-center text-sm text-[#8B95A1] dark:text-[#6B7280]">계정이 없습니다</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#F2F4F6] dark:border-[#252D3D] bg-[#F9FAFB] dark:bg-[#252D3D]">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280]">이름</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280]">아이디</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280]">역할</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280]">상태</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280]">생성일</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {visibleAccounts.map((a) => (
                  <tr key={a.id} className="border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0 hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors">
                    <td className="px-6 py-4 font-medium text-[#191F28] dark:text-[#F2F4F6]">{a.name}</td>
                    <td className="px-4 py-4 text-[#4E5968] dark:text-[#9CA3AF]">{a.login_id}</td>
                    <td className="px-4 py-4">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${roleStyle[a.role] ?? ''}`}>{a.role}</span>
                    </td>
                    <td className="px-4 py-4">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${orgStatusStyle[a.status] ?? ''}`}>
                        {orgStatusLabel[a.status] ?? a.status}
                      </span>
                    </td>
                    <td className="px-4 py-4 text-[#8B95A1] dark:text-[#6B7280]">{formatDate(a.created_at)}</td>
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-2 justify-end">
                        <button onClick={() => setEditing(a)}
                          className="px-3 py-1.5 text-xs text-[#4E5968] dark:text-[#9CA3AF] border border-[#E5E8EB] dark:border-[#2D3748] rounded-lg hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] transition-colors">수정</button>
                        {a.role === 'COMPANY' ? (
                          <button disabled title="COMPANY 계정은 '전체 조직'에서 조직째 삭제하세요"
                            className="px-3 py-1.5 text-xs text-[#B0B8C1] dark:text-[#4B5563] rounded-lg cursor-not-allowed">삭제</button>
                        ) : (
                          <button onClick={() => handleDeleteAccount(a.id, a.name)}
                            className="px-3 py-1.5 text-xs text-[#8B95A1] rounded-lg hover:bg-red-50 hover:text-red-500 transition-colors">삭제</button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* 전체 조직 */}
        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
          <div className="px-6 py-4 border-b border-[#E5E8EB] dark:border-[#2D3748]">
            <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">전체 조직</p>
          </div>
          {loading ? (
            <div className="py-12 text-center text-sm text-[#8B95A1] dark:text-[#6B7280]">불러오는 중...</div>
          ) : orgs.length === 0 ? (
            <div className="py-12 text-center text-sm text-[#8B95A1] dark:text-[#6B7280]">등록된 조직이 없습니다</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#F2F4F6] dark:border-[#252D3D] bg-[#F9FAFB] dark:bg-[#252D3D]">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280]">회사명</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280]">상태</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280]">생성일</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {orgs.map((o) => (
                  <tr key={o.id} className="border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0 hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors">
                    <td className="px-6 py-4 font-medium text-[#191F28] dark:text-[#F2F4F6]">{o.name}</td>
                    <td className="px-4 py-4">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${orgStatusStyle[o.status] ?? ''}`}>
                        {orgStatusLabel[o.status] ?? o.status}
                      </span>
                    </td>
                    <td className="px-4 py-4 text-[#8B95A1] dark:text-[#6B7280]">{formatDate(o.created_at)}</td>
                    <td className="px-4 py-4 text-right">
                      <button onClick={() => handleDeleteOrg(o.id, o.name)}
                        className="px-3 py-1.5 text-xs text-[#8B95A1] rounded-lg hover:bg-red-50 hover:text-red-500 transition-colors">삭제</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {showModal && (
        <CreateAccountModal
          orgs={orgs}
          onClose={() => setShowModal(false)}
          onCreated={() => { setShowModal(false); fetchList(); }}
        />
      )}
      {editing && (
        <EditAccountModal
          account={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); fetchList(); }}
        />
      )}
    </AppLayout>
  );
}
