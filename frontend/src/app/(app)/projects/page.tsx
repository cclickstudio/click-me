'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { authedFetch } from '@/lib/api';
import { formatKST, formatKSTDate } from '@/lib/datetime';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Project = { id: string; name: string; description: string | null; status: string; created_by_name: string | null; created_at: string };
type SimRow = { id: string; status: string; sample_size: number; created_by_name: string | null; created_at: string };
type GenRow = { id: string; status: string; product_name: string | null; created_by_name: string | null; created_at: string };

const fmt = (iso: string) => formatKSTDate(iso);
const fmtFull = (iso: string) => formatKST(iso);

const simStatusStyle: Record<string, string> = {
  COMPLETED: 'text-emerald-500 bg-emerald-50 dark:bg-emerald-900/20',
  QUEUED: 'text-yellow-500 bg-yellow-50 dark:bg-yellow-900/20',
  RUNNING: 'text-blue-500 bg-blue-50 dark:bg-blue-900/20',
  FAILED: 'text-red-500 bg-red-50 dark:bg-red-900/20',
};
const simStatusLabel: Record<string, string> = { COMPLETED: '완료', QUEUED: '대기', RUNNING: '진행 중', FAILED: '실패' };
const genStatusStyle: Record<string, string> = {
  completed: 'text-emerald-500 bg-emerald-50 dark:bg-emerald-900/20',
  pending: 'text-yellow-500 bg-yellow-50 dark:bg-yellow-900/20',
  running: 'text-blue-500 bg-blue-50 dark:bg-blue-900/20',
  failed: 'text-red-500 bg-red-50 dark:bg-red-900/20',
};
const genStatusLabel: Record<string, string> = { completed: '완료', pending: '대기', running: '진행 중', failed: '실패' };

