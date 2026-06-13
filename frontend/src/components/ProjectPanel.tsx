'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useProjects } from './ProjectContext';
import { useAuth } from './AuthProvider';

const SHOW_ON = ['/chat', '/simulation', '/generator', '/manage', '/simulations', '/generations'];

const statusColor: Record<string, string> = {
  COMPLETED: 'bg-emerald-400', completed: 'bg-emerald-400',
  QUEUED: 'bg-yellow-400', pending: 'bg-yellow-400',
  RUNNING: 'bg-blue-400', running: 'bg-blue-400',
  FAILED: 'bg-red-400', failed: 'bg-red-400',
};

const fmt = (iso: string) => {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="13" height="13" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
      className={`transition-transform duration-150 shrink-0 ${open ? 'rotate-90' : ''}`}
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

function ProjectItem({
  project,
  activeSimId,
  activeGenId,
  autoOpen,
  myOnly,
  myName,
  isOpen,
  onToggleOpen,
}: {
  project: { id: string; name: string; status: string };
  activeSimId: string | null;
  activeGenId: string | null;
  autoOpen: boolean;
  myOnly: boolean;
  myName: string | null;
  isOpen: boolean;
  onToggleOpen: (id: string) => void;
}) {
  const { details, loadDetails, selectedProjectId, selectProject } = useProjects();
  const router = useRouter();
  const [simOpen, setSimOpen] = useState(false);
  const [genOpen, setGenOpen] = useState(false);

  const d = details[project.id];
  const isLoading = isOpen && !d?.loaded;
  const isSelected = selectedProjectId === project.id;

  const allSims = d?.sims ?? [];
  const allGens = d?.gens ?? [];
  const sims = myOnly ? allSims.filter(s => s.created_by_name === myName) : allSims;
  const gens = myOnly ? allGens.filter(g => g.created_by_name === myName) : allGens;

  useEffect(() => {
    if (!autoOpen) return;
    onToggleOpen(project.id);
    loadDetails(project.id).then(() => {
      if (activeSimId) setSimOpen(true);
      if (activeGenId) setGenOpen(true);
    });
  }, [autoOpen]);

  const toggle = async () => {
    onToggleOpen(project.id);
    if (!isOpen) {
      selectProject(project.id);
      await loadDetails(project.id);
    }
  };

  const goToSim = (e: React.MouseEvent) => {
    e.stopPropagation();
    selectProject(project.id);
    router.push('/simulation');
  };

  const goToGen = (e: React.MouseEvent) => {
    e.stopPropagation();
    selectProject(project.id);
    router.push('/generator');
  };

  return (
    <div>
      <button
        onClick={toggle}
        className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-left ${
          isSelected ? 'bg-[#EBF3FF] dark:bg-[#1E3A5F]' : 'hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D]'
        }`}
      >
        <ChevronIcon open={isOpen} />
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
          className={isSelected ? 'text-[#3182F6] shrink-0' : 'text-[#8B95A1] shrink-0'}>
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
        </svg>
        <span className={`text-sm font-medium truncate flex-1 ${isSelected ? 'text-[#3182F6]' : 'text-[#191F28] dark:text-[#F2F4F6]'}`}>
          {project.name}
        </span>
      </button>

      {isOpen && (
        <div className="ml-5 border-l border-[#E5E8EB] dark:border-[#2D3748] pl-2 space-y-0.5 mt-0.5 mb-1">
          {isLoading ? (
            <p className="text-xs text-[#B0B8C1] px-2 py-1.5">불러오는 중...</p>
          ) : (
            <>
              {/* 시뮬레이션 섹션 */}
              <button
                onClick={() => setSimOpen(v => !v)}
                className="w-full flex items-center gap-2 px-2 py-1.5 hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] rounded-md transition-colors"
              >
                <ChevronIcon open={simOpen} />
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[#8B95A1] shrink-0">
                  <circle cx="12" cy="12" r="10" /><polygon points="10 8 16 12 10 16 10 8" />
                </svg>
                <span className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] uppercase tracking-wide">
                  시뮬레이션{sims.length > 0 ? ` (${sims.length})` : ''}
                </span>
              </button>
              {simOpen && (
                <div className="ml-4 space-y-0.5">
                  {sims.length === 0 ? (
                    <p className="text-xs text-[#B0B8C1] px-2 py-1">
                      {myOnly ? '내가 실행한 내역 없음' : '내역 없음'}
                    </p>
                  ) : sims.map(s => {
                    const isActive = s.id === activeSimId;
                    return (
                      <Link
                        key={s.id}
                        href={`/simulations/${s.id}`}
                        className={`flex items-center gap-2 px-2 py-1.5 rounded-md transition-colors group ${
                          isActive ? 'bg-[#EBF3FF] dark:bg-[#1E3A5F]' : 'hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F]'
                        }`}
                      >
                        <span className={`w-2 h-2 rounded-full shrink-0 ${statusColor[s.status] ?? 'bg-[#B0B8C1]'}`} />
                        <div className="flex-1 min-w-0">
                          <p className={`text-xs truncate ${isActive ? 'text-[#3182F6] font-medium' : 'text-[#4E5968] dark:text-[#9CA3AF] group-hover:text-[#3182F6]'}`}>
                            {s.sample_size}명 · {s.created_by_name ?? '—'}
                          </p>
                          <p className="text-[10px] text-[#B0B8C1] dark:text-[#4B5563]">{fmt(s.created_at)}</p>
                        </div>
                        {isActive && <span className="shrink-0 w-1.5 h-1.5 rounded-full bg-[#3182F6]" />}
                      </Link>
                    );
                  })}
                  <button
                    onClick={goToSim}
                    className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md text-xs text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors"
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                    </svg>
                    시뮬레이션 추가
                  </button>
                </div>
              )}

              {/* 제너레이터 섹션 */}
              <button
                onClick={() => setGenOpen(v => !v)}
                className="w-full flex items-center gap-2 px-2 py-1.5 hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] rounded-md transition-colors"
              >
                <ChevronIcon open={genOpen} />
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[#8B95A1] shrink-0">
                  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                </svg>
                <span className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] uppercase tracking-wide">
                  제너레이터{gens.length > 0 ? ` (${gens.length})` : ''}
                </span>
              </button>
              {genOpen && (
                <div className="ml-4 space-y-0.5">
                  {gens.length === 0 ? (
                    <p className="text-xs text-[#B0B8C1] px-2 py-1">
                      {myOnly ? '내가 실행한 내역 없음' : '내역 없음'}
                    </p>
                  ) : gens.map(g => {
                    const isActive = g.id === activeGenId;
                    return (
                      <Link
                        key={g.id}
                        href={`/generations/${g.id}`}
                        className={`flex items-center gap-2 px-2 py-1.5 rounded-md transition-colors group ${
                          isActive ? 'bg-[#EBF3FF] dark:bg-[#1E3A5F]' : 'hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F]'
                        }`}
                      >
                        <span className={`w-2 h-2 rounded-full shrink-0 ${statusColor[g.status] ?? 'bg-[#B0B8C1]'}`} />
                        <div className="flex-1 min-w-0">
                          <p className={`text-xs truncate ${isActive ? 'text-[#3182F6] font-medium' : 'text-[#4E5968] dark:text-[#9CA3AF] group-hover:text-[#3182F6]'}`}>
                            {g.product_name ?? '—'} · {g.created_by_name ?? '—'}
                          </p>
                          <p className="text-[10px] text-[#B0B8C1] dark:text-[#4B5563]">{fmt(g.created_at)}</p>
                        </div>
                        {isActive && <span className="shrink-0 w-1.5 h-1.5 rounded-full bg-[#3182F6]" />}
                      </Link>
                    );
                  })}
                  <button
                    onClick={goToGen}
                    className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md text-xs text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors"
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                    </svg>
                    제너레이터 추가
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default function ProjectPanel() {
  const pathname = usePathname();
  const { projects, loading, details, loadDetails, selectProject } = useProjects();
  const { user } = useAuth();
  const [myOnly, setMyOnly] = useState(false);
  const [openProjectId, setOpenProjectId] = useState<string | null>(null);

  const show = SHOW_ON.some(p => pathname.startsWith(p));

  const simMatch = pathname.match(/^\/simulations\/([^/]+)/);
  const genMatch = pathname.match(/^\/generations\/([^/]+)/);
  const activeSimId = simMatch?.[1] ?? null;
  const activeGenId = genMatch?.[1] ?? null;
  const activeItemId = activeSimId ?? activeGenId;

  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);

  useEffect(() => {
    if (!activeItemId) { setActiveProjectId(null); return; }

    for (const [pid, d] of Object.entries(details)) {
      if (activeSimId && d.sims.some(s => s.id === activeSimId)) { setActiveProjectId(pid); selectProject(pid); return; }
      if (activeGenId && d.gens.some(g => g.id === activeGenId)) { setActiveProjectId(pid); selectProject(pid); return; }
    }

    (async () => {
      for (const p of projects) {
        if (details[p.id]?.loaded) continue;
        await loadDetails(p.id);
        const d = details[p.id];
        if (!d) continue;
        if (activeSimId && d.sims.some(s => s.id === activeSimId)) { setActiveProjectId(p.id); selectProject(p.id); return; }
        if (activeGenId && d.gens.some(g => g.id === activeGenId)) { setActiveProjectId(p.id); selectProject(p.id); return; }
      }
    })();
  }, [activeItemId, details, projects]);

  if (!show) return null;

  return (
    <aside className="fixed top-0 left-56 h-full w-60 bg-[#FAFBFC] dark:bg-[#161B27] border-r border-[#E5E8EB] dark:border-[#2D3748] flex flex-col z-30 transition-colors">
      {/* 헤더 */}
      <div className="h-14 flex items-center justify-between px-4 border-b border-[#E5E8EB] dark:border-[#2D3748] shrink-0">
        <p className="text-sm font-semibold text-[#4E5968] dark:text-[#9CA3AF]">프로젝트</p>
        {/* 전체 / 내 것 토글 */}
        <div className="flex items-center gap-0.5 bg-[#F2F4F6] dark:bg-[#252D3D] rounded-lg p-0.5">
          <button
            onClick={() => setMyOnly(false)}
            className={`px-2 py-1 rounded-md text-[11px] font-medium transition-colors ${
              !myOnly
                ? 'bg-white dark:bg-[#1C2333] text-[#191F28] dark:text-[#F2F4F6] shadow-sm'
                : 'text-[#8B95A1] dark:text-[#6B7280] hover:text-[#4E5968] dark:hover:text-[#9CA3AF]'
            }`}
          >
            ALL
          </button>
          <button
            onClick={() => setMyOnly(true)}
            className={`px-2 py-1 rounded-md text-[11px] font-medium transition-colors ${
              myOnly
                ? 'bg-white dark:bg-[#1C2333] text-[#191F28] dark:text-[#F2F4F6] shadow-sm'
                : 'text-[#8B95A1] dark:text-[#6B7280] hover:text-[#4E5968] dark:hover:text-[#9CA3AF]'
            }`}
          >
            MY
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto py-2 px-2">
        {loading ? (
          <p className="text-xs text-[#B0B8C1] px-3 py-2">불러오는 중...</p>
        ) : projects.length === 0 ? (
          <p className="text-xs text-[#B0B8C1] px-3 py-2">프로젝트가 없습니다</p>
        ) : (
          <div className="space-y-0.5">
            {projects.map(p => (
              <ProjectItem
                key={p.id}
                project={p}
                activeSimId={activeSimId}
                activeGenId={activeGenId}
                autoOpen={p.id === activeProjectId}
                myOnly={myOnly}
                myName={user?.name ?? null}
                isOpen={openProjectId === p.id}
                onToggleOpen={(id) => setOpenProjectId(prev => prev === id ? null : id)}
              />
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
