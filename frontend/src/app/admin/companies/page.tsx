'use client';

import { useEffect, useState } from 'react';
import AppLayout from '@/components/AppLayout';
import { getToken } from '@/lib/authApi';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type PendingCompany = {
  user_id: string;
  user_name: string;
  email: string;
  company_name: string;
  organization_id: string;
  created_at: string;
};

function formatDate(iso: string) {
  const d = new Date(iso);
  return `${d.getFullYear()}.${d.getMonth() + 1}.${d.getDate()}`;
}

export default function AdminCompaniesPage() {
  const [list, setList] = useState<PendingCompany[]>([]);
  const [loading, setLoading] = useState(true);

  const authHeaders = () => ({ Authorization: `Bearer ${getToken()}`, 'Content-Type': 'application/json' });

  const fetchList = async () => {
    setLoading(true);
    const res = await fetch(`${API_BASE}/api/admin/pending-companies`, { headers: authHeaders() });
    if (res.ok) setList(await res.json());
    setLoading(false);
  };

  useEffect(() => { fetchList(); }, []);

  const handle = async (userId: string, action: 'approve' | 'reject') => {
    await fetch(`${API_BASE}/api/admin/${action}-company/${userId}`, { method: 'POST', headers: authHeaders() });
    await fetchList();
  };

  return (
    <AppLayout>
      <div className="px-8 py-8 max-w-5xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">기업 계정 승인</h1>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">가입 대기 중인 기업 계정을 검토하고 승인하세요</p>
        </div>

        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
          {loading ? (
            <div className="py-20 text-center text-sm text-[#8B95A1] dark:text-[#6B7280]">불러오는 중...</div>
          ) : list.length === 0 ? (
            <div className="py-20 text-center text-sm text-[#8B95A1] dark:text-[#6B7280]">대기 중인 기업 계정이 없습니다</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#F2F4F6] dark:border-[#252D3D] bg-[#F9FAFB] dark:bg-[#252D3D]">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280]">회사명</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280]">담당자</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280]">이메일</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280]">가입일</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1] dark:text-[#6B7280]">Organization ID</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {list.map((c) => (
                  <tr key={c.user_id} className="border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0 hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors">
                    <td className="px-6 py-4 font-medium text-[#191F28] dark:text-[#F2F4F6]">{c.company_name}</td>
                    <td className="px-4 py-4 text-[#4E5968] dark:text-[#9CA3AF]">{c.user_name}</td>
                    <td className="px-4 py-4 text-[#4E5968] dark:text-[#9CA3AF]">{c.email}</td>
                    <td className="px-4 py-4 text-[#8B95A1] dark:text-[#6B7280]">{formatDate(c.created_at)}</td>
                    <td className="px-4 py-4 font-mono text-xs text-[#8B95A1] dark:text-[#6B7280]">{c.organization_id.slice(0, 8)}…</td>
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-2 justify-end">
                        <button onClick={() => handle(c.user_id, 'approve')}
                          className="px-3 py-1.5 bg-[#3182F6] text-white text-xs font-medium rounded-lg hover:bg-[#1B6EEB] transition-colors">
                          승인
                        </button>
                        <button onClick={() => handle(c.user_id, 'reject')}
                          className="px-3 py-1.5 border border-[#E5E8EB] dark:border-[#2D3748] text-xs font-medium text-[#8B95A1] dark:text-[#6B7280] rounded-lg hover:bg-red-50 hover:text-red-500 hover:border-red-200 transition-colors">
                          반려
                        </button>
                      </div>
                    </td>
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