function ProjectCard({ project, onDelete }: { project: Project; onDelete: (id: string) => void }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [sims, setSims] = useState<SimRow[]>([]);
  const [gens, setGens] = useState<GenRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && !loaded) {
      setLoading(true);
      const [s, g] = await Promise.all([
        authedFetch(`${API_BASE}/api/projects/${project.id}/simulations`).then(r => r.json()).catch(() => []),
        authedFetch(`${API_BASE}/api/projects/${project.id}/generations`).then(r => r.json()).catch(() => []),
      ]);
      if (Array.isArray(s)) setSims(s);
      if (Array.isArray(g)) setGens(g);
      setLoaded(true);
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm('프로젝트를 삭제하시겠습니까?')) return;
    setDeleting(true);
    await authedFetch(`${API_BASE}/api/projects/${project.id}`, { method: 'DELETE' });
    onDelete(project.id);
  };

  return (
    <div className="bg-card border border-line rounded-2xl overflow-hidden">
      {/* 헤더 */}
      <div
        className="flex items-center gap-3 px-5 py-4 cursor-pointer hover:bg-accent transition-colors select-none"
        onClick={toggle}
      >
        <svg
          width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
          className={`text-ink-tertiary transition-transform duration-150 shrink-0 ${open ? 'rotate-90' : ''}`}
        >
          <polyline points="9 18 15 12 9 6" />
        </svg>
        <div className="w-8 h-8 rounded-xl bg-primary-subtle flex items-center justify-center shrink-0">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#3182F6" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-ink truncate">{project.name}</p>
          {project.description && <p className="text-xs text-ink-tertiary truncate">{project.description}</p>}
        </div>
        <div className="flex items-center gap-3 shrink-0" onClick={e => e.stopPropagation()}>
          <span className="text-xs text-ink-muted">{fmt(project.created_at)}</span>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="p-1.5 rounded-lg text-ink-tertiary hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20 transition-colors disabled:opacity-40"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14H6L5 6" /><path d="M10 11v6" /><path d="M14 11v6" /><path d="M9 6V4h6v2" />
            </svg>
          </button>
        </div>
      </div>

      {/* 펼쳐진 내역 */}
      {open && (
        <div className="border-t border-line">
          {loading ? (
            <div className="py-8 text-center text-xs text-ink-tertiary">불러오는 중...</div>
          ) : (
            <div className="divide-y divide-line">
              {/* 시뮬레이션 */}
              <div className="px-5 py-3">
                <p className="text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2">
                  시뮬레이션 ({sims.length})
                </p>
                {sims.length === 0 ? (
                  <p className="text-xs text-ink-muted">내역이 없습니다</p>
                ) : (
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left">
                        <th className="pb-2 font-medium text-ink-tertiary pr-4">상태</th>
                        <th className="pb-2 font-medium text-ink-tertiary pr-4">샘플 수</th>
                        <th className="pb-2 font-medium text-ink-tertiary pr-4">실행자</th>
                        <th className="pb-2 font-medium text-ink-tertiary">일시</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#F9FAFB] dark:divide-[#1C2333]">
                      {sims.map(s => (
                        <tr
                          key={s.id}
                          onClick={() => router.push(`/simulation/${s.id}`)}
                          className="cursor-pointer hover:bg-accent transition-colors"
                        >
                          <td className="py-1.5 pr-4">
                            <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${simStatusStyle[s.status] ?? ''}`}>
                              {simStatusLabel[s.status] ?? s.status}
                            </span>
                          </td>
                          <td className="py-1.5 pr-4 text-ink-secondary">{s.sample_size}명</td>
                          <td className="py-1.5 pr-4 text-ink-secondary">{s.created_by_name ?? '—'}</td>
                          <td className="py-1.5 text-ink-tertiary">{fmtFull(s.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              {/* 제너레이터 */}
              <div className="px-5 py-3">
                <p className="text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2">
                  제너레이터 ({gens.length})
                </p>
                {gens.length === 0 ? (
                  <p className="text-xs text-ink-muted">내역이 없습니다</p>
                ) : (
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left">
                        <th className="pb-2 font-medium text-ink-tertiary pr-4">상품명</th>
                        <th className="pb-2 font-medium text-ink-tertiary pr-4">상태</th>
                        <th className="pb-2 font-medium text-ink-tertiary pr-4">실행자</th>
                        <th className="pb-2 font-medium text-ink-tertiary">일시</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#F9FAFB] dark:divide-[#1C2333]">
                      {gens.map(g => (
                        <tr
                          key={g.id}
                          onClick={() => router.push(`/generations/${g.id}`)}
                          className="cursor-pointer hover:bg-accent transition-colors"
                        >
                          <td className="py-1.5 pr-4 text-ink-secondary">{g.product_name ?? '—'}</td>
                          <td className="py-1.5 pr-4">
                            <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${genStatusStyle[g.status] ?? ''}`}>
                              {genStatusLabel[g.status] ?? g.status}
                            </span>
                          </td>
                          <td className="py-1.5 pr-4 text-ink-secondary">{g.created_by_name ?? '—'}</td>
                          <td className="py-1.5 text-ink-tertiary">{fmtFull(g.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [creating, setCreating] = useState(false);

  const fetchProjects = async () => {
    setLoading(true);
    const res = await authedFetch(`${API_BASE}/api/projects`);
    const data = await res.json();
    if (Array.isArray(data)) setProjects(data);
    setLoading(false);
  };

  useEffect(() => { fetchProjects(); }, []);

  const handleCreate = async () => {
    if (!name.trim()) return;
    setCreating(true);
    await authedFetch(`${API_BASE}/api/projects`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim(), description: description.trim() || null }),
    });
    setName(''); setDescription(''); setShowModal(false); setCreating(false);
    await fetchProjects();
  };

  return (
    <>
      <div className="px-8 py-8 max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-ink">프로젝트 관리</h1>
            <p className="text-sm text-ink-tertiary mt-1">프로젝트를 클릭하면 시뮬레이션·제너레이터 내역을 확인할 수 있습니다</p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:bg-primary-hover transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            새 프로젝트
          </button>
        </div>

        {loading ? (
          <div className="py-20 text-center text-sm text-ink-tertiary">불러오는 중...</div>
        ) : projects.length === 0 ? (
          <div className="py-20 text-center">
            <div className="w-14 h-14 bg-surface-1 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#8B95A1" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <p className="text-sm font-medium text-ink">프로젝트가 없습니다</p>
            <p className="text-xs text-ink-tertiary mt-1">새 프로젝트를 만들어 시작하세요</p>
            <button
              onClick={() => setShowModal(true)}
              className="mt-4 px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:bg-primary-hover transition-colors"
            >
              첫 프로젝트 만들기
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {projects.map((p) => (
              <ProjectCard
                key={p.id}
                project={p}
                onDelete={(id) => setProjects((prev) => prev.filter((x) => x.id !== id))}
              />
            ))}
          </div>
        )}
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-card rounded-2xl shadow-xl w-full max-w-md mx-4 p-6">
            <h2 className="text-lg font-bold text-ink mb-4">새 프로젝트</h2>
            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-ink-secondary block mb-1">프로젝트 이름 *</label>
                <input
                  value={name} onChange={(e) => setName(e.target.value)}
                  placeholder="예: 2024 여름 캠페인"
                  className="w-full px-3 py-2.5 text-sm border border-line rounded-xl bg-surface-2 text-ink placeholder:text-ink-muted focus:outline-none focus:border-primary transition-colors"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-ink-secondary block mb-1">설명 (선택)</label>
                <textarea
                  value={description} onChange={(e) => setDescription(e.target.value)}
                  placeholder="프로젝트에 대한 간단한 설명" rows={3}
                  className="w-full px-3 py-2.5 text-sm border border-line rounded-xl bg-surface-2 text-ink placeholder:text-ink-muted focus:outline-none focus:border-primary transition-colors resize-none"
                />
              </div>
            </div>
            <div className="flex gap-2 mt-5">
              <button
                onClick={() => { setShowModal(false); setName(''); setDescription(''); }}
                className="flex-1 py-2.5 text-sm font-medium border border-line rounded-xl text-ink-secondary hover:bg-accent transition-colors"
              >취소</button>
              <button
                onClick={handleCreate} disabled={!name.trim() || creating}
                className="flex-1 py-2.5 text-sm font-medium bg-primary text-primary-foreground rounded-xl hover:bg-primary-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >{creating ? '생성 중...' : '만들기'}</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
