'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { authedFetch } from '@/lib/api';
import { useAuth } from '@/components/AuthProvider';
import { useProjects } from '@/components/ProjectContext';
import { formatKST, formatKSTDate } from '@/lib/datetime';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Project = {
  id: string;
  name: string;
  description: string | null;
  status: string;
  created_by_name: string | null;
  created_at: string;
};
type SimRow = { id: string; status: string; sample_size: number; created_by_name: string | null; created_at: string };
type GenRow = { id: string; status: string; product_name: string | null; created_by_name: string | null; created_at: string };

const simStatusStyle: Record<string, string> = {
  COMPLETED: 'text-emerald-500 bg-emerald-50 dark:bg-emerald-900/20',
  QUEUED:    'text-yellow-500 bg-yellow-50 dark:bg-yellow-900/20',
  RUNNING:   'text-blue-500 bg-blue-50 dark:bg-blue-900/20',
  FAILED:    'text-red-500 bg-red-50 dark:bg-red-900/20',
};
const simStatusLabel: Record<string, string> = { COMPLETED: '완료', QUEUED: '대기', RUNNING: '진행 중', FAILED: '실패' };
const genStatusStyle: Record<string, string> = {
  completed: 'text-emerald-500 bg-emerald-50 dark:bg-emerald-900/20',
  pending:   'text-yellow-500 bg-yellow-50 dark:bg-yellow-900/20',
  running:   'text-blue-500 bg-blue-50 dark:bg-blue-900/20',
  failed:    'text-red-500 bg-red-50 dark:bg-red-900/20',
};
const genStatusLabel: Record<string, string> = { completed: '완료', pending: '대기', running: '진행 중', failed: '실패' };

