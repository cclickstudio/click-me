'use client';

import { useEffect, useState } from 'react';
import AppLayout from '@/components/AppLayout';
import { getToken } from '@/lib/authApi';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type ChatRow = { id: string; project_id: string | null; message_count: number; created_at: string };

function formatDate(iso: string) {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

export default function AdminChatsPage() {
  const [list, setList] = useState<ChatRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/api/admin/chats`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => r.json()).then(setList).finally(() => setLoading(false));
  }, []);

  return (
    <AppLayout>
      <div className="px-8 py-8 max-w-5xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">채팅 내역</h1>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">전체 사용자 채팅 세션 목록</p>
        </div>
        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
          {loading ? (
            <div className="py-20 text-center text-sm text-[#8B95A1]">불러오는 중...</div>
          ) : list.length === 0 ? (
            <div className="py-20 text-center text-sm text-[#8B95A1]">채팅 내역이 없습니다</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#F2F4F6] dark:border-[#252D3D] bg-[#F9FAFB] dark:bg-[#252D3D]">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-[#8B95A1]">세션 ID</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">메시지 수</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">프로젝트 ID</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">생성일</th>
                </tr>
              </thead>
              <tbody>
                {list.map((r) => (
                  <tr key={r.id} className="border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0 hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] transition-colors">
                    <td className="px-6 py-3 font-mono text-xs text-[#4E5968] dark:text-[#9CA3AF]">{r.id.slice(0, 8)}…</td>
                    <td className="px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">{r.message_count}개</td>
                    <td className="px-4 py-3 font-mono text-xs text-[#8B95A1]">{r.project_id ? r.project_id.slice(0, 8) + '…' : '—'}</td>
                    <td className="px-4 py-3 text-[#8B95A1]">{formatDate(r.created_at)}</td>
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
