'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import AppLayout from '@/components/AppLayout';
import { getToken } from '@/lib/authApi';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type SimDetail = {
  id: string;
  status: string;
  sample_size: number;
  result: Record<string, unknown> | null;
  persona_results: unknown[] | null;
  created_at: string;
  created_by_name: string | null;
  ad_id: string;
  ad_title: string | null;
  project_id: string;
  project_name: string;
};

const statusStyle: Record<string, { bg: string; text: string; label: string }> = {
  COMPLETED: { bg: 'bg-emerald-50 dark:bg-emerald-900/20', text: 'text-emerald-600', label: '완료' },
  QUEUED:    { bg: 'bg-yellow-50 dark:bg-yellow-900/20',   text: 'text-yellow-600',  label: '대기 중' },
  RUNNING:   { bg: 'bg-blue-50 dark:bg-blue-900/20',       text: 'text-blue-600',    label: '진행 중' },
  FAILED:    { bg: 'bg-red-50 dark:bg-red-900/20',         text: 'text-red-600',     label: '실패' },
};

const fmt = (iso: string) => new Date(iso).toLocaleString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start gap-4 py-3 border-b border-[#F2F4F6] dark:border-[#252D3D] last:border-0">
      <span className="w-28 shrink-0 text-sm text-[#8B95A1] dark:text-[#6B7280]">{label}</span>
      <span className="text-sm text-[#191F28] dark:text-[#F2F4F6] flex-1">{value}</span>
    </div>
  );
}

export default function SimulationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<SimDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch(`${API_BASE}/api/projects/simulations/${id}`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then(r => { if (!r.ok) throw new Error('not found'); return r.json(); })
      .then(setData)
      .catch(() => setError('시뮬레이션을 불러올 수 없습니다.'))
      .finally(() => setLoading(false));
  }, [id]);

  const st = data ? (statusStyle[data.status] ?? { bg: 'bg-gray-50', text: 'text-gray-600', label: data.status }) : null;

  return (
    <AppLayout>
      <div className="px-8 py-8 max-w-3xl mx-auto">
        {/* 뒤로가기 */}
        <button onClick={() => router.back()} className="flex items-center gap-1.5 text-sm text-[#8B95A1] hover:text-[#3182F6] transition-colors mb-6">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
          뒤로
        </button>

        {loading && <p className="text-sm text-[#8B95A1]">불러오는 중...</p>}
        {error && <p className="text-sm text-red-500">{error}</p>}

        {data && (
          <>
            <div className="flex items-start justify-between mb-6">
              <div>
                <p className="text-xs text-[#8B95A1] mb-1">{data.project_name}</p>
                <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">시뮬레이션 상세</h1>
              </div>
              {st && (
                <span className={`px-3 py-1.5 rounded-full text-sm font-medium ${st.bg} ${st.text}`}>
                  {st.label}
                </span>
              )}
            </div>

            {/* 기본 정보 */}
            <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl px-6 py-2 mb-6">
              <InfoRow label="ID" value={<span className="font-mono text-xs">{data.id}</span>} />
              <InfoRow label="프로젝트" value={data.project_name} />
              <InfoRow label="광고 제목" value={data.ad_title ?? '—'} />
              <InfoRow label="샘플 수" value={`${data.sample_size}명`} />
              <InfoRow label="실행자" value={data.created_by_name ?? '—'} />
              <InfoRow label="실행일시" value={fmt(data.created_at)} />
            </div>

            {/* 집계 결과 */}
            <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 mb-6">
              <h2 className="text-base font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-4">집계 결과</h2>
              {data.result ? (
                <pre className="text-xs bg-[#F9FAFB] dark:bg-[#161B27] rounded-xl p-4 overflow-x-auto text-[#4E5968] dark:text-[#9CA3AF] leading-relaxed whitespace-pre-wrap">
                  {JSON.stringify(data.result, null, 2)}
                </pre>
              ) : (
                <div className="py-8 text-center text-sm text-[#B0B8C1] dark:text-[#4B5563]">
                  {data.status === 'COMPLETED' ? '집계 데이터가 없습니다.' : '시뮬레이션이 아직 완료되지 않았습니다.'}
                </div>
              )}
            </div>

            {/* 페르소나별 반응 */}
            {data.persona_results && data.persona_results.length > 0 && (
              <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6">
                <h2 className="text-base font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-4">
                  페르소나별 반응 ({data.persona_results.length}명)
                </h2>
                <pre className="text-xs bg-[#F9FAFB] dark:bg-[#161B27] rounded-xl p-4 overflow-x-auto text-[#4E5968] dark:text-[#9CA3AF] leading-relaxed whitespace-pre-wrap">
                  {JSON.stringify(data.persona_results, null, 2)}
                </pre>
              </div>
            )}
          </>
        )}
      </div>
    </AppLayout>
  );
}
