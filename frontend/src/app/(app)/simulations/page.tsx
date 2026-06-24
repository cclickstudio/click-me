'use client';
// 통합 시뮬레이션 내역 — Role별로 데이터 소스만 분기(ADMIN=전체, USER/COMPANY=소속 조직).
// 행 클릭 시 결과 대시보드(/simulation/[id])로 이동. 삭제·복원은 상세 페이지에서 처리.

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/AuthProvider';
import { getToken } from '@/lib/authApi';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Row = {
  id: string;
  ad_id?: string;
  ad_title: string | null;
  status: string;
  sample_size: number;
  created_by_name: string | null;
  created_at: string;
};

const fmt = (iso: string) => {
  const d = new Date(iso);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};

const STATUS_LABEL: Record<string, { label: string; color: string }> = {
  QUEUED: { label: '대기', color: 'bg-[#F2F4F6] text-[#8B95A1]' },
  RUNNING: { label: '실행중', color: 'bg-[#EEF2FF] text-[#4F46E5]' },
  COMPLETED: { label: '완료', color: 'bg-[#ECFDF5] text-[#059669]' },
  FAILED: { label: '실패', color: 'bg-[#FEF2F2] text-[#DC2626]' },
};

export default function SimulationsPage() {
  const router = useRouter();
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';
  const [list, setList] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    // ADMIN은 전체 시뮬, 그 외(USER/COMPANY)는 소속 조직 시뮬 — 데이터 소스만 다르다.
    const path = user.role === 'ADMIN' ? '/api/admin/simulations' : '/api/company/simulations';
    setLoading(true);
    fetch(`${API_BASE}${path}`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => r.json())
      .then(d => setList(Array.isArray(d) ? d : []))
      .catch(() => setList([]))
      .finally(() => setLoading(false));
  }, [user]);

  return (
      <div className="px-8 py-8 max-w-5xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">시뮬레이션 내역</h1>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">
            {isAdmin ? '전체 사용자 시뮬레이션 실행 목록' : '소속 조직의 시뮬레이션 실행 목록'}
          </p>
        </div>
        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
          {loading ? (
            <div className="py-20 text-center text-sm text-[#8B95A1]">불러오는 중...</div>
          ) : list.length === 0 ? (
            <div className="py-20 text-center text-sm text-[#8B95A1]">시뮬레이션 내역이 없습니다</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#F2F4F6] dark:border-[#252D3D] bg-[#F9FAFB] dark:bg-[#252D3D]">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-[#8B95A1]">광고명</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">상태</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">샘플 수</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">실행자</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-[#8B95A1]">실행일</th>
                </tr>
              </thead>
              <tbody>
                {list.map(r => {
                  const s = STATUS_LABEL[r.status] ?? { label: r.status, color: 'bg-[#F2F4F6] text-[#8B95A1]' };
                  return (
                    <tr
                      key={r.id}
                      onClick={() => router.push(`/simulation/${r.id}`)}
                      className="border-b border-[#F9FAFB] dark:border-[#1C2333] last:border-0 hover:bg-[#F9FAFB] dark:hover:bg-[#252D3D] cursor-pointer transition-colors"
                    >
                      <td className="px-6 py-3 text-[#191F28] dark:text-[#F2F4F6] font-medium">{r.ad_title ?? '—'}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${s.color}`}>{s.label}</span>
                      </td>
                      <td className="px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">{r.sample_size}명</td>
                      <td className="px-4 py-3 text-[#4E5968] dark:text-[#9CA3AF]">{r.created_by_name ?? '—'}</td>
                      <td className="px-4 py-3 text-[#8B95A1]">{fmt(r.created_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
  );
}
