'use client';

import { useEffect, useState } from 'react';
import AppLayout from '@/components/AppLayout';
import { getToken } from '@/lib/authApi';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type PendingMember = { member_id: string; user_id: string; user_name: string; email: string; created_at: string };
type Member = { member_id: string; user_id: string; user_name: string; email: string; status: string; joined_at: string | null; created_at: string };

const fmt = (iso: string) => { const d = new Date(iso); return `${d.getFullYear()}.${d.getMonth()+1}.${d.getDate()}`; };
const statusStyle: Record<string, string> = {
  ACTIVE:   'text-emerald-500 bg-emerald-50 dark:bg-emerald-900/20',
  PENDING:  'text-yellow-500 bg-yellow-50 dark:bg-yellow-900/20',
  REJECTED: 'text-red-500 bg-red-50 dark:bg-red-900/20',
};
const statusLabel: Record<string, string> = { ACTIVE:'승인됨', PENDING:'대기', REJECTED:'반려됨' };

export default function CompanyMembersPage() {
  const [pending, setPending] = useState<PendingMember[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);

  const authHeaders = () => ({ Authorization: `Bearer ${getToken()}`, 'Content-Type': 'application/json' });

  const fetchAll = async () => {
    setLoading(true);
    const [p, m] = await Promise.all([
      fetch(`${API_BASE}/api/company/pending-members`, { headers: authHeaders() }).then((r) => r.json()).catch(() => []),
      fetch(`${API_BASE}/api/company/members`, { headers: authHeaders() }).then((r) => r.json()).catch(() => []),
    ]);
    if (Array.isArray(p)) setPending(p);
    if (Array.isArray(m)) setMembers(m);
    setLoading(false);
  };

  useEffect(() => { fetchAll(); }, []);

  const handle = async (memberId: string, action: 'approve' | 'reject') => {
    await fetch(`${API_BASE}/api/company/${action}-member/${memberId}`, { method: 'POST', headers: authHeaders() });
    await fetchAll();
  };

  return (
    <AppLayout>
      <div className="px-8 py-8 max-w-5xl mx-auto space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">멤버 관리</h1>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">소속 멤버를 승인하고 관리하세요</p>
        </div>

        {/* 승인 대기 */}
        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
          <div className="px-6 py-4 border-b border-[#E5E8EB] dark:border-[#2D3748] flex items-center gap-2">
            <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">승인 대기</p>
            {pending.length > 0 && (
              <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-[#F74D4D] text-white text-[10px] font-bold">{pending.length}</span>
            )}
          </div>
          {loading ? (
            <div className="py-12 text-center text-sm text-[#8B95A1]">불러오는 중...</div>
          ) : pending.length === 0 ? (
            <div className="py-12 text-center text-sm text-[#8B95A1]">대기 중인 멤버가 없습니다</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#F2F4F6] dark:border-[#252D3D] bg-[#F9FAFB] dark:bg-[#252D3D]">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-[#8B95A1]">이름</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">이메일</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">신청일</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {pending.map((m) => (
                  <tr key={m.member_id} className="border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0 hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors">
                    <td className="px-6 py-4 font-medium text-[#191F28] dark:text-[#F2F4F6]">{m.user_name}</td>
                    <td className="px-4 py-4 text-[#4E5968] dark:text-[#9CA3AF]">{m.email}</td>
                    <td className="px-4 py-4 text-[#8B95A1]">{fmt(m.created_at)}</td>
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-2 justify-end">
                        <button onClick={() => handle(m.member_id, 'approve')}
                          className="px-3 py-1.5 bg-[#3182F6] text-white text-xs font-medium rounded-lg hover:bg-[#1B6EEB] transition-colors">승인</button>
                        <button onClick={() => handle(m.member_id, 'reject')}
                          className="px-3 py-1.5 border border-[#E5E8EB] dark:border-[#2D3748] text-xs text-[#8B95A1] rounded-lg hover:bg-red-50 hover:text-red-500 hover:border-red-200 transition-colors">반려</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* 전체 멤버 */}
        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
          <div className="px-6 py-4 border-b border-[#E5E8EB] dark:border-[#2D3748]">
            <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">전체 멤버</p>
          </div>
          {members.length === 0 ? (
            <div className="py-12 text-center text-sm text-[#8B95A1]">멤버가 없습니다</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#F2F4F6] dark:border-[#252D3D] bg-[#F9FAFB] dark:bg-[#252D3D]">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-[#8B95A1]">이름</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">이메일</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">상태</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">합류일</th>
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.member_id} className="border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0">
                    <td className="px-6 py-3 font-medium text-[#191F28] dark:text-[#F2F4F6]">{m.user_name}</td>
                    <td className="px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">{m.email}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${statusStyle[m.status] ?? ''}`}>
                        {statusLabel[m.status] ?? m.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-[#8B95A1]">{m.joined_at ? fmt(m.joined_at) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
