'use client';

import { useEffect, useState } from 'react';
import AppLayout from '@/components/AppLayout';
import { getToken } from '@/lib/authApi';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Row = { id: string; status: string; product_name: string | null; project_name: string | null; created_by_name: string | null; created_at: string };

const fmt = (iso: string) => {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};

const statusStyle: Record<string, string> = {
  completed: 'text-emerald-500 bg-emerald-50 dark:bg-emerald-900/20',
  running:   'text-blue-500 bg-blue-50 dark:bg-blue-900/20',
  pending:   'text-yellow-500 bg-yellow-50 dark:bg-yellow-900/20',
  failed:    'text-red-500 bg-red-50 dark:bg-red-900/20',
};
const statusLabel: Record<string, string> = {
  completed: '완료', running: '진행 중', pending: '대기', failed: '실패',
};

export default function CompanyGenerationsPage() {
  const [list, setList] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/api/company/generations`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then((r) => r.json())
      .then((data) => { if (Array.isArray(data)) setList(data); })
      .finally(() => setLoading(false));
  }, []);

  return (
    <AppLayout>
      <div className="px-8 py-8 max-w-5xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">제너레이터 내역</h1>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">우리 조직의 광고 생성 목록</p>
        </div>
        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
          {loading ? (
            <div className="py-20 text-center text-sm text-[#8B95A1]">불러오는 중...</div>
          ) : list.length === 0 ? (
            <div className="py-20 text-center text-sm text-[#8B95A1]">제너레이터 내역이 없습니다</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#F2F4F6] dark:border-[#252D3D] bg-[#F9FAFB] dark:bg-[#252D3D]">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-[#8B95A1]">ID</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">상품명</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">프로젝트</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">실행자</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">상태</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">생성일</th>
                </tr>
              </thead>
              <tbody>
                {list.map((r) => (
                  <tr key={r.id} className="border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0 hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors">
                    <td className="px-6 py-3 font-mono text-xs text-[#4E5968] dark:text-[#9CA3AF]">{r.id.slice(0, 8)}…</td>
                    <td className="px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">{r.product_name ?? '—'}</td>
                    <td className="px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">{r.project_name ?? '—'}</td>
                    <td className="px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">{r.created_by_name ?? '—'}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${statusStyle[r.status] ?? ''}`}>
                        {statusLabel[r.status] ?? r.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-[#8B95A1]">{fmt(r.created_at)}</td>
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