const fmt = (iso: string) => formatKSTDate(iso);
const fmtFull = (iso: string) => formatKST(iso);

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start gap-4 py-3 border-b border-line last:border-0">
      <span className="w-28 shrink-0 text-sm text-ink-tertiary">{label}</span>
      <span className="text-sm text-ink flex-1">{value}</span>
    </div>
  );
}

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const { refresh: refreshProjects } = useProjects();
  const isAdmin = user?.role === 'ADMIN';

  const [project, setProject] = useState<Project | null>(null);
  const [sims, setSims] = useState<SimRow[]>([]);
  const [gens, setGens] = useState<GenRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [proj, s, g] = await Promise.all([
          authedFetch(`${API_BASE}/api/projects/${id}`).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
          authedFetch(`${API_BASE}/api/projects/${id}/simulations`).then(r => r.json()).catch(() => []),
          authedFetch(`${API_BASE}/api/projects/${id}/generations`).then(r => r.json()).catch(() => []),
        ]);
        setProject(proj);
        if (Array.isArray(s)) setSims(s);
        if (Array.isArray(g)) setGens(g);
      } catch {
        setError('프로젝트를 불러올 수 없습니다.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id]);

  const handleDelete = async () => {
    if (!confirm('프로젝트를 삭제하시겠습니까? 관련된 시뮬레이션과 제너레이터 내역도 함께 삭제됩니다.')) return;
    setDeleting(true);
    await authedFetch(`${API_BASE}/api/projects/${id}`, { method: 'DELETE' });
    await refreshProjects();
    router.push('/dashboard');
  };

  return (
      <div className="px-8 py-8 max-w-5xl mx-auto">
        {/* 뒤로가기 */}
        <button
          onClick={() => router.back()}
          className="flex items-center gap-1.5 text-sm text-ink-tertiary hover:text-primary transition-colors mb-6"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
          뒤로
        </button>

        {loading && <p className="text-sm text-ink-tertiary">불러오는 중...</p>}
        {error && <p className="text-sm text-red-500">{error}</p>}

        {project && (
          <>
            {/* 헤더 */}
            <div className="flex items-start justify-between mb-6">
              <div>
                <h1 className="text-2xl font-bold text-ink">{project.name}</h1>
                {project.description && (
                  <p className="text-sm text-ink-tertiary mt-1">{project.description}</p>
                )}
              </div>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm font-medium text-red-500 border border-red-200 dark:border-red-900/40 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-40"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14H6L5 6" /><path d="M10 11v6" /><path d="M14 11v6" /><path d="M9 6V4h6v2" />
                </svg>
                {deleting ? '삭제 중...' : '프로젝트 삭제'}
              </button>
            </div>

            {/* 기본 정보 */}
            <div className="bg-card border border-line rounded-2xl px-6 py-2 mb-6">
              {isAdmin && <InfoRow label="ID" value={<span className="font-mono text-xs">{project.id}</span>} />}
              <InfoRow label="생성자" value={project.created_by_name ?? '—'} />
              <InfoRow label="생성일" value={fmt(project.created_at)} />
            </div>

            {/* 시뮬레이션 */}
            <div className="bg-card border border-line rounded-2xl overflow-hidden mb-4">
              <div className="flex items-center justify-between px-6 py-4 border-b border-line">
                <div className="flex items-center gap-2">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-primary">
                    <circle cx="12" cy="12" r="10" /><polygon points="10 8 16 12 10 16 10 8" />
                  </svg>
                  <p className="text-sm font-semibold text-ink">시뮬레이션</p>
                  <span className="text-xs text-ink-tertiary">({sims.length})</span>
                </div>
              </div>
              {sims.length === 0 ? (
                <div className="py-10 text-center text-xs text-ink-muted">내역이 없습니다</div>
              ) : (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-line text-left">
                      <th className="px-6 py-3 font-medium text-ink-tertiary">상태</th>
                      <th className="px-3 py-3 font-medium text-ink-tertiary">샘플 수</th>
                      <th className="px-3 py-3 font-medium text-ink-tertiary">실행자</th>
                      <th className="px-3 py-3 font-medium text-ink-tertiary">일시</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sims.map(s => (
                      <tr
                        key={s.id}
                        onClick={() => router.push(`/simulation/${s.id}`)}
                        className="border-b border-line last:border-0 hover:bg-accent cursor-pointer transition-colors"
                      >
                        <td className="px-6 py-3">
                          <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${simStatusStyle[s.status] ?? ''}`}>
                            {simStatusLabel[s.status] ?? s.status}
                          </span>
                        </td>
                        <td className="px-3 py-3 text-ink-secondary">{s.sample_size}명</td>
                        <td className="px-3 py-3 text-ink-secondary">{s.created_by_name ?? '—'}</td>
                        <td className="px-3 py-3 text-ink-muted">{fmtFull(s.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* 제너레이터 */}
            <div className="bg-card border border-line rounded-2xl overflow-hidden">
              <div className="flex items-center justify-between px-6 py-4 border-b border-line">
                <div className="flex items-center gap-2">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-primary">
                    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                  </svg>
                  <p className="text-sm font-semibold text-ink">제너레이터</p>
                  <span className="text-xs text-ink-tertiary">({gens.length})</span>
                </div>
              </div>
              {gens.length === 0 ? (
                <div className="py-10 text-center text-xs text-ink-muted">내역이 없습니다</div>
              ) : (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-line text-left">
                      <th className="px-6 py-3 font-medium text-ink-tertiary">상품명</th>
                      <th className="px-3 py-3 font-medium text-ink-tertiary">상태</th>
                      <th className="px-3 py-3 font-medium text-ink-tertiary">실행자</th>
                      <th className="px-3 py-3 font-medium text-ink-tertiary">일시</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gens.map(g => (
                      <tr
                        key={g.id}
                        onClick={() => router.push(`/generations/${g.id}`)}
                        className="border-b border-line last:border-0 hover:bg-accent cursor-pointer transition-colors"
                      >
                        <td className="px-6 py-3 text-ink-secondary">{g.product_name ?? '—'}</td>
                        <td className="px-3 py-3">
                          <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${genStatusStyle[g.status] ?? ''}`}>
                            {genStatusLabel[g.status] ?? g.status}
                          </span>
                        </td>
                        <td className="px-3 py-3 text-ink-secondary">{g.created_by_name ?? '—'}</td>
                        <td className="px-3 py-3 text-ink-muted">{fmtFull(g.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </div>
  );
}
